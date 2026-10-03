import copy
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("catalog", Path(__file__).with_name("validate_catalog.py"))
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class CatalogValidationTest(unittest.TestCase):
    def entries(self):
        return [dict(id=name, displayName=name, version="0.1.0-alpha.3",
                     type="github-release-assets", repositoryId="zalava-" + name,
                     repositoryUri="https://github.com/Zalava/zalava-module-" + name,
                     releaseTag="v0.1.0-alpha.3",
                     assetName=f"zalava-module-{name}-0.1.0-alpha.3.jar", sha256="a" * 64)
                for name in sorted(catalog.OFFICIAL)]

    def archive(self, *, service="META-INF/services/org.zalava.api.ZalavaModule", version="0.1.0-alpha.3", bundled=False, nested=False):
        stream = io.BytesIO()
        metadata = f"schemaVersion: 1\nmodules:\n  - moduleId: zalava-module-time\n    version: {version}\n"
        with zipfile.ZipFile(stream, "w") as jar:
            jar.writestr("module-metadata.yaml", metadata)
            jar.writestr("module.properties", "module.version=0.1.0-alpha.3")
            jar.writestr(service, "example.TimeModule")
            if bundled:
                jar.writestr("org/zalava/api/ZalavaModule.class", b"bundled SDK")
        payload = stream.getvalue()
        if nested:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as jar:
                jar.writestr("module-metadata.yaml", metadata)
                jar.writestr("module.jar", payload)
            payload = stream.getvalue()
        entry = next(item for item in self.entries() if item["id"] == "time")
        entry["sha256"] = hashlib.sha256(payload).hexdigest()
        return entry, payload

    def verify(self, entry, payload):
        with patch.object(catalog.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
            catalog.verify_downloads([entry])

    def test_download_retries_transient_failure_but_not_missing_release(self):
        url = "https://github.com/Zalava/fixture"
        gateway = catalog.urllib.error.HTTPError(url, 502, "gateway", {}, None)
        missing = catalog.urllib.error.HTTPError(url, 404, "missing", {}, None)
        with patch.object(catalog.time, "sleep"), patch.object(catalog.urllib.request, "urlopen", side_effect=[gateway, io.BytesIO(b"artifact")]) as request:
            self.assertEqual(catalog.download(url), b"artifact")
            self.assertEqual(request.call_count, 2)
        with patch.object(catalog.time, "sleep"), patch.object(catalog.urllib.request, "urlopen", side_effect=missing) as request:
            with self.assertRaises(catalog.urllib.error.HTTPError):
                catalog.download(url)
            self.assertEqual(request.call_count, 1)
        with patch.object(catalog.time, "sleep"), patch.object(catalog.urllib.request, "urlopen", side_effect=gateway) as request:
            with self.assertRaises(catalog.urllib.error.HTTPError):
                catalog.download(url)
            self.assertEqual(request.call_count, 3)

    def test_current_registration_and_nested_runtime_archive(self):
        for nested in (False, True):
            self.verify(*self.archive(nested=nested))

    def test_requires_every_official_module_once(self):
        for entries in (self.entries()[:-1], self.entries() + [self.entries()[0]]):
            with self.assertRaises(ValueError):
                catalog.validate(entries)
        catalog.validate(self.entries())

    def test_rejects_mismatched_tag_unsafe_source_and_digest(self):
        for field, value in (("releaseTag", "v0.1.0-alpha.30"),
                             ("repositoryUri", "https://example.com/artifact"),
                             ("sha256", "not-a-digest"), ("version", "0.1.0-SNAPSHOT")):
            entries = copy.deepcopy(self.entries())
            entries[0][field] = value
            with self.assertRaises(ValueError):
                catalog.validate(entries)

    def test_rejects_digest_tampering(self):
        entry, payload = self.archive()
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.verify(entry, payload + b"tamper")

    def test_rejects_legacy_spi_and_bundled_sdk(self):
        for options in ({"service": "META-INF/services/org.zalava.ZalavaModule"}, {"bundled": True}, {"bundled": True, "nested": True}):
            with self.assertRaises(ValueError):
                self.verify(*self.archive(**options))

    def test_metadata_version_comparison_is_exact(self):
        with self.assertRaises(ValueError):
            self.verify(*self.archive(version="0.1.0-alpha.30"))

    def test_parser_accepts_per_module_versions_and_rejects_truncation(self):
        content = "schemaVersion: 1\nmodules:\n"
        for entry in self.entries():
            content += f"  - id: {entry['id']}\n    displayName: {entry['displayName']}\n    version: {entry['version']}\n    artifact:\n"
            for field in ("type", "repositoryId", "repositoryUri", "releaseTag", "assetName", "sha256"):
                content += f"      {field}: {entry[field]}\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.yaml"
            path.write_text(content)
            with patch.object(catalog, "CATALOG", path):
                catalog.validate(catalog.parse())
                path.write_text(content.rsplit("\n", 2)[0] + "\n")
                with self.assertRaises(ValueError):
                    catalog.parse()


if __name__ == "__main__":
    unittest.main()
