"""
server/performance.py — Performance optimization utilities.

Provides:
- Calculation caching for expensive operations
- Performance profiling helpers
- Optimization tips and monitoring
"""

import time
import logging
from functools import wraps
from typing import Callable, Any, Dict, Tuple, Optional
from collections import OrderedDict


logger = logging.getLogger("game_server.performance")


class PerformanceCache:
    """LRU cache for performance-critical calculations."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of cached entries
            ttl_seconds: Time-to-live for cache entries
        """
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.cache = OrderedDict()

    def _make_key(self, *args, **kwargs) -> str:
        """Create a cache key from arguments."""
        import hashlib
        import json
        
        key_data = {
            "args": str(args),
            "kwargs": json.dumps(kwargs, default=str, sort_keys=True),
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, *args, **kwargs) -> Optional[Any]:
        """Get value from cache."""
        key = self._make_key(*args, **kwargs)
        
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return value
            else:
                del self.cache[key]
        
        return None

    def set(self, value: Any, *args, **kwargs):
        """Store value in cache."""
        key = self._make_key(*args, **kwargs)
        
        # Remove oldest entry if cache is full
        if len(self.cache) >= self.max_size and key not in self.cache:
            self.cache.popitem(last=False)
        
        self.cache[key] = (value, time.time())
        if key in self.cache:
            self.cache.move_to_end(key)

    def clear(self):
        """Clear the entire cache."""
        self.cache.clear()

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "ttl": self.ttl,
        }


# Global caches for common operations
validation_cache = PerformanceCache(max_size=500, ttl_seconds=600)
module_bonus_cache = PerformanceCache(max_size=1000, ttl_seconds=300)
ship_effectiveness_cache = PerformanceCache(max_size=500, ttl_seconds=300)


def cache_result(cache_obj: PerformanceCache) -> Callable:
    """Decorator to cache function results."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to get from cache
            result = cache_obj.get(*args, **kwargs)
            if result is not None:
                return result
            
            # Calculate and cache result
            result = func(*args, **kwargs)
            cache_obj.set(result, *args, **kwargs)
            return result
        
        return wrapper
    return decorator


class PerformanceProfiler:
    """Simple performance profiler for identifying bottlenecks."""

    def __init__(self):
        self.timings = {}

    def start(self, operation_name: str):
        """Start timing an operation."""
        self.timings[operation_name] = {
            "start": time.perf_counter(),
            "count": 0,
            "total": 0.0,
        }

    def end(self, operation_name: str):
        """End timing an operation."""
        if operation_name not in self.timings:
            return
        
        elapsed = time.perf_counter() - self.timings[operation_name]["start"]
        self.timings[operation_name]["count"] += 1
        self.timings[operation_name]["total"] += elapsed

    def get_stats(self, operation_name: str) -> Dict[str, float]:
        """Get statistics for an operation."""
        if operation_name not in self.timings:
            return {}
        
        timing = self.timings[operation_name]
        count = timing["count"]
        
        if count == 0:
            return {"count": 0, "total": 0, "average": 0, "min": 0, "max": 0}
        
        return {
            "count": count,
            "total": timing["total"],
            "average": timing["total"] / count,
            "min": timing.get("min", 0),
            "max": timing.get("max", 0),
        }

    def reset(self):
        """Reset all timings."""
        self.timings.clear()

    def report(self):
        """Log a performance report."""
        logger.info("=== Performance Report ===")
        for op_name in sorted(self.timings.keys()):
            stats = self.get_stats(op_name)
            if stats["count"] > 0:
                logger.info(
                    f"{op_name}: {stats['count']} calls, "
                    f"{stats['total']:.3f}s total, "
                    f"{stats['average']*1000:.2f}ms avg"
                )


# Global profiler instance
profiler = PerformanceProfiler()


def profile_operation(operation_name: str) -> Callable:
    """Decorator to profile function execution time."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            profiler.start(operation_name)
            try:
                return func(*args, **kwargs)
            finally:
                profiler.end(operation_name)
        
        return wrapper
    return decorator


class OptimizationTips:
    """Best practices for performance optimization."""

    @staticmethod
    def get_tips_for_modules():
        """Tips for optimizing module operations."""
        return [
            "Cache module bonus calculations when possible",
            "Use set operations for module validation instead of loops",
            "Pre-compute role-based bonuses at ship creation",
            "Batch module availability checks where possible",
        ]

    @staticmethod
    def get_tips_for_combat():
        """Tips for optimizing combat operations."""
        return [
            "Cache damage multiplier calculations",
            "Use lookup tables for role-based combat modifiers",
            "Limit special weapon effect calculations to used weapons only",
            "Batch ship status updates instead of individual calculations",
        ]

    @staticmethod
    def get_tips_for_validation():
        """Tips for optimizing validation operations."""
        return [
            "Use validation cache for duplicate checks",
            "Index player names for O(1) lookup instead of O(n)",
            "Batch validate multiple inputs together",
            "Cache validation rules that don't change per-session",
        ]

    @staticmethod
    def get_tips_for_persistence():
        """Tips for optimizing save/load operations."""
        return [
            "Compress character saves before storage",
            "Use incremental saves for frequently-changed data",
            "Batch write operations to minimize disk I/O",
            "Archive old saves to separate storage",
        ]

    @staticmethod
    def log_all_tips():
        """Log all optimization tips."""
        logger.info("=== Modules ===")
        for tip in OptimizationTips.get_tips_for_modules():
            logger.info(f"- {tip}")
        
        logger.info("=== Combat ===")
        for tip in OptimizationTips.get_tips_for_combat():
            logger.info(f"- {tip}")
        
        logger.info("=== Validation ===")
        for tip in OptimizationTips.get_tips_for_validation():
            logger.info(f"- {tip}")
        
        logger.info("=== Persistence ===")
        for tip in OptimizationTips.get_tips_for_persistence():
            logger.info(f"- {tip}")
