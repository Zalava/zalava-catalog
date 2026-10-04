#!/usr/bin/env python3
"""Validate stable source locators; releases remain module-owned."""
import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.yaml"
OFFICIAL = frozenset(("brave-search", "channel-telegram", "docker", "filesystem", "home-assistant", "mcp-bridge", "playwright-browser", "shopping-list", "tasks", "tika", "time", "web-fetch"))


def parse():
    return json.loads(CATALOG.read_text())


def validate(document):
    if set(document) != {"schemaVersion", "repository", "modules"} or document["schemaVersion"] != 1:
        raise ValueError("invalid locator schema")
    if document["repository"] != {"type": "module-locator", "indexRepository": "https://github.com/Zalava/zalava-catalog", "indexPath": "catalog.yaml"}:
        raise ValueError("catalog must identify its stable locator repository")
    modules = document["modules"]
    expected_ids = {"zalava-module-" + module for module in OFFICIAL}
    if len(modules) != len(expected_ids) or {m["moduleId"] for m in modules} != expected_ids:
        raise ValueError("each official module must occur once")
    for module in modules:
        if set(module) != {"moduleId", "displayName", "description", "repository", "releaseIndexPath"}:
            raise ValueError("locator must not contain release versions or artifacts")
        if module["repository"] != "https://github.com/Zalava/" + module["moduleId"]:
            raise ValueError("module source identity mismatch")
        if module["releaseIndexPath"] != "releases/index.yaml":
            raise ValueError("official modules must own releases/index.yaml")
        if any(not isinstance(module[key], str) or not module[key].strip() for key in module):
            raise ValueError("locator fields must be non-empty strings")


def verify_sources(document):
    for module in document["modules"]:
        repository = module["repository"].removeprefix("https://github.com/")
        url = f'https://raw.githubusercontent.com/{repository}/main/{module["releaseIndexPath"]}'
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read(256 * 1024 + 1)
        if len(payload) > 256 * 1024:
            raise ValueError("release index exceeds host metadata size limit")
        index = json.loads(payload)
        if index["schemaVersion"] != 1 or index["moduleId"] != module["moduleId"] or not index["releases"]:
            raise ValueError("module-owned index identity mismatch")
        print("verified source " + module["moduleId"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-sources", action="store_true")
    args = parser.parse_args()
    try:
        document = parse()
        validate(document)
        if args.verify_sources:
            verify_sources(document)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"catalog validation failed: {error}")
        return 1
    print(f'validated {len(document["modules"])} stable source locators')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
