import os
import sys
import unittest


CLIENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

from network_client import NetworkClient


class NetworkClientSyncTests(unittest.TestCase):
    def test_stale_snapshot_version_is_ignored(self):
        client = NetworkClient("ws://localhost:8765")
        client.state_version = 5
        client._full_state_cache = {"state_version": 5, "planets": [1]}

        client._apply_state_snapshot({"version": 4, "player": {"name": "Old"}})

        self.assertEqual(client.state_version, 5)

    def test_invalidate_world_state_cache_clears_all_caches(self):
        client = NetworkClient("ws://localhost:8765")
        client.market_prices_cache = {"Aether": {"ore": {"buy": 10, "sell": 8}}}
        client.planet_events = {"Aether": ["storm"]}
        client._full_state_cache = {"state_version": 2}
        client._full_state_cached_at = 10.0

        client._invalidate_world_state_cache()

        self.assertEqual(client.market_prices_cache, {})
        self.assertEqual(client.planet_events, {})
        self.assertEqual(client._full_state_cache, {})
        self.assertEqual(client._full_state_cached_at, 0.0)


if __name__ == "__main__":
    unittest.main()
