#!/usr/bin/env python3
"""Certbot manual auth/cleanup hook for Hetzner Cloud DNS (DNS-01).

This script mirrors the Cloud-API behaviour of the sibling Ansible role
``hetzner_dns_records`` (see
``collections/ansible_collections/lv3/platform/roles/hetzner_dns_records/tasks/record.yml``).
It talks to the modern Hetzner Console / Cloud API at
``https://api.hetzner.cloud/v1`` using ``Authorization: Bearer <token>`` and
the zone rrset endpoints:

    GET    /zones                                       — list zones (paginated)
    GET    /zones/{zone}/rrsets?name=<name>&type=TXT    — read an rrset
    POST   /zones/{zone}/rrsets                         — create an rrset
    POST   /zones/{zone}/rrsets/{ref}/actions/set_records — replace records[]
    DELETE /zones/{zone}/rrsets/{ref}                   — delete an rrset

It deliberately does NOT use the deprecated standalone Hetzner DNS API
(dns.hetzner.com), which the certbot-dns-hetzner plugin uses and which now
fails ("token invalid (unauthorized)") for accounts migrated to the Cloud API.

certbot invokes this script twice per challenge:

    --manual-auth-hook    "<this script> auth"
    --manual-cleanup-hook "<this script> cleanup"

certbot supplies ``CERTBOT_DOMAIN`` and ``CERTBOT_VALIDATION`` in the
environment. The API token is read from the file named by
``HETZNER_CLOUD_DNS_CREDENTIALS_FILE`` (a single line
``hetzner_cloud_dns_api_token = <TOKEN>``), falling back to
``HETZNER_DNS_API_TOKEN``.

Appending (rather than overwriting) the TXT value is critical: a SAN cert for
``apps.example.com`` + ``*.apps.example.com`` triggers TWO challenges at the
SAME ``_acme-challenge.apps`` name with different values; both must coexist in
the rrset for validation to succeed.

Uses only the Python standard library (no third-party imports).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE_URL = os.environ.get(
    "HETZNER_DNS_API_BASE_URL", "https://api.hetzner.cloud/v1"
).rstrip("/")
ACME_PREFIX = "_acme-challenge"
TXT_TTL = 60


def log(message):
    """Print concise progress to stderr."""
    sys.stderr.write("[hetzner-cloud-acme-hook] {0}\n".format(message))
    sys.stderr.flush()


def die(message):
    """Print an error to stderr and exit non-zero."""
    sys.stderr.write("[hetzner-cloud-acme-hook] ERROR: {0}\n".format(message))
    sys.stderr.flush()
    sys.exit(1)


def read_token():
    """Resolve the Hetzner Cloud API token from the credentials file or env."""
    credentials_file = os.environ.get("HETZNER_CLOUD_DNS_CREDENTIALS_FILE", "")
    if credentials_file:
        try:
            with open(credentials_file, "r") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        if key.strip() == "hetzner_cloud_dns_api_token":
                            token = value.strip()
                            if token:
                                return token
        except IOError as error:
            log(
                "could not read credentials file {0}: {1}".format(
                    credentials_file, error
                )
            )
    token = os.environ.get("HETZNER_DNS_API_TOKEN", "").strip()
    if token:
        return token
    die(
        "no Hetzner Cloud DNS API token found "
        "(checked HETZNER_CLOUD_DNS_CREDENTIALS_FILE and HETZNER_DNS_API_TOKEN)"
    )


def api_request(method, path, token, query=None, body=None,
                ok_status=(200, 201, 204)):
    """Perform an authenticated Cloud API request and return (status, json)."""
    url = API_BASE_URL + path
    if query:
        url = url + "?" + urllib.parse.urlencode(query)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, method=method)
    request.add_header("Authorization", "Bearer {0}".format(token))
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            status = response.getcode()
            raw = response.read().decode("utf-8") if response.length != 0 else ""
            payload = json.loads(raw) if raw.strip() else {}
            return status, payload
    except urllib.error.HTTPError as error:
        raw = ""
        try:
            raw = error.read().decode("utf-8")
        except Exception:  # noqa: BLE001 - best-effort error body
            raw = ""
        if error.code in ok_status:
            payload = {}
            if raw.strip():
                try:
                    payload = json.loads(raw)
                except ValueError:
                    payload = {}
            return error.code, payload
        die(
            "{0} {1} failed: HTTP {2} {3}".format(
                method, url, error.code, raw.strip()
            )
        )
    except urllib.error.URLError as error:
        die("{0} {1} failed: {2}".format(method, url, error))


def list_zones(token):
    """Return all zones, paginating through the Cloud API."""
    zones = []
    page = 1
    while True:
        status, payload = api_request(
            "GET",
            "/zones",
            token,
            query={"page": page, "per_page": 50},
            ok_status=(200,),
        )
        batch = payload.get("zones", []) or []
        zones.extend(batch)
        meta = (payload.get("meta") or {}).get("pagination") or {}
        next_page = meta.get("next_page")
        if not next_page or not batch:
            break
        page = next_page
    return zones


def zone_identifier(zone):
    """Return the provider reference used in rrset URLs for a zone."""
    # The Cloud API addresses zones by name in the rrset path; fall back to id.
    return zone.get("name") or str(zone.get("id"))


def resolve_zone(token, domain):
    """Pick the zone whose name is the longest suffix of the domain."""
    zones = list_zones(token)
    best = None
    best_len = -1
    for zone in zones:
        name = (zone.get("name") or "").rstrip(".")
        if not name:
            continue
        if domain == name or domain.endswith("." + name):
            if len(name) > best_len:
                best = zone
                best_len = len(name)
    if best is None:
        die(
            "no Hetzner Cloud DNS zone is a suffix of domain '{0}'".format(domain)
        )
    return best


def relative_record_name(domain, zone_name):
    """Compute the zone-relative _acme-challenge record name."""
    zone_name = zone_name.rstrip(".")
    if domain == zone_name:
        remainder = ""
    elif domain.endswith("." + zone_name):
        remainder = domain[: -(len(zone_name) + 1)]
    else:
        remainder = domain
    if remainder:
        return "{0}.{1}".format(ACME_PREFIX, remainder)
    return ACME_PREFIX


def get_txt_rrset(token, zone_ref, record_name):
    """Return the existing TXT rrset dict for record_name, or None."""
    status, payload = api_request(
        "GET",
        "/zones/{0}/rrsets".format(urllib.parse.quote(zone_ref, safe="")),
        token,
        query={"name": record_name, "type": "TXT"},
        ok_status=(200, 404),
    )
    if status == 404:
        return None
    rrsets = payload.get("rrsets", []) or []
    for rrset in rrsets:
        if rrset.get("name") == record_name and rrset.get("type") == "TXT":
            return rrset
    return None


def record_values(rrset):
    """Return the list of TXT values from an rrset's records[]."""
    return [
        record.get("value")
        for record in (rrset.get("records") or [])
        if record.get("value") is not None
    ]


def set_records(token, zone_ref, rrset_ref, values):
    """Replace the records[] of an rrset via the set_records action."""
    body = {"records": [{"value": value, "comment": ""} for value in values]}
    api_request(
        "POST",
        "/zones/{0}/rrsets/{1}/actions/set_records".format(
            urllib.parse.quote(zone_ref, safe=""),
            urllib.parse.quote(str(rrset_ref), safe=""),
        ),
        token,
        body=body,
        ok_status=(200, 201),
    )


def create_rrset(token, zone_ref, record_name, values):
    """Create a new TXT rrset with the given values."""
    body = {
        "name": record_name,
        "type": "TXT",
        "ttl": TXT_TTL,
        "records": [{"value": value, "comment": ""} for value in values],
    }
    api_request(
        "POST",
        "/zones/{0}/rrsets".format(urllib.parse.quote(zone_ref, safe="")),
        token,
        body=body,
        ok_status=(200, 201, 409),
    )


def delete_rrset(token, zone_ref, rrset_ref):
    """Delete an rrset; treat 404 as already gone."""
    api_request(
        "DELETE",
        "/zones/{0}/rrsets/{1}".format(
            urllib.parse.quote(zone_ref, safe=""),
            urllib.parse.quote(str(rrset_ref), safe=""),
        ),
        token,
        ok_status=(200, 201, 204, 404),
    )


def rrset_reference(rrset):
    """Return the provider reference used to address an rrset in URLs."""
    # The Cloud API addresses an rrset by "<name>/<type>" or by id; prefer id.
    if rrset.get("id") is not None:
        return rrset.get("id")
    return "{0}/{1}".format(rrset.get("name"), rrset.get("type"))


def do_auth(token, domain, validation):
    quoted = '"{0}"'.format(validation)
    zone = resolve_zone(token, domain)
    zone_ref = zone_identifier(zone)
    record_name = relative_record_name(domain, zone.get("name", ""))
    log(
        "auth: zone='{0}' record='{1}' (domain '{2}')".format(
            zone.get("name"), record_name, domain
        )
    )
    existing = get_txt_rrset(token, zone_ref, record_name)
    if existing is None:
        log("auth: creating TXT rrset with 1 value")
        create_rrset(token, zone_ref, record_name, [quoted])
    else:
        values = record_values(existing)
        if quoted in values:
            log("auth: TXT value already present; no change")
        else:
            values.append(quoted)
            log("auth: appending TXT value -> {0} value(s)".format(len(values)))
            set_records(token, zone_ref, rrset_reference(existing), values)
    propagation_seconds = int(
        os.environ.get("HETZNER_CLOUD_DNS_PROPAGATION_SECONDS", "60") or "60"
    )
    log("auth: sleeping {0}s for DNS propagation".format(propagation_seconds))
    time.sleep(propagation_seconds)


def do_cleanup(token, domain, validation):
    quoted = '"{0}"'.format(validation)
    zone = resolve_zone(token, domain)
    zone_ref = zone_identifier(zone)
    record_name = relative_record_name(domain, zone.get("name", ""))
    existing = get_txt_rrset(token, zone_ref, record_name)
    if existing is None:
        log("cleanup: rrset already gone; nothing to do")
        return
    values = record_values(existing)
    remaining = [value for value in values if value != quoted]
    if len(remaining) == len(values):
        log("cleanup: value not present; nothing to remove")
        if not remaining:
            delete_rrset(token, zone_ref, rrset_reference(existing))
        return
    if remaining:
        log(
            "cleanup: removing value -> {0} value(s) remain".format(
                len(remaining)
            )
        )
        set_records(token, zone_ref, rrset_reference(existing), remaining)
    else:
        log("cleanup: removing last value; deleting rrset")
        delete_rrset(token, zone_ref, rrset_reference(existing))


def main(argv):
    if len(argv) < 2 or argv[1] not in ("auth", "cleanup"):
        die("usage: {0} <auth|cleanup>".format(argv[0]))
    action = argv[1]
    domain = os.environ.get("CERTBOT_DOMAIN", "").strip()
    validation = os.environ.get("CERTBOT_VALIDATION", "").strip()
    if not domain:
        die("CERTBOT_DOMAIN is not set")
    if not validation:
        die("CERTBOT_VALIDATION is not set")
    token = read_token()
    if action == "auth":
        do_auth(token, domain, validation)
    else:
        do_cleanup(token, domain, validation)


if __name__ == "__main__":
    main(sys.argv)
