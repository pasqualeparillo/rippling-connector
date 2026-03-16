"""
Auth verification test for Rippling connector.
Run this script to verify your credentials are correctly configured.

Supports both auth methods defined in connector_spec.yaml:
  - oauth: exchanges refresh_token for an access token, then calls /platform/api/me
  - api_token: uses static Bearer token to call /platform/api/me

Usage:
    python tests/unit/sources/rippling/auth_test.py
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', '..'))

import requests

BASE_URL = "https://api.rippling.com"
TOKEN_URL = "https://app.rippling.com/api/o/token/"
VERIFY_ENDPOINT = "/platform/api/me"


def load_config(source_name: str) -> dict:
    # auth_test.py lives at tests/unit/sources/<source>/auth_test.py
    # dev_config.json lives at tests/unit/sources/<source>/configs/dev_config.json
    config_path = os.path.join(os.path.dirname(__file__), "configs", "dev_config.json")
    config_path = os.path.normpath(config_path)
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"dev_config.json not found at: {config_path}")
    with open(config_path) as f:
        return json.load(f)


def get_access_token_oauth(config: dict) -> str:
    """Exchange refresh_token for a short-lived access token."""
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": config["refresh_token"],
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Token exchange failed: HTTP {resp.status_code} — {resp.text}"
        )
    return resp.json()["access_token"]


def test_auth():
    """Verify credentials in dev_config.json are valid by making a simple API call."""
    config = load_config("rippling")

    # Determine auth method and build Bearer token
    if "refresh_token" in config:
        print("Auth method: OAuth 2.0 (exchanging refresh_token for access_token)...")
        try:
            access_token = get_access_token_oauth(config)
        except RuntimeError as e:
            print(f"[FAIL] {e}")
            return False
        auth_method_label = "OAuth 2.0"
    elif "api_token" in config:
        access_token = config["api_token"]
        auth_method_label = "API Token (Bearer)"
    else:
        print("[FAIL] dev_config.json contains neither 'refresh_token' nor 'api_token'.")
        print("       Check tests/unit/sources/rippling/configs/dev_config.json")
        return False

    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(
        f"{BASE_URL}{VERIFY_ENDPOINT}",
        headers=headers,
        timeout=10,
    )

    if response.status_code == 200:
        data = response.json()
        # Print non-sensitive identity fields if available
        name = data.get("name") or data.get("workEmail") or data.get("id") or "(no name field)"
        print(f"[PASS] Authentication successful using {auth_method_label}.")
        print(f"       Connected as: {name}")
        return True
    elif response.status_code == 401:
        print(f"[FAIL] Authentication failed: Invalid credentials (HTTP 401).")
        print(f"       Check your credentials in tests/unit/sources/rippling/configs/dev_config.json")
        print(f"       Response: {response.text}")
        return False
    elif response.status_code == 403:
        print(f"[FAIL] Authorization failed: Insufficient permissions (HTTP 403).")
        print(f"       Ensure your credentials have the required scopes/permissions.")
        print(f"       Response: {response.text}")
        return False
    else:
        print(f"[FAIL] Unexpected response: HTTP {response.status_code}")
        print(f"       Body: {response.text}")
        return False


if __name__ == "__main__":
    success = test_auth()
    sys.exit(0 if success else 1)
