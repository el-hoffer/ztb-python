#!/usr/bin/env python3

"""Gateway version management CLI.
This script provides four subcommands (all of which support --dry-run):
1) generate-template - build a CSV template based on current state
2) download - read the CSV and download the selected version
3) set-default - read the CSV and set the selected version as default
4) activate - read the CSV and activate the selected version

Example usage:  "python3 upgrader.py generate-template" or "python upgrader.py activate --dry-run"
"""

from __future__ import annotations

import os
from dotenv import load_dotenv
import requests
import argparse
import csv
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

load_dotenv()


CSV_COLUMNS = [
    "gateway_id",
    "gateway_name",
    "active_version",
    "default_version",
    "downloaded_version_1",
    "downloaded_version_2",
    "downloaded_version_3",
    "desired_version",
    "available_versions",
]

class APIClient:
    def __init__(self, apiUrl: str, token: str, timeout: int = 30) -> None:
        if not token:
            raise ValueError("API token missing, make sure apiKey is specified in .env")
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()
        self.apiUrl = apiUrl

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.apiUrl}{path}"
        kwargs.setdefault("headers", self._headers())
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(method=method, url=url, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type or response.text.strip().startswith(("{", "[")):
            return response.json()
        return response.text

    def list_gateways(self) -> List[Dict[str, Any]]:
        """Return gateway records from the API."""
        data_ztb = self._request("GET", "v3/Gateway/")
        data_hub = self._request("GET", "v3/Gateway/?gateway_type=access")
        all_gws = data_ztb.get("rows", []) + data_hub.get("rows", [])
        return [
            gateway
            for row in all_gws
            for gateway in row.get("gateways", [])
            if gateway.get("operational_state") in {"standalone", "active", "standby"}
        ]

    def list_available_versions(self) -> List[str]:
        """Return the globally available versions from the API."""
        data = self._request("GET", "v2/Gateway/releases")
        items = data.get("result", [])
        return [
            normalize_version(item["version_number"])
            for item in items
            if item.get("version_number")
        ]
    
    def get_gateway(self, gateway_id: str) -> Dict[str, Any]:
        """Return the current gateway."""
        data = self._request("GET", f"v2/Gateway/id/{gateway_id}")
        return data.get("result", data)

    def download_version(self, gateway_id: str, version: str) -> Any:
        """Request download of a version for a gateway."""
        payload = {"action": "download","version": version}
        return self._request("POST", f"v2/Gateway/sw_image_update/id/{gateway_id}", json=payload)
    
    def set_default_version(self, gateway_id: str, version: str) -> Any:
        """Set the default version for a gateway."""
        payload = {"action": "set_default", "version": version}
        return self._request("POST", f"v2/Gateway/sw_image_update/id/{gateway_id}", json=payload)

    def activate_version(self, gateway_id: str, version: str) -> Any:
        """Activate desired version for selected gateways."""
        payload = {"action": "activate","version": version}
        return self._request("POST", f"v2/Gateway/sw_image_update/id/{gateway_id}", json=payload)



def downloaded_versions(gateway: Dict[str, Any]) -> List[str]:
    """Extract up to three downloaded versions."""
    versions: List[str] = []
    for image in get_gateway_images(gateway):
        version = normalize_version(image.get("version"))
        if version:
            versions.append(version)
    return versions[:3]

def get_default_version(gateway: Dict[str, Any]) -> str:
    """Return the version marked as default in sw_image_status.images."""
    for image in get_gateway_images(gateway):
        if image.get("is_default") is True:
            return normalize_version(image.get("version"))
    return ""

def normalize_version(value: Any) -> str:
    """Normalize version strings from the API/CSV."""
    if value is None:
        return ""
    return unquote(str(value)).strip()

def get_gateway_images(gateway: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return sw_image_status.images safely."""
    sw_image_status = gateway.get("sw_image_status") or {}
    images = sw_image_status.get("images") or []
    return [image for image in images if isinstance(image, dict)]

def get_all_downloaded_versions(gateway: Dict[str, Any]) -> List[str]:
    """Return all downloaded versions present on the gateway."""
    versions: List[str] = []
    for image in get_gateway_images(gateway):
        version = normalize_version(image.get("version"))
        if version:
            versions.append(version)
    return versions

def gateway_to_csv_row(gateway: Dict[str, Any], available_versions: List[str]) -> Dict[str, str]:
    """Map a gateway payload to CSV."""
    gateway_id = gateway["gateway_id"]
    gateway_name = gateway["display_name"]
    active_version = normalize_version(gateway.get("running_version"))
    default_version = get_default_version(gateway)
    downloaded = downloaded_versions(gateway)

    row = {
        "gateway_id": gateway_id,
        "gateway_name": gateway_name,
        "active_version": active_version,
        "default_version": default_version,
        "downloaded_version_1": downloaded[0] if len(downloaded) > 0 else "",
        "downloaded_version_2": downloaded[1] if len(downloaded) > 1 else "",
        "downloaded_version_3": downloaded[2] if len(downloaded) > 2 else "",
        "desired_version": "",
        "available_versions": ";".join(available_versions),
    }
    return row

def generate_template(client: APIClient) -> int:
    """Generate a CSV template populated from gateway and version APIs."""
    gateways = client.list_gateways()
    available_versions = client.list_available_versions()
    output_csv = "gateways.csv"

    with open(output_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for gateway in gateways:
            writer.writerow(gateway_to_csv_row(gateway, available_versions))

    print(f"Wrote template with {len(gateways)} gateways to {output_csv}")
    if not available_versions:
        print("Warning: no available versions were returned by the API.")
    return 0



def parse_available_versions(raw_value: str) -> List[str]:
    """Parse semicolon-separated available versions from the CSV."""
    if not raw_value:
        return []
    return [part.strip() for part in raw_value.split(";") if part.strip()]



def process_csv(
    client: APIClient,
    csv_path: str,
    action: str,
    dry_run: bool = False,
) -> int:
    """Process download, set-default, or activation requests from a CSV file."""
    if action not in {"download", "activate", "set-default"}:
        raise ValueError(f"Unsupported action: {action}")

    success_count = 0
    failure_count = 0
    skipped_count = 0

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing_columns = [
            col
            for col in ("gateway_id", "desired_version", "available_versions")
            if col not in reader.fieldnames
        ]
        if missing_columns:
            print(f"Error: CSV is missing required columns: {', '.join(missing_columns)}")
            return 2

        for row_number, row in enumerate(reader, start=2):
            gateway_id = (row.get("gateway_id") or "").strip()
            gateway_name = (row.get("gateway_name") or "").strip()
            desired_version = normalize_version(row.get("desired_version"))
            available_versions = [
                normalize_version(version)
                for version in parse_available_versions((row.get("available_versions") or "").strip())
            ]
            label = gateway_name or gateway_id or f"row {row_number}"

            if not gateway_id:
                skipped_count += 1
                print(f"[SKIP] row {row_number}: missing gateway_id")
                continue

            if not desired_version:
                skipped_count += 1
                print(f"[SKIP] {label}: desired_version is blank")
                continue

            if available_versions and desired_version not in available_versions:
                failure_count += 1
                print(
                    f"[FAIL] {label}: desired_version '{desired_version}' is not present in available_versions"
                )
                continue

            try:
                if action == "set-default":
                    gateway = client.get_gateway(gateway_id)
                    current_default = get_default_version(gateway)
                    current_downloaded = get_all_downloaded_versions(gateway)

                    if desired_version == current_default:
                        skipped_count += 1
                        print(
                            f"[SKIP] {label}: version '{desired_version}' is already the default"
                        )
                        continue

                    if desired_version not in current_downloaded:
                        failure_count += 1
                        print(
                            f"[FAIL] {label}: version '{desired_version}' is not downloaded on this gateway. "
                            f"Download it first, then run set-default."
                        )
                        continue

                    if dry_run:
                        success_count += 1
                        print(f"[DRY-RUN] would set default version '{desired_version}' for {label}")
                        continue

                    client.set_default_version(gateway_id=gateway_id, version=desired_version)
                    success_count += 1
                    print(f"[OK] {label}: set-default requested for version '{desired_version}'")
                    continue

                if action == "activate":
                    gateway = client.get_gateway(gateway_id)
                    current_default = get_default_version(gateway)

                    if current_default and desired_version != current_default:
                        print(
                            f"[WARN] {label}: version '{desired_version}' is not currently the default "
                            f"(current default: '{current_default}'). Activation will still be requested."
                        )

                    if dry_run:
                        success_count += 1
                        print(f"[DRY-RUN] would activate version '{desired_version}' for {label}")
                        continue

                    client.activate_version(gateway_id=gateway_id, version=desired_version)
                    success_count += 1
                    print(f"[OK] {label}: activate requested for version '{desired_version}'")
                    continue

                if dry_run:
                    success_count += 1
                    print(f"[DRY-RUN] would download version '{desired_version}' for {label}")
                    continue

                if action == "download":
                    client.download_version(gateway_id=gateway_id, version=desired_version)
                    success_count += 1
                    print(f"[OK] {label}: download requested for version '{desired_version}'")
                    continue

                raise ValueError(f"Unhandled action: {action}")

            except requests.RequestException as exc:
                failure_count += 1
                print(f"[FAIL] {label}: {action} request failed: {exc}")
            except Exception as exc:  # pragma: no cover
                failure_count += 1
                print(f"[FAIL] {label}: unexpected error: {exc}")

    print(
        f"Summary: action={action}, success={success_count}, failure={failure_count}, skipped={skipped_count}"
    )
    return 1 if failure_count else 0



def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate and process gateway version CSV templates using environment "
            "variables from the shell or a .env file. The script always reads and "
            "writes gateways.csv in the current working directory."
        )
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "generate-template",
        help="Generate gateways.csv from the API",
        description="Generate gateways.csv in the current working directory from the API.",
    )

    download_parser = subparsers.add_parser(
        "download",
        help="Read gateways.csv and download desired versions",
        description="Read gateways.csv in the current working directory and download desired versions.",
    )

    download_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate rows in gateways.csv and print actions without calling the API",
    )

    set_default_parser = subparsers.add_parser(
        "set-default",
        help="Read gateways.csv and set desired versions as default",
        description="Read gateways.csv in the current working directory and set desired versions as default.",
    )

    set_default_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate rows in gateways.csv and print actions without calling the API",
    )

    activate_parser = subparsers.add_parser(
        "activate",
        help="Read gateways.csv and activate desired versions",
        description="Read gateways.csv in the current working directory and activate desired versions.",
    )
    activate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate rows in gateways.csv and print actions without calling the API",
    )

    return parser



def validate_common_args(args: argparse.Namespace) -> Optional[int]:
    """Validate shared configuration before running a command."""
    required_env_vars = ["API_URL", "API_KEY"]
    missing = [name for name in required_env_vars if not os.getenv(name)]
    if missing:
        print(
            "Error: missing required environment variable(s): " + ", ".join(missing) +
            ". Set them in your shell or in a .env file.",
            file=sys.stderr,
        )
        return 2
    return None



def get_token(apiUrl: str, apiKey: str) -> str:
    token_url = f"{apiUrl}v3/api-key-auth/login"
    response = requests.post(token_url, json={"api_key": apiKey}, timeout=15)
    response.raise_for_status()
    return response.json()["result"]["delegate_token"]



def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    validation_exit_code = validate_common_args(args)
    if validation_exit_code is not None:
        return validation_exit_code
    
    apiKey = os.getenv("API_KEY")
    apiUrl = os.getenv("API_URL")
    token = get_token(apiUrl, apiKey)

    client = APIClient(
        apiUrl=apiUrl,
        token=token,
    )

    try:
        if args.command == "generate-template":
            return generate_template(client=client)
        if args.command == "download":
            return process_csv(client=client, csv_path="gateways.csv", action="download", dry_run=args.dry_run)
        if args.command == "set-default":
            return process_csv(client=client, csv_path="gateways.csv", action="set-default", dry_run=args.dry_run)
        if args.command == "activate":
            return process_csv(client=client, csv_path="gateways.csv", action="activate", dry_run=args.dry_run)
        parser.error(f"Unknown command: {args.command}")
        return 2
    except requests.RequestException as exc:
        print(f"API request failed: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"File error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
