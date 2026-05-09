"""
skills/timer.py — Timer Skill
Set, cancel, and list timers. Multiple simultaneous timers supported.
"""

import threading
import logging
import time
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class TimerSkill:
    def __init__(self, config: dict, speak_callback: Callable):
        self.cfg = config
        self.speak = speak_callback
        self._timers: Dict[str, threading.Timer] = {}
        self._timer_count = 0

    def set_timer(self, duration_seconds: int, label: Optional[str] = None) -> str:
        """Set a timer for duration_seconds."""
        self._timer_count += 1
        timer_id = f"timer_{self._timer_count}"
        name = label or f"Timer {self._timer_count}"

        def _on_expire():
            self.speak(f"Time's up! Your {name} is done.")
            if timer_id in self._timers:
                del self._timers[timer_id]

        timer = threading.Timer(duration_seconds, _on_expire)
        timer.daemon = True
        timer.start()
        self._timers[timer_id] = timer

        # Format duration for response
        if duration_seconds < 60:
            duration_str = f"{duration_seconds} second{'s' if duration_seconds != 1 else ''}"
        elif duration_seconds < 3600:
            mins = duration_seconds // 60
            secs = duration_seconds % 60
            duration_str = f"{mins} minute{'s' if mins != 1 else ''}"
            if secs:
                duration_str += f" and {secs} seconds"
        else:
            hours = duration_seconds // 3600
            mins = (duration_seconds % 3600) // 60
            duration_str = f"{hours} hour{'s' if hours != 1 else ''}"
            if mins:
                duration_str += f" and {mins} minutes"

        logger.info(f"Timer set: {name} for {duration_str}")
        return f"Timer set for {duration_str}."

    def cancel_timer(self) -> str:
        """Cancel the most recent timer."""
        if not self._timers:
            return "You don't have any active timers."

        # Cancel the last timer
        timer_id = list(self._timers.keys())[-1]
        self._timers[timer_id].cancel()
        del self._timers[timer_id]
        return "Timer cancelled."

    def list_timers(self) -> str:
        """List active timers."""
        if not self._timers:
            return "No active timers."
        count = len(self._timers)
        return f"You have {count} active timer{'s' if count != 1 else ''}."

    def parse_duration(self, value: str, unit: str) -> int:
        """Convert value + unit to seconds."""
        val = int(value)
        unit = unit.lower()
        if unit in ("second", "sec", "s"):
            return val
        elif unit in ("minute", "min", "m"):
            return val * 60
        elif unit in ("hour", "hr", "h"):
            return val * 3600
        return val
