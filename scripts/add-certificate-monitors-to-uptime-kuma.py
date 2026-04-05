#!/usr/bin/env python3
"""
Add SSL Certificate Monitoring to Uptime Kuma

This script automatically creates Uptime Kuma monitors for all edge-published domains,
configured to check:
- HTTP status codes
- SSL certificate validity
- Certificate expiration (alerts < 30 days)

Usage:
    python3 scripts/add-certificate-monitors-to-uptime-kuma.py \
        --base-url https://uptime.lv3.org \
        --api-key <uptime-kuma-api-key> \
        --config config/subdomain-catalog.json

Requirements:
    - requests library (pip install requests)
    - Uptime Kuma admin API key from https://uptime.lv3.org/settings
"""

import json
import sys
import argparse
from typing import Dict, List, Optional
import requests
from pathlib import Path


class UptimeKumaClient:
    """Client for Uptime Kuma REST API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make authenticated request to Uptime Kuma API."""
        url = f"{self.base_url}/api/{endpoint}"
        try:
            if method == "GET":
                resp = self.session.get(url)
            elif method == "POST":
                resp = self.session.post(url, json=data)
            elif method == "PUT":
                resp = self.session.put(url, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if resp.status_code >= 400:
                raise Exception(f"API error {resp.status_code}: {resp.text}")

            return resp.json() if resp.text else {}
        except requests.RequestException as e:
            raise Exception(f"Request failed: {e}")

    def get_monitors(self) -> List[Dict]:
        """Get all monitors."""
        result = self._request("GET", "monitor")
        return result.get("monitors", []) if isinstance(result, dict) else result

    def create_monitor(self, monitor_config: Dict) -> Dict:
        """Create a new monitor."""
        return self._request("POST", "monitor", monitor_config)

    def update_monitor(self, monitor_id: int, monitor_config: Dict) -> Dict:
        """Update an existing monitor."""
        return self._request("PUT", f"monitor/{monitor_id}", monitor_config)

    def get_monitor(self, monitor_id: int) -> Dict:
        """Get a specific monitor."""
        return self._request("GET", f"monitor/{monitor_id}")


def load_subdomain_catalog(config_path: str) -> List[Dict]:
    """Load subdomain catalog from JSON."""
    try:
        with open(config_path, 'r') as f:
            catalog = json.load(f)
        return catalog.get("subdomains", [])
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}", file=sys.stderr)
        sys.exit(1)


def create_certificate_monitor_config(fqdn: str, service_id: str = "") -> Dict:
    """Create Uptime Kuma monitor configuration for SSL certificate checking."""
    return {
        "type": "http",
        "name": f"Certificate: {fqdn}",
        "url": f"https://{fqdn}/",
        "method": "GET",
        "hostname": fqdn,
        "port": 443,
        "maxretries": 2,
        "interval": 3600,  # Check every hour
        "retryInterval": 60,  # Retry after 60 seconds
        "timeout": 30,
        "notificationIDList": [],
        "tags": ["ssl-certificate", "monitoring", service_id] if service_id else ["ssl-certificate", "monitoring"],
        "expiryNotification": True,  # Alert on certificate expiration
        "tlsca": "",
        "tlscert": "",
        "tlskey": "",
        "tlspin": "",
        "tlsversion": "",
        "acceptable_status_codes": ["200", "201", "202", "203", "204", "205", "206", "300", "301", "302", "303", "304", "305", "307", "308", "400", "401", "402", "403", "404"],
        "validateSSL": True,
        "follow_redirects": True,
        "description": f"Monitor SSL certificate validity and expiration for {fqdn}",
        "active": True,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Add SSL certificate monitors to Uptime Kuma"
    )
    parser.add_argument("--base-url", required=True,
                        help="Uptime Kuma base URL (e.g., https://uptime.lv3.org)")
    parser.add_argument("--api-key", required=True,
                        help="Uptime Kuma API key (from settings)")
    parser.add_argument("--config", default="config/subdomain-catalog.json",
                        help="Path to subdomain catalog config")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be created without actually creating")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip domains that already have monitors")
    parser.add_argument("--fqdn", help="Only add monitor for a specific FQDN")
    parser.add_argument("--update-all", action="store_true",
                        help="Update existing monitors with new configuration")

    args = parser.parse_args()

    # Load catalog
    catalog = load_subdomain_catalog(args.config)

    # Filter domains
    domains_to_monitor = []
    for entry in catalog:
        if args.fqdn and entry["fqdn"] != args.fqdn:
            continue
        if entry.get("exposure") not in ["edge-published", "edge-static"]:
            continue
        domains_to_monitor.append(entry)

    if not domains_to_monitor:
        print("No edge-published/static domains found to monitor")
        sys.exit(0)

    print(f"Found {len(domains_to_monitor)} edge-published domains to monitor")

    if args.dry_run:
        print("\nDry-run mode: Showing what would be created\n")
        for entry in domains_to_monitor:
            config = create_certificate_monitor_config(entry["fqdn"], entry.get("service_id", ""))
            print(json.dumps(config, indent=2))
        sys.exit(0)

    # Connect to Uptime Kuma
    print(f"\nConnecting to Uptime Kuma at {args.base_url}...")
    try:
        client = UptimeKumaClient(args.base_url, args.api_key)
        existing_monitors = client.get_monitors()
        print(f"Found {len(existing_monitors)} existing monitors")
    except Exception as e:
        print(f"Error connecting to Uptime Kuma: {e}", file=sys.stderr)
        sys.exit(1)

    # Create mapping of existing monitors by URL
    existing_by_url = {m.get("url", ""): m for m in existing_monitors}
    existing_by_name = {m.get("name", ""): m for m in existing_monitors}

    created = 0
    updated = 0
    skipped = 0

    for entry in domains_to_monitor:
        fqdn = entry["fqdn"]
        monitor_name = f"Certificate: {fqdn}"
        monitor_url = f"https://{fqdn}/"
        config = create_certificate_monitor_config(fqdn, entry.get("service_id", ""))

        # Check if monitor already exists
        existing_monitor = existing_by_url.get(monitor_url) or existing_by_name.get(monitor_name)

        if existing_monitor:
            if args.update_all:
                print(f"Updating monitor for {fqdn}...")
                try:
                    client.update_monitor(existing_monitor.get("id"), config)
                    print(f"  ✓ Updated: {monitor_name}")
                    updated += 1
                except Exception as e:
                    print(f"  ✗ Failed to update: {e}", file=sys.stderr)
            elif args.skip_existing:
                print(f"Skipping {fqdn} (monitor already exists)")
                skipped += 1
            else:
                print(f"Monitor already exists for {fqdn}")
                skipped += 1
        else:
            print(f"Creating monitor for {fqdn}...")
            try:
                result = client.create_monitor(config)
                print(f"  ✓ Created: {monitor_name} (ID: {result.get('id', 'unknown')})")
                created += 1
            except Exception as e:
                print(f"  ✗ Failed to create: {e}", file=sys.stderr)

    print(f"\nSummary:")
    print(f"  Created: {created}")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")
    print(f"  Total: {len(domains_to_monitor)}")

    sys.exit(0 if created + updated + skipped == len(domains_to_monitor) else 1)


if __name__ == "__main__":
    main()
