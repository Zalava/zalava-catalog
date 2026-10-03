#!/usr/bin/env python3
"""Validate the version-1 Zalava release-asset catalog without dependencies."""

from __future__ import annotations

import hashlib
import io
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.yaml"
HEX = re.compile(r"[0-9a-f]{64}\Z")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-alpha\.\d+)?\Z")
OFFICIAL = frozenset(("brave-search", "channel-telegram", "docker", "filesystem", "home-assistant", "mcp-bridge", "playwright-browser", "shopping-list", "tasks", "tika", "time", "web-fetch"))
ASSET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}\.jar\Z")


def scalar(line: str, field: str) -> str:
    prefix = f"      {field}: "
    if not line.startswith(prefix):
        raise ValueError(f"expected {field}")
    return line.removeprefix(prefix).strip()


def parse() -> list[dict[str, str]]:
    lines = CATALOG.read_text(encoding="utf-8").splitlines()
    if lines[:2] != ["schemaVersion: 1", "modules:"]:
        raise ValueError("expected schemaVersion 1 and modules list")
    expected = ("type", "repositoryId", "repositoryUri", "releaseTag", "assetName", "sha256")
    entries: list[dict[str, str]] = []
    index = 2
    while index < len(lines):
        if index + 10 > len(lines):
            raise ValueError("incomplete module entry")
        if not lines[index].startswith("  - id: "):
            raise ValueError("expected module id")
        entry = {"id": lines[index].removeprefix("  - id: ").strip()}
        if index + 3 >= len(lines) or not lines[index + 1].startswith("    displayName: ") or not lines[index + 2].startswith("    version: ") or lines[index + 3] != "    artifact:":
            raise ValueError(f"invalid module entry {entry['id']}")
        entry["displayName"] = lines[index + 1].removeprefix("    displayName: ").strip()
        entry["version"] = lines[index + 2].removeprefix("    version: ").strip()
        for offset, field in enumerate(expected, start=4):
            entry[field] = scalar(lines[index + offset], field)
        entries.append(entry)
        index += 10
    return entries


def validate(entries: list[dict[str, str]]) -> None:
    ids = [entry["id"] for entry in entries]
    if len(entries) != len(OFFICIAL) or set(ids) != OFFICIAL:
        raise ValueError("catalog must contain each of the twelve official modules once")
    for entry in entries:
        if not VERSION.fullmatch(entry["version"]):
            raise ValueError(f"{entry['id']}: invalid immutable version")
        if entry["type"] != "github-release-assets":
            raise ValueError(f"{entry['id']}: unsupported artifact type")
        if entry["repositoryId"] != f"zalava-{entry['id']}":
            raise ValueError(f"{entry['id']}: repository id does not match module id")
        repository = f"https://github.com/Zalava/zalava-module-{entry['id']}"
        if entry["repositoryUri"] != repository or entry["releaseTag"] != "v" + entry["version"]:
            raise ValueError(f"{entry['id']}: invalid immutable repository or tag")
        expected_asset = f"zalava-module-{entry['id']}-{entry['version']}.jar"
        if entry["assetName"] != expected_asset or not ASSET.fullmatch(entry["assetName"]):
            raise ValueError(f"{entry['id']}: asset does not match module version")
        if not HEX.fullmatch(entry["sha256"]):
            raise ValueError(f"{entry['id']}: invalid SHA-256")


def download(url: str) -> bytes:
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except (OSError, urllib.error.URLError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code not in (502, 503, 504):
                raise
            if attempt == 3:
                raise
            print(f"release download retry {attempt}: {url}: {error}", file=sys.stderr)
            time.sleep(attempt)
    raise AssertionError("unreachable")


def verify_downloads(entries: list[dict[str, str]]) -> None:
    for entry in entries:
        url = f"{entry['repositoryUri']}/releases/download/{entry['releaseTag']}/{entry['assetName']}"
        payload = download(url)
        digest = hashlib.sha256(payload).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"{entry['id']}: digest mismatch ({digest})")
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as artifact:
                metadata = artifact.read("module-metadata.yaml").decode("utf-8")
                if any(name.startswith("org/zalava/api/") and name.endswith(".class") for name in artifact.namelist()):
                    raise ValueError(f"{entry['id']}: module bundles the host SDK")
                try:
                    version = artifact.read("module.properties").decode("utf-8").strip()
                    service = artifact.read(
                        "META-INF/services/org.zalava.api.ZalavaModule"
                    ).decode("utf-8").strip()
                except KeyError:
                    with zipfile.ZipFile(io.BytesIO(artifact.read("module.jar"))) as module:
                        if any(name.startswith("org/zalava/api/") and name.endswith(".class") for name in module.namelist()):
                            raise ValueError(f"{entry['id']}: module bundles the host SDK")
                        version = module.read("module.properties").decode("utf-8").strip()
                        service = module.read(
                            "META-INF/services/org.zalava.api.ZalavaModule"
                        ).decode("utf-8").strip()
        except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as error:
            raise ValueError(f"{entry['id']}: missing valid module descriptor") from error
        expected_properties = (
            version == f"module.version={entry['version']}"
            or (
                f"moduleId=zalava-module-{entry['id']}" in version.splitlines()
                and f"version={entry['version']}" in version.splitlines()
            )
        )
        if not expected_properties or re.findall(r"^  - moduleId: (.+)$", metadata, re.MULTILINE) != ["zalava-module-" + entry["id"]]:
            raise ValueError(f"{entry['id']}: module identity or version mismatch")
        if re.findall(r"^    version: (.+)$", metadata, re.MULTILINE) != [entry["version"]] or not service:
            raise ValueError(f"{entry['id']}: incomplete module metadata or service registration")
        print(f"verified {entry['id']} {digest}")


def main() -> int:
    try:
        entries = parse()
        validate(entries)
        verify_downloads(entries)
    except (OSError, ValueError) as error:
        print(f"catalog validation failed: {error}", file=sys.stderr)
        return 1
    print(f"validated {len(entries)} immutable GitHub Release assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
