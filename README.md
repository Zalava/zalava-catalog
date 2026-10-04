# Zalava module catalog

This public catalog locates stable module source repositories and their
`releases/index.yaml` paths. It contains no module versions, release tags,
artifact names or digests. A module release never requires a catalog update.

The host resolves the module-owned index at an immutable Git commit and obtains
versions, artifacts, checksums, license, compatibility and permissions there.
Preparation pins that evidence; the administrator explicitly approves installation.
Module repositories own release-index validation and publication.

`catalog.yaml` uses JSON syntax, a valid YAML subset accepted by the host loader.
Run `python scripts/validate_catalog.py` and
`python -m unittest discover -s scripts` for deterministic locator checks.
Run `python scripts/validate_catalog.py --verify-sources` after module index PRs
merge to check the actual public default-branch source locations. Missing indexes
fail that check; they are never treated as successful discovery.
