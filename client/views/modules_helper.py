"""
Ship modules and upgrades helper module for PlanetView.

Handles all ship-related module and upgrade logic including:
- Module installation and management
- Ship configuration and customization
- Upgrade tracking and validation
"""

from constants import *


class ModuleManager:
    """Manages ship modules and upgrades for a game view."""

    def __init__(self, view):
        """Initialize module manager.
        
        Args:
            view: The parent PlanetView instance
        """
        self.view = view
        self.selected_ship_index = 0
        self.module_installation_status = {}

    def get_player_ships(self):
        """Get list of player's ships."""
        return self.view.network.player.ships

    def get_current_ship(self):
        """Get the currently active ship."""
        return self.view.network.player.spaceship

    def install_module(self, module_name, slot_index=None):
        """Install a module on the current ship.
        
        Args:
            module_name: Name of module to install
            slot_index: Optional slot index (auto-selects if None)
            
        Returns:
            Tuple of (success, message)
        """
        ship = self.get_current_ship()
        if not ship:
            return False, "NO ACTIVE SHIP"

        ok, msg = self.view.network.install_ship_upgrade(module_name)
        if ok:
            self.view.network.save_game()
        return ok, msg

    def uninstall_module(self, slot_index):
        """Uninstall a module from a specific slot.
        
        Args:
            slot_index: Index of the slot to uninstall from
            
        Returns:
            Tuple of (success, message)
        """
        ship = self.get_current_ship()
        if not ship:
            return False, "NO ACTIVE SHIP"

        if slot_index < 0 or slot_index >= len(ship.upgrades):
            return False, "INVALID SLOT"

        module = ship.upgrades[slot_index] if slot_index < len(ship.upgrades) else None
        if not module:
            return False, "NO MODULE IN SLOT"

        ok, msg = self.view.network.uninstall_ship_upgrade(slot_index)
        if ok:
            self.view.network.save_game()
        return ok, msg

    def get_available_modules(self):
        """Get list of modules player can install.
        
        Returns:
            List of (module_name, type, bonus_info) tuples
        """
        modules = []
        
        # Define available modules with their bonuses
        module_info = {
            "scanner": {
                "type": "sensor",
                "bonus": "+10% scanning range",
                "description": "Extends planetary scanning capabilities"
            },
            "jammer": {
                "type": "defense",
                "bonus": "+12% evasion",
                "description": "Reduces detection and targeting probability"
            },
            "cargo_optimizer": {
                "type": "cargo",
                "bonus": "+12% capacity, -3.5% fuel burn",
                "description": "Optimizes cargo space and fuel efficiency"
            }
        }
        
        for module_name, info in module_info.items():
            modules.append((module_name, info["type"], info["bonus"]))
        
        return modules

    def get_module_info(self, module_name):
        """Get detailed information about a module.
        
        Args:
            module_name: Name of the module
            
        Returns:
            Dictionary with module info or None
        """
        module_info = {
            "scanner": {
                "name": "Scanner Module",
                "type": "Sensor",
                "bonus": "+10% scanning range",
                "power_consumption": "Low",
                "weight": "Light",
                "description": "Extends your planetary scanning capabilities, allowing you to scan targets from greater distances.",
                "effectiveness": {
                    "Hauler": "Moderate",
                    "Interceptor": "High",
                    "Siege": "Low",
                    "Runner": "High"
                }
            },
            "jammer": {
                "name": "Jammer Module",
                "type": "Defense",
                "bonus": "+12% evasion",
                "power_consumption": "Medium",
                "weight": "Medium",
                "description": "Reduces your detection and targeting probability, making you harder to hit in combat.",
                "effectiveness": {
                    "Hauler": "Low",
                    "Interceptor": "High",
                    "Siege": "Moderate",
                    "Runner": "High"
                }
            },
            "cargo_optimizer": {
                "name": "Cargo Optimizer",
                "type": "Cargo",
                "bonus": "+12% capacity, -3.5% fuel burn",
                "power_consumption": "Very Low",
                "weight": "Very Light",
                "description": "Optimizes your cargo routing and fuel efficiency, allowing you to carry more and travel further.",
                "effectiveness": {
                    "Hauler": "High",
                    "Interceptor": "Moderate",
                    "Siege": "Low",
                    "Runner": "High"
                }
            }
        }
        
        return module_info.get(module_name)

    def get_ship_slot_capacity(self):
        """Get number of module slots for current ship.
        
        Module slots are determined by ship cost:
        - < 12K: 1 slot
        - 12K-200K: 2 slots
        - 200K-1.2M: 3 slots
        - >= 1.2M: 4 slots
        """
        ship = self.get_current_ship()
        if not ship:
            return 0
        
        cost = ship.cost
        if cost < 12000:
            return 1
        elif cost < 200000:
            return 2
        elif cost < 1200000:
            return 3
        else:
            return 4

    def get_installed_modules(self):
        """Get list of currently installed modules."""
        ship = self.get_current_ship()
        if not ship:
            return []
        
        modules = []
        for slot_index, module in enumerate(ship.upgrades or []):
            if isinstance(module, dict) and "name" in module:
                modules.append({
                    "slot": slot_index,
                    "name": module.get("name"),
                    "bonus": module.get("bonus")
                })
        
        return modules

    def get_module_bonuses(self):
        """Calculate total bonuses from installed modules."""
        ship = self.get_current_ship()
        if not ship:
            return {}
        
        bonuses = {
            "scanning": 0,
            "evasion": 0,
            "cargo_capacity": 0,
            "fuel_efficiency": 0
        }
        
        for module in ship.upgrades or []:
            if isinstance(module, dict):
                module_name = module.get("name", "").lower()
                if "scanner" in module_name:
                    bonuses["scanning"] += 10
                elif "jammer" in module_name:
                    bonuses["evasion"] += 12
                elif "cargo" in module_name or "optimizer" in module_name:
                    bonuses["cargo_capacity"] += 12
                    bonuses["fuel_efficiency"] -= 3.5
        
        return bonuses

    def auto_install_cargo_modules(self):
        """Automatically install recommended modules for cargo optimization."""
        ship = self.get_current_ship()
        if not ship:
            return False, "NO ACTIVE SHIP"
        
        # Get ship role
        role = self._determine_ship_role(ship)
        
        # Recommend modules based on role
        recommendations = {
            "Hauler": ["cargo_optimizer"],
            "Interceptor": ["scanner"],
            "Siege": ["jammer"],
            "Runner": ["jammer", "scanner"]
        }
        
        modules_to_install = recommendations.get(role, [])
        installed = []
        
        for module_name in modules_to_install:
            ok, msg = self.install_module(module_name)
            if ok:
                installed.append(module_name)
        
        if installed:
            return True, f"INSTALLED: {', '.join(installed)}"
        return False, "FAILED TO INSTALL MODULES"

    def _determine_ship_role(self, ship):
        """Determine ship role from its characteristics."""
        if not ship:
            return "Unknown"
        
        # Haulers: high cargo, low combat
        if ship.cargo > 100 and ship.firepower < 50:
            return "Hauler"
        # Interceptors: high speed, low cargo
        elif ship.speed > 15 and ship.cargo < 30:
            return "Interceptor"
        # Siege: high firepower, low speed
        elif ship.firepower > 50 and ship.speed < 10:
            return "Siege"
        # Runners: balanced with good speed
        elif ship.speed > 12 and ship.cargo > 40:
            return "Runner"
        
        return "General"

    def validate_module_compatibility(self, module_name):
        """Check if module is compatible with current ship.
        
        Args:
            module_name: Name of module to validate
            
        Returns:
            Tuple of (valid, reason)
        """
        ship = self.get_current_ship()
        if not ship:
            return False, "NO ACTIVE SHIP"
        
        # Check slot availability
        slots_available = self.get_ship_slot_capacity()
        slots_used = len([m for m in (ship.upgrades or []) if m])
        
        if slots_used >= slots_available:
            return False, f"NO AVAILABLE SLOTS ({slots_used}/{slots_available})"
        
        # Check for duplicate modules
        if ship.upgrades:
            for existing in ship.upgrades:
                if isinstance(existing, dict) and existing.get("name") == module_name:
                    return False, f"DUPLICATE MODULE: {module_name}"
        
        # Check if module exists
        module_info = self.get_module_info(module_name)
        if not module_info:
            return False, f"UNKNOWN MODULE: {module_name}"
        
        return True, "COMPATIBLE"

    def get_module_effectiveness(self, module_name):
        """Get effectiveness of a module for current ship.
        
        Args:
            module_name: Name of module
            
        Returns:
            Effectiveness rating (High, Moderate, Low)
        """
        ship = self.get_current_ship()
        if not ship:
            return "Unknown"
        
        role = self._determine_ship_role(ship)
        module_info = self.get_module_info(module_name)
        
        if not module_info:
            return "Unknown"
        
        effectiveness = module_info.get("effectiveness", {})
        return effectiveness.get(role, "Moderate")
