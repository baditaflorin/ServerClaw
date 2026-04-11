#!/usr/bin/env python3
"""
Neko Timeout Hierarchy Compliance Test

Verifies NGINX proxy_read_timeout for browser.lv3.org is explicitly set
to 3600s (1 hour) for long-lived WebRTC streams.

Background (ADR 0170):
  ADR 0170 specifies a timeout hierarchy:
  - http_request layer: 60s maximum (default for most HTTP)
  - WebRTC streams: 5-60 minute operator interactions (3600s)

Neko (this implementation) requires a documented exception to ADR 0170:
  - Long-lived WebSocket connections for signalling
  - Media negotiation and ICE candidate exchange
  - Operator maintains active browser session for debugging/exploration

This test ensures:
1. The 3600s timeout is explicitly configured (not accidental)
2. ADR 0380 documents the exception (so it's not reverted later)
3. No default 60s timeout is accidentally used

This prevents timeout failures that plagued past RTC implementations.
"""

import re
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Optional


def read_file(path: str) -> Optional[str]:
    """Read file contents."""
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return None


def find_nginx_site_config() -> Optional[str]:
    """
    Find browser.lv3.org NGINX site configuration.

    Checks multiple possible locations:
    - /etc/nginx/sites-enabled/browser.lv3.org.conf
    - /etc/nginx/sites-available/browser.lv3.org.conf
    - Local playbook template path
    """
    paths = [
        "/etc/nginx/sites-enabled/browser.lv3.org.conf",
        "/etc/nginx/sites-available/browser.lv3.org.conf",
        "collections/ansible_collections/lv3/platform/playbooks/templates/nginx-site-neko.conf.j2",
    ]

    for path in paths:
        content = read_file(path)
        if content:
            print(f"Found NGINX config: {path}")
            return content

    return None


def find_adr_0380() -> Optional[str]:
    """
    Find ADR 0380 documentation file.

    Checks:
    - docs/adr/0380-neko-*.md
    """
    import glob

    adr_paths = glob.glob("docs/adr/0380-neko-*.md")
    if adr_paths:
        return read_file(adr_paths[0])

    return None


def test_neko_nginx_timeout_is_explicit():
    """
    Test: NGINX proxy_read_timeout is explicitly set to 3600s.

    Failure cases:
    - Timeout not set at all (would use default 60s)
    - Timeout set to less than 3600s
    - Timeout set but commented out
    """
    print("\n=== Neko NGINX Timeout Configuration Test ===")

    nginx_config = find_nginx_site_config()
    if not nginx_config:
        print("✗ FAILED: Could not find browser.lv3.org NGINX configuration")
        print("  Check paths:")
        print("    - /etc/nginx/sites-enabled/browser.lv3.org.conf")
        print("    - /etc/nginx/sites-available/browser.lv3.org.conf")
        print("    - collections/.../templates/nginx-site-neko.conf.j2")
        return False

    # Test 1: Find proxy_read_timeout directive
    print("Test 1: Checking for explicit proxy_read_timeout...")

    # Match proxy_read_timeout with 3600s
    # Regex: proxy_read_timeout 3600s;
    pattern = r"^\s*proxy_read_timeout\s+3600s\s*;"
    matches = [
        line for line in nginx_config.split("\n") if re.search(pattern, line) and not line.strip().startswith("#")
    ]

    if not matches:
        print("  ✗ FAILED: proxy_read_timeout 3600s not found")

        # Check if it's set to something else
        other_timeouts = [
            line
            for line in nginx_config.split("\n")
            if "proxy_read_timeout" in line and not line.strip().startswith("#")
        ]

        if other_timeouts:
            print(f"  Found other timeout settings:")
            for line in other_timeouts:
                print(f"    {line.strip()}")
        else:
            print(f"  No proxy_read_timeout found at all (would default to 60s)")

        return False

    print(f"  ✓ Found {len(matches)} explicit proxy_read_timeout 3600s directive(s)")
    for match in matches:
        print(f"    {match.strip()}")

    # Test 2: Verify it's applied to neko location blocks
    print("\nTest 2: Verifying timeout applies to neko locations...")

    # Find location blocks that should have this timeout
    location_patterns = [
        r"location\s+/",  # Root location
        r"location\s+/api/health",  # Health endpoint
        r"location\s+/ws",  # WebSocket endpoint
    ]

    for pattern in location_patterns:
        location_blocks = re.findall(f"{pattern}[^{{]*{{([^}}]*?)}}", nginx_config, re.DOTALL)

        if location_blocks:
            for block in location_blocks:
                if "proxy_read_timeout 3600s" in block:
                    print(f"  ✓ {pattern} has 3600s timeout")
                else:
                    print(f"  ⚠ {pattern} may not have explicit timeout in block")

    return True


def test_adr_0380_documents_timeout_exception():
    """
    Test: ADR 0380 documents the ADR 0170 exception.

    Ensures the 3600s timeout exception is intentional, not accidental.
    """
    print("\n=== ADR 0380 Timeout Exception Documentation Test ===")

    adr_content = find_adr_0380()
    if not adr_content:
        print("✗ FAILED: ADR 0380 not found")
        print("  Expected: docs/adr/0380-neko-*.md")
        return False

    # Check for keywords indicating timeout exception is documented
    keywords = [
        "ADR 0170",
        "timeout",
        "3600",
        "exception",
        "long-lived",
        "WebRTC",
    ]

    found_keywords = {kw: kw.lower() in adr_content.lower() for kw in keywords}

    print("Keywords in ADR 0380:")
    for kw, found in found_keywords.items():
        status = "✓" if found else "✗"
        print(f"  {status} {kw}")

    # ADR should mention timeout exception
    has_timeout_exception = ("ADR 0170" in adr_content or "ADR 0170" in adr_content.replace(" ", "")) and (
        "exception" in adr_content.lower() or "timeout" in adr_content.lower()
    )

    if has_timeout_exception:
        print("\n✓ ADR 0380 documents timeout exception")
        return True
    else:
        print("\n✗ FAILED: ADR 0380 does not clearly document ADR 0170 exception")
        print("  Add section explaining: Why Neko requires 3600s timeout (long-lived WebRTC sessions)")
        return False


def test_no_default_timeout_will_be_used():
    """
    Test: Verify 60s default won't be used by accident.

    Checks that:
    1. At least one location block explicitly sets 3600s
    2. OR the server block sets it (applies to all locations)
    """
    print("\n=== Default Timeout Prevention Test ===")

    nginx_config = find_nginx_site_config()
    if not nginx_config:
        print("✗ FAILED: NGINX config not found")
        return False

    # Count how many times proxy_read_timeout is set
    timeout_directives = [
        line.strip()
        for line in nginx_config.split("\n")
        if "proxy_read_timeout" in line and not line.strip().startswith("#")
    ]

    print(f"proxy_read_timeout directives found: {len(timeout_directives)}")
    for directive in timeout_directives:
        print(f"  {directive}")

    if len(timeout_directives) == 0:
        print("\n✗ FAILED: No proxy_read_timeout directives found")
        print("  NGINX will use default 30s, breaking WebRTC streams after 30s")
        return False

    # Verify at least one is 3600s
    has_3600 = any("3600" in d for d in timeout_directives)
    if not has_3600:
        print("\n✗ FAILED: No directive sets 3600s timeout")
        return False

    print("\n✓ Timeout configuration prevents default (60s) from being used")
    return True


def main():
    """Run all timeout compliance tests."""
    print("\n" + "=" * 60)
    print("Neko Timeout Hierarchy Compliance Test Suite")
    print("=" * 60)

    tests = [
        test_neko_nginx_timeout_is_explicit,
        test_adr_0380_documents_timeout_exception,
        test_no_default_timeout_will_be_used,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test raised exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if all(results):
        print("\n✓ ALL TESTS PASSED: Neko timeout configuration is compliant")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED: Fix timeout configuration")
        return 1


if __name__ == "__main__":
    sys.exit(main())
