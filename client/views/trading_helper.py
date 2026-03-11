"""
Trading system helper module for PlanetView.

Handles all market and trading-related logic including:
- Market item filtering and display
- Trade calculations and price lookups
- Contract management
- Banking and inventory operations
"""

from constants import *


class TradingManager:
    """Manages market and trading operations for a game view."""

    def __init__(self, view):
        """Initialize trading manager.
        
        Args:
            view: The parent PlanetView instance
        """
        self.view = view
        self.visible_items_cache = []
        self.cache_time = 0
        self.market_scroll_index = 0
        self.selected_market_item = None

    def get_visible_market_items(self):
        """Get the list of items available in the current planet's market."""
        planet = self.view.network.current_planet
        planet_inventory = self.view.network.planet_inventories.get(planet.name, {})

        items_list = []
        for item_name, quantity in planet_inventory.items():
            if quantity > 0:
                price = planet.get_price(item_name)
                items_list.append((item_name, quantity, price))

        items_list.sort(key=lambda x: (x[2] is None, x[2] if x[2] else 0), reverse=True)
        self.visible_items_cache = items_list
        return items_list

    def is_item_buyable(self, item_name):
        """Check if player can afford to buy at least 1 unit of item."""
        planet = self.view.network.current_planet
        price = planet.get_price(item_name)
        if price is None:
            return False
        return self.view.network.player.credits >= price

    def get_market_row_colors(self, item_name, current_price, comparison_planet=None):
        """Get color coding for a market item row."""
        if current_price is None:
            return COLOR_TEXT_DIM, (40, 40, 40)

        if comparison_planet:
            comparison_price = comparison_planet.get_price(item_name)
            if comparison_price is not None:
                if current_price < comparison_price:
                    return (100, 255, 100), (20, 60, 20)  # Green (good buy)
                elif current_price > comparison_price:
                    return (255, 100, 100), (60, 20, 20)  # Red (expensive)

        if item_name in ("Water", "Organics", "Metals", "Machinery"):
            if current_price > 5000:
                return COLOR_ACCENT, (60, 20, 20)
            elif current_price < 2000:
                return COLOR_PRIMARY, (20, 40, 60)

        return COLOR_TEXT, (40, 40, 40)

    def format_trade_feedback(self, action, item_name, qty):
        """Format a trade action message."""
        if action == "buy":
            return f"PURCHASE {qty:,} {item_name.upper()}"
        elif action == "sell":
            return f"SELL {qty:,} {item_name.upper()}"
        elif action == "give":
            return f"GIVE {qty:,} {item_name.upper()}"
        return f"{action.upper()} {qty:,} {item_name.upper()}"

    def get_market_layout(self, item_count):
        """Determine layout parameters for market display."""
        row_height = 40
        list_start_y = SCREEN_HEIGHT - 250
        market_list_height = list_start_y - 102

        max_visible_rows = market_list_height // row_height
        max_visible_rows = max(1, max_visible_rows - 1)

        if item_count <= max_visible_rows:
            return {
                "row_height": row_height,
                "start_y": list_start_y,
                "max_visible": max_visible_rows,
                "scroll_offset": 0,
            }

        scroll_offset = min(
            self.market_scroll_index, max(0, item_count - max_visible_rows)
        )
        return {
            "row_height": row_height,
            "start_y": list_start_y,
            "max_visible": max_visible_rows,
            "scroll_offset": scroll_offset,
        }

    def visible_rows_count(self):
        """Get number of visible market rows in current viewport."""
        row_height = 40
        list_start_y = SCREEN_HEIGHT - 250
        market_list_height = list_start_y - 102
        return max(1, (market_list_height // row_height) - 1)

    def get_contract_panel_height(self):
        """Get the height of the trade contract panel."""
        return 124  # MARKET_CONTRACT_PANEL_HEIGHT

    def wrap_market_text(self, text, max_chars=72, max_lines=2):
        """Wrap market text for display."""
        import textwrap
        
        if len(text) <= max_chars:
            return text
        
        lines = textwrap.wrap(text, width=max_chars)
        return "\n".join(lines[:max_lines])

    def refresh_finance_cache(self, force=False):
        """Refresh cached finance data from network."""
        if force:
            self.cache_time = 0
            self.view.network._refresh_account()

    def scroll_market_up(self):
        """Scroll market view up."""
        items = self.get_visible_market_items()
        if self.market_scroll_index > 0:
            self.market_scroll_index -= 1

    def scroll_market_down(self):
        """Scroll market view down."""
        items = self.get_visible_market_items()
        layout = self.get_market_layout(len(items))
        max_scroll = max(0, len(items) - layout["max_visible"])
        if self.market_scroll_index < max_scroll:
            self.market_scroll_index += 1

    def execute_trade(self, action, item_name, quantity):
        """Execute a trade action (buy, sell, give).
        
        Args:
            action: "buy", "sell", "give", or "transfer"
            item_name: Name of the item
            quantity: Number of units
            
        Returns:
            Tuple of (success, message)
        """
        if action == "buy":
            ok, msg = self.view.network.buy_item(item_name, quantity)
        elif action == "sell":
            ok, msg = self.view.network.sell_item(item_name, quantity)
        elif action == "give":
            ok, msg = self.view.network.give_cargo_to_planet(item_name, quantity)
        elif action == "transfer":
            ok, msg = self.view.network.transfer_to_bank(item_name, quantity)
        else:
            return False, f"UNKNOWN ACTION: {action}"

        return ok, msg

    def get_item_storage_info(self, item_name):
        """Get inventory and bank storage info for an item."""
        player = self.view.network.player
        inventory_qty = player.inventory.get(item_name, 0)
        bank_qty = player.bank_inventory.get(item_name, 0) if hasattr(player, 'bank_inventory') else 0
        return inventory_qty, bank_qty

    def can_afford_purchase(self, item_name, quantity):
        """Check if player can afford to buy quantity of item."""
        planet = self.view.network.current_planet
        price = planet.get_price(item_name)
        if price is None:
            return False
        total_cost = price * quantity
        return self.view.network.player.credits >= total_cost

    def calculate_transaction_total(self, item_name, quantity, action="buy"):
        """Calculate total cost/reward for a transaction."""
        planet = self.view.network.current_planet
        price = planet.get_price(item_name)
        if price is None:
            return 0
        
        if action == "buy":
            return price * quantity
        elif action == "sell":
            # Sell price is typically lower than buy price
            sell_price = max(1, int(price * 0.85))
            return sell_price * quantity
        
        return 0

    def get_available_contracts(self):
        """Get list of available trading contracts."""
        return self.view.network.get_contracts() or []

    def accept_contract(self, contract_id):
        """Accept a trading contract.
        
        Args:
            contract_id: ID of the contract to accept
            
        Returns:
            Tuple of (success, message)
        """
        ok, msg = self.view.network.accept_contract(contract_id)
        if ok:
            self.view.network.save_game()
        return ok, msg

    def complete_contract(self, contract_id):
        """Complete an accepted contract.
        
        Args:
            contract_id: ID of the contract to complete
            
        Returns:
            Tuple of (success, message, reward)
        """
        ok, msg, reward = self.view.network.complete_contract(contract_id)
        if ok:
            self.view.network.save_game()
        return ok, msg, reward
