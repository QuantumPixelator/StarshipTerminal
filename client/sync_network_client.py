"""
Synchronous wrapper for NetworkClient to work with Arcade views.
Arcade is not async-aware, so we need to run async operations in a way Arcade can handle.
"""

import asyncio
import threading
from network_client import NetworkClient


class SyncNetworkClient:
    """
    Synchronous wrapper for NetworkClient that works with Arcade.

    This runs the async network client in a background thread and provides
    synchronous methods that Arcade views can call directly.
    """

    def __init__(self, server_url: str = "ws://localhost:8765"):
        self.network = NetworkClient(server_url)
        self.loop = None
        self.thread = None
        self._connected = False

    def start(self):
        """Start the async event loop in a background thread."""

        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()

        # Wait for loop to be ready
        while self.loop is None:
            pass

    def _run_async(self, coro):
        """Run an async coroutine and wait for result."""
        if not self.loop:
            self.start()

        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=10)  # 10 second timeout

    def connect(self, player_name: str) -> bool:
        """Connect to server synchronously."""
        try:
            result = self._run_async(self.network.connect(player_name))
            self._connected = result
            return result
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    @property
    def connected(self):
        return self._connected

    @property
    def player(self):
        return self.network.player

    @property
    def current_planet(self):
        return self.network.current_planet

    @property
    def known_planets(self):
        return self.network.known_planets

    # Generate synchronous wrappers for all NetworkClient methods
    def __getattr__(self, name):
        """
        Dynamically wrap async methods to be synchronous.
        If the NetworkClient has an async method, this makes it callable synchronously.
        """
        attr = getattr(self.network, name)

        if asyncio.iscoroutinefunction(attr):

            def sync_wrapper(*args, **kwargs):
                result = self._run_async(attr(*args, **kwargs))
                if name == "start_combat_session" and isinstance(result, dict):
                    if "status" in result:
                        return (True, "Combat window initialized.", result)
                    return (
                        result.get("success", False),
                        str(result.get("message", "")),
                        result.get("session", {}),
                    )
                return result

            return sync_wrapper
        else:
            return attr

    def close(self):
        """Close connection and stop loop."""
        if self._connected:
            try:
                self._run_async(self.network.close())
            except:
                pass

        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

        self._connected = False
