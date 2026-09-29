# Zalava official module catalog

This repository is the auditable catalog of official, installable Zalava module
artifacts. It deliberately records immutable GitHub Release assets rather than
branch or package coordinates.

`catalog.yaml` is schema version 1. Every module entry contains its stable
module identifier, release version, and an `artifact` value with:

- `type`: currently `github-release-assets` only;
- `repositoryId` and canonical GitHub `repositoryUri`;
- immutable `releaseTag` and exact release `assetName`; and
- the lowercase SHA-256 digest of that asset.

Validate structure and the release assets before accepting catalog changes:

```sh
python3 scripts/validate_catalog.py
```

The validator uses only the Python standard library. It rejects unexpected
schema values and downloads each declared immutable release asset over HTTPS to
verify its digest. A successful result is catalog-source evidence; it is not
evidence of real-host installation or browser acceptance.
