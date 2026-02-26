"""
Travel computation helpers for Starship Terminal client.
Provides fuel cost, warp duration, and speed multiplier calculations
that are shared between PlanetView, TravelView, and WarpView.
"""


def _get_arrival_pause_seconds(network, default_value=0.0, refresh_config=False):
    """Return the configured arrival pause duration in seconds."""
    if refresh_config and hasattr(network, "_refresh_config"):
        try:
            network._refresh_config()
        except Exception:
            pass

    try:
        value = float(network.config.get("planet_arrival_pause_seconds"))
    except Exception:
        value = float(default_value)

    return max(0.0, value)


def _get_fuel_usage_multiplier(network):
    """Return the global fuel usage multiplier from server config (default 1.15)."""
    try:
        value = float(network.config.get("fuel_usage_multiplier", 1.15))
    except Exception:
        value = 1.15
    # Global balance adjustment: -10% fuel usage across the board.
    return max(0.0, value * 0.90)


def _calculate_travel_fuel_cost(network, distance):
    """
    Compute the fuel cost for travelling *distance* units.

    Applies:
    - Ship burn rate (with engineer bonus reduction)
    - Global fuel_usage_multiplier (+15% by default)
    - Rounds to nearest integer, minimum 1 if any fuel is used
    """
    ship = network.player.spaceship
    burn_rate = (
        ship.get_effective_fuel_burn_rate()
        if hasattr(ship, "get_effective_fuel_burn_rate")
        else ship.fuel_burn_rate
    )
    fuel_cost = (float(distance) / 10.0) * float(burn_rate)

    crew = getattr(network.player, "crew", {}) or {}
    engineer = crew.get("engineer") if isinstance(crew, dict) else None
    if engineer is not None and hasattr(engineer, "get_bonus"):
        engineer_bonus = max(0.0, min(0.95, float(engineer.get_bonus())))
        fuel_cost *= 1.0 - engineer_bonus

    scaled = max(0.0, fuel_cost) * _get_fuel_usage_multiplier(network)
    rounded = float(int(round(scaled)))
    if scaled > 0.0:
        rounded = max(1.0, rounded)
    return rounded


def _get_warp_travel_duration_seconds(
    network,
    distance,
    default_value=3.0,
    refresh_config=False,
):
    """
    Calculate the visual warp travel duration for a given distance.

    Scales linearly from the configured base duration relative to
    travel_time_reference_distance, then clamps to [min, max].
    """
    base_seconds = _get_arrival_pause_seconds(
        network, default_value=default_value, refresh_config=refresh_config
    )
    try:
        reference_distance = float(network.config.get("travel_time_reference_distance", 300.0))
    except Exception:
        reference_distance = 300.0
    reference_distance = max(1.0, reference_distance)

    distance_factor = max(0.1, float(distance) / reference_distance)
    travel_seconds = base_seconds * distance_factor

    try:
        min_seconds = float(
            network.config.get("travel_time_min_seconds", max(0.8, base_seconds * 0.35))
        )
    except Exception:
        min_seconds = max(0.8, base_seconds * 0.35)

    try:
        max_seconds = float(
            network.config.get("travel_time_max_seconds", max(min_seconds, base_seconds * 4.0))
        )
    except Exception:
        max_seconds = max(min_seconds, base_seconds * 4.0)

    max_seconds = max(min_seconds, max_seconds)
    return max(min_seconds, min(max_seconds, travel_seconds))
