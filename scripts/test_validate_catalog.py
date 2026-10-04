import copy
import unittest
import validate_catalog as catalog


class CatalogTest(unittest.TestCase):
    def test_current_locator(self):
        catalog.validate(catalog.parse())

    def test_rejects_release_inventory_and_source_mismatch(self):
        for key, value in (("version", "0.1.0-alpha.4"), ("artifact", {}),
                           ("repository", "https://github.com/other/source"),
                           ("releaseIndexPath", "../index.yaml")):
            document = copy.deepcopy(catalog.parse())
            document["modules"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                catalog.validate(document)

    def test_rejects_missing_and_duplicate_sources(self):
        document = catalog.parse()
        document["modules"].pop()
        with self.assertRaises(ValueError):
            catalog.validate(document)
        document = catalog.parse()
        document["modules"][1] = document["modules"][0]
        with self.assertRaises(ValueError):
            catalog.validate(document)


if __name__ == "__main__":
    unittest.main()
