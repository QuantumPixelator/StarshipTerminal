import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import planets


class TestPlanetCatalogLineEndings(unittest.TestCase):
    def test_generate_planets_parses_crlf_separated_blocks(self):
        catalog_text = (
            "Name: Alpha\r\n"
            "Population: 1000000\r\n"
            "Description: Alpha world\r\n"
            "Vendor: A\r\n"
            "Trade Center: A Hub\r\n"
            "Defenders: 1000\r\n"
            "Shields: 2000\r\n"
            "Bank: Off\r\n"
            "Items: Fuel Cells,80\r\n"
            "Active: On\r\n"
            "\r\n"
            "Name: Beta\r\n"
            "Population: 2000000\r\n"
            "Description: Beta world\r\n"
            "Vendor: B\r\n"
            "Trade Center: B Hub\r\n"
            "Defenders: 1500\r\n"
            "Shields: 2500\r\n"
            "Bank: Off\r\n"
            "Items: Fuel Cells,90\r\n"
            "Active: On\r\n"
        )

        original_reader = planets.read_default_catalog_text
        original_active_items = planets.active_item_names
        original_smuggle_loader = planets._load_smuggling_item_pool

        def fake_reader(file_name):
            if file_name == "planets.txt":
                return catalog_text
            if file_name == "smuggle_items.txt":
                return ""
            return ""

        try:
            planets.read_default_catalog_text = fake_reader
            planets.active_item_names = {"Fuel Cells"}
            planets._load_smuggling_item_pool = lambda: ([], {})

            loaded = planets.generate_planets()
            names = {p.name for p in loaded}

            self.assertEqual(len(loaded), 2)
            self.assertIn("Alpha", names)
            self.assertIn("Beta", names)
        finally:
            planets.read_default_catalog_text = original_reader
            planets.active_item_names = original_active_items
            planets._load_smuggling_item_pool = original_smuggle_loader


if __name__ == "__main__":
    unittest.main()
