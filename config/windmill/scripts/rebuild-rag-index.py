import json
import os
import urllib.request


def main():
    base_url = os.environ["PLATFORM_CONTEXT_INTERNAL_URL"].rstrip("/")
    token = os.environ["PLATFORM_CONTEXT_API_TOKEN"]
    request = urllib.request.Request(
        f"{base_url}/v1/admin/rebuild-local",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=b"{}",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))
