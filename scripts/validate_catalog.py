#!/usr/bin/env python3
"""Validate the version-1 Zalava release-asset catalog without dependencies."""

from __future__ import annotations

import hashlib
import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.yaml"
HEX = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}\Z")
TAG = re.compile(r"v[0-9][A-Za-z0-9._-]{0,127}\Z")
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
        if not lines[index].startswith("  - id: "):
            raise ValueError("expected module id")
        entry = {"id": lines[index].removeprefix("  - id: ").strip()}
        if index + 3 >= len(lines) or not lines[index + 1].startswith("    displayName: ") or lines[index + 2] != "    version: 0.1.0-alpha.2" or lines[index + 3] != "    artifact:":
            raise ValueError(f"invalid module entry {entry['id']}")
        entry["displayName"] = lines[index + 1].removeprefix("    displayName: ").strip()
        entry["version"] = "0.1.0-alpha.2"
        for offset, field in enumerate(expected, start=4):
            entry[field] = scalar(lines[index + offset], field)
        entries.append(entry)
        index += 10
    return entries


def validate(entries: list[dict[str, str]]) -> None:
    ids = [entry["id"] for entry in entries]
    if len(entries) != 11 or len(ids) != len(set(ids)) or any(not ID.fullmatch(value) for value in ids):
        raise ValueError("catalog must contain eleven unique safe module ids")
    for entry in entries:
        if entry["type"] != "github-release-assets":
            raise ValueError(f"{entry['id']}: unsupported artifact type")
        if entry["repositoryId"] != f"zalava-{entry['id']}":
            raise ValueError(f"{entry['id']}: repository id does not match module id")
        repository = f"https://github.com/Zalava/zalava-module-{entry['id']}"
        if entry["repositoryUri"] != repository or not TAG.fullmatch(entry["releaseTag"]):
            raise ValueError(f"{entry['id']}: invalid immutable repository or tag")
        expected_asset = f"zalava-module-{entry['id']}-{entry['version']}.jar"
        if entry["assetName"] != expected_asset or not ASSET.fullmatch(entry["assetName"]):
            raise ValueError(f"{entry['id']}: asset does not match module version")
        if not HEX.fullmatch(entry["sha256"]):
            raise ValueError(f"{entry['id']}: invalid SHA-256")


def verify_downloads(entries: list[dict[str, str]]) -> None:
    for entry in entries:
        url = f"{entry['repositoryUri']}/releases/download/{entry['releaseTag']}/{entry['assetName']}"
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"{entry['id']}: digest mismatch ({digest})")
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as artifact:
                metadata = artifact.read("module-metadata.yaml").decode("utf-8")
                try:
                    version = artifact.read("module.properties").decode("utf-8").strip()
                    service = artifact.read(
                        "META-INF/services/org.zalava.ZalavaModule"
                    ).decode("utf-8").strip()
                except KeyError:
                    with zipfile.ZipFile(io.BytesIO(artifact.read("module.jar"))) as module:
                        version = module.read("module.properties").decode("utf-8").strip()
                        service = module.read(
                            "META-INF/services/org.zalava.ZalavaModule"
                        ).decode("utf-8").strip()
        except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as error:
            raise ValueError(f"{entry['id']}: missing valid module descriptor") from error
        expected_module_id = f"moduleId: zalava-module-{entry['id']}"
        expected_properties = (
            version == f"module.version={entry['version']}"
            or (
                f"moduleId=zalava-module-{entry['id']}" in version
                and f"version={entry['version']}" in version
            )
        )
        if not expected_properties or expected_module_id not in metadata:
            raise ValueError(f"{entry['id']}: module identity or version mismatch")
        if f"version: {entry['version']}" not in metadata or not service:
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
