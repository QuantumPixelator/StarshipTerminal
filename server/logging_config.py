"""
server/logging_config.py — Centralized logging configuration for Starship Terminal game server.

Provides structured logging for:
- Module installations and bonuses
- Special weapon usage and cooldowns
- Server-side validation (duplicate checks, etc.)
- Combat events
- Game state changes
- Error tracking and recovery
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


class GameServerFormatter(logging.Formatter):
    """Custom formatter for game server logs with type-specific coloring."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m",  # Red background
        "RESET": "\033[0m",
    }

    def format(self, record):
        if sys.stdout.isatty():  # Only use colors if output is a terminal
            levelname = record.levelname
            color = self.COLORS.get(levelname, "")
            reset = self.COLORS["RESET"]
            record.levelname = f"{color}{levelname}{reset}"

        return super().format(record)


def setup_server_logging(
    log_file="server.log", log_level=logging.INFO, enable_console=True
):
    """
    Configure logging for the game server.

    Args:
        log_file: Path to log file (relative to server root)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_console: Whether to log to console in addition to file
    """
    # Create logger
    logger = logging.getLogger("game_server")
    logger.setLevel(log_level)

    # Format string: timestamp - logger name - level - message
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = GameServerFormatter(log_format)

    # File handler
    log_path = Path(__file__).parent / log_file
    try:
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create log file {log_path}: {e}")

    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


# Create module instances for different subsystems
def get_module_logger(module_name):
    """Get a logger for a specific game subsystem."""
    return logging.getLogger(f"game_server.{module_name}")


# Specialized loggers for different systems
def get_validation_logger():
    """Get logger for validation events (account/character creation, duplicate checks)."""
    return get_module_logger("validation")


def get_combat_logger():
    """Get logger for combat events and special weapon usage."""
    return get_module_logger("combat")


def get_module_logger_subsystem():
    """Get logger for module installation and bonus calculations."""
    return get_module_logger("modules")


def get_session_logger():
    """Get logger for session/connection events."""
    return get_module_logger("session")


def get_persistence_logger():
    """Get logger for save/load operations."""
    return get_module_logger("persistence")


def log_validation_error(error_type, details, player_name=None):
    """
    Log a validation error with structured information.

    Args:
        error_type: Type of validation error (e.g., "duplicate_name", "invalid_module")
        details: Error details dictionary
        player_name: Optional player name for context
    """
    logger = get_validation_logger()
    context = f"[{player_name}] " if player_name else ""
    logger.error(
        f"{context}Validation error: {error_type} - {details}",
        extra={"error_type": error_type, "details": details},
    )


def log_module_installation(player_name, ship_model, modules, success):
    """Log module installation events."""
    logger = get_module_logger_subsystem()
    status = "SUCCESS" if success else "FAILED"
    logger.info(
        f"[{player_name}] Module installation {status}: ship={ship_model}, modules={modules}"
    )


def log_special_weapon_usage(player_name, weapon_type, success, result=None):
    """Log special weapon usage events."""
    logger = get_combat_logger()
    status = "SUCCESS" if success else "FAILED"
    logger.info(
        f"[{player_name}] Special weapon {status}: weapon={weapon_type}, result={result}"
    )


def log_cooldown_check(player_name, feature, cooldown_remaining):
    """Log cooldown checks for features with cooldowns."""
    logger = get_combat_logger()
    if cooldown_remaining > 0:
        logger.debug(
            f"[{player_name}] {feature} on cooldown: {cooldown_remaining:.1f}s remaining"
        )
    else:
        logger.debug(f"[{player_name}] {feature} ready to use")


def log_session_event(player_name, event_type, details=None):
    """Log session-related events."""
    logger = get_session_logger()
    detail_str = f" - {details}" if details else ""
    logger.info(f"[{player_name}] Session event: {event_type}{detail_str}")


def log_persistence_error(operation, file_path, error):
    """Log save/load operation errors."""
    logger = get_persistence_logger()
    logger.error(f"Persistence error: {operation} {file_path} - {error}")


# Handler decorator for improved error handling
def handle_errors(error_message_template="Operation failed", log_level=logging.ERROR):
    """
    Decorator for error handling in game handlers.

    Usage:
        @handle_errors("Failed to install module")
        def _h_install_module(server, session, gm, params):
            ...
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger = get_module_logger("handlers")
                logger.log(
                    log_level,
                    f"{error_message_template}: {func.__name__} - {str(e)}",
                    exc_info=True,
                )
                # Return a safe error response
                return {
                    "success": False,
                    "message": error_message_template,
                    "error": str(e),
                }

        return wrapper

    return decorator
