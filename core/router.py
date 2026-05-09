"""
core/router.py — Fixed Intent Router

Key fix: web_search patterns are now LAST and much more specific.
"can you guide me", "explain", "how do I", "tell me about" now
correctly fall through to the LLM instead of hitting web_search.

Rule: only route to web_search when the user explicitly says
"search", "look up", "google", or asks a clear factual question
with a short specific subject (not a conversational request).
"""

import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

INTENTS = [
    # ── Timers ──────────────────────────────────────────────
    ("timer_set", [
        r"set\s+(?:a\s+)?timer\s+(?:for\s+)?(\d+)\s*(second|minute|hour|sec|min|hr)s?",
        r"(?:timer|remind\s+me)\s+(?:in|after)\s+(\d+)\s*(second|minute|hour|sec|min|hr)s?",
        r"(\d+)\s*(second|minute|hour|sec|min|hr)s?\s+timer",
    ]),
    ("timer_cancel", [
        r"cancel\s+(?:the\s+)?timer",
        r"stop\s+(?:the\s+)?timer",
    ]),

    # ── Scheduler ───────────────────────────────────────────
    ("schedule_task", [
        r"remind\s+me\s+(?:in\s+\d|at\s+\d|tomorrow)",
        r"schedule\s+(?:a\s+)?(?:task|reminder|event)\s+",
        r"set\s+(?:a\s+)?reminder\s+(?:for|at|in)\s+",
        r"every\s+(?:morning|evening|night|noon|day)\s+at\s+",
        r"every\s+morning\b|every\s+evening\b|every\s+night\b",
    ]),
    ("schedule_list", [
        r"(?:list|show)\s+(?:my\s+)?(?:tasks|reminders|schedule)",
        r"what\s+(?:tasks|reminders)\s+(?:do\s+I\s+have|are\s+scheduled)",
        r"(?:any\s+)?(?:upcoming|pending)\s+(?:tasks|reminders)",
    ]),
    ("schedule_cancel", [
        r"cancel\s+all\s+(?:tasks|reminders)",
        r"delete\s+(?:all\s+)?(?:tasks|reminders)",
        r"cancel\s+(?:the\s+)?reminder\s+(?:for\s+)?(.+)",
    ]),

    # ── Weather ─────────────────────────────────────────────
    ("weather_current", [
        r"what(?:'s|\s+is)\s+(?:the\s+)?weather",
        r"how(?:'s|\s+is)\s+(?:the\s+)?weather",
        r"is\s+it\s+(?:raining|sunny|cloudy|cold|hot|warm)\s*(?:today|outside|right\s+now)?",
        r"(?:current\s+)?temperature\s+(?:today|outside|right\s+now)",
        r"weather\s+(?:today|right\s+now|currently)",
    ]),
    ("weather_forecast", [
        r"weather\s+(?:tomorrow|this\s+week|forecast|next\s+few\s+days)",
        r"will\s+it\s+rain\s+",
        r"(?:3|three|7|seven)[- ]day\s+forecast",
    ]),

    # ── Volume ──────────────────────────────────────────────
    ("volume_up",   [r"(?:turn\s+up|increase|raise)\s+(?:the\s+)?volume", r"\bvolume\s+up\b", r"\blouder\b"]),
    ("volume_down", [r"(?:turn\s+down|decrease|lower)\s+(?:the\s+)?volume", r"\bvolume\s+down\b", r"\bquieter\b"]),
    ("volume_set",  [r"set\s+(?:the\s+)?volume\s+(?:to\s+)?(\d+)\s*(?:percent|%)?", r"volume\s+(?:to\s+)?(\d+)\s*(?:percent|%)?"]),
    ("volume_mute", [r"\bmute\b|\bunmute\b|\bsilence\s+(?:the\s+)?(?:volume|audio|sound)?\b"]),

    # ── Brightness ──────────────────────────────────────────
    ("brightness_up",   [r"(?:increase|raise|turn\s+up)\s+(?:the\s+)?brightness", r"\bbrightness\s+up\b", r"\bbrighter\b"]),
    ("brightness_down", [r"(?:decrease|lower|turn\s+down)\s+(?:the\s+)?brightness", r"\bbrightness\s+down\b", r"\bdimmer\b"]),

    # ── Browser ─────────────────────────────────────────────
    ("open_browser", [
        r"open\s+(?:the\s+)?(?:browser|firefox|chrome|chromium|brave|web\s+browser)",
        r"launch\s+(?:the\s+)?(?:browser|firefox|chrome|web)",
        r"start\s+(?:firefox|chrome|chromium|brave)",
    ]),
    ("search_browser", [
        r"(?:search|google)\s+(?:in\s+(?:the\s+)?browser\s+)?(?:for\s+)?(.+)",
        r"open\s+browser\s+and\s+search\s+(?:for\s+)?(.+)",
        r"browse\s+(?:the\s+web\s+)?for\s+(.+)",
        r"search\s+(?:the\s+)?(?:web|internet|online)\s+for\s+(.+)",
    ]),
    ("open_youtube", [
        r"(?:open|go\s+to|launch)\s+youtube\b",
        r"(?:search|play|find)\s+on\s+youtube\s+(.+)",
        r"youtube\s+(.+)",
    ]),
    ("open_url", [
        r"(?:open|go\s+to|visit|navigate\s+to)\s+((?:https?://|www\.)\S+)",
        r"(?:open|go\s+to)\s+(\w+\.(?:com|org|net|io|co)\b\S*)",
    ]),

    # ── Apps ────────────────────────────────────────────────
    ("open_terminal", [r"(?:open|launch)\s+(?:the\s+)?(?:terminal|console|bash|shell|command\s+line)"]),
    ("open_files",    [r"(?:open|show|launch)\s+(?:the\s+)?(?:files|file\s+manager|my\s+files)\b"]),
    ("open_settings", [r"(?:open|launch|show)\s+(?:the\s+)?(?:system\s+)?settings\b"]),
    ("open_app", [
        r"(?:open|launch|start|run)\s+(?:the\s+)?([a-zA-Z][\w\s\-\.]{1,30})(?:\s+app(?:lication)?)?\s*$",
    ]),

    # ── Screenshot ──────────────────────────────────────────
    ("screenshot_region", [r"(?:region|area|partial|selection)\s+screenshot", r"screenshot\s+(?:a\s+)?(?:region|area|part)"]),
    ("screenshot",        [r"\bscreenshot\b", r"capture\s+(?:the\s+)?screen", r"take\s+(?:a\s+)?screenshot"]),

    # ── Clipboard ───────────────────────────────────────────
    ("clipboard_copy", [r"copy\s+(?:to\s+clipboard\s+)?[\"'](.+?)[\"']", r"copy\s+(.+?)\s+to\s+(?:the\s+)?clipboard"]),

    # ── System info ─────────────────────────────────────────
    ("sys_battery",   [r"\bbattery\b.*(?:level|status|percent|left|remaining)?", r"how\s+much\s+battery"]),
    ("sys_ip",        [r"(?:what\s+is\s+my\s+)?(?:ip|ip\s+address)\b", r"\bmy\s+ip\b"]),
    ("sys_disk",      [r"(?:disk|storage|drive)\s+(?:usage|space|available|free|info)", r"how\s+much\s+(?:disk\s+)?space"]),
    ("sys_ram",       [r"(?:ram|memory)\s+(?:usage|used|available|info)", r"how\s+much\s+ram"]),
    ("sys_temp",      [r"cpu\s+temperature\b", r"how\s+hot\s+is\s+(?:my\s+)?(?:cpu|computer|laptop)"]),
    ("sys_processes", [r"(?:list|show)\s+(?:running\s+)?(?:processes|programs)\b", r"\btop\s+processes\b"]),
    ("sys_kill",      [r"(?:kill|terminate)\s+(?:process\s+)?(.+)\b"]),

    # ── Power ────────────────────────────────────────────────
    ("lock_screen", [r"(?:lock|secure)\s+(?:the\s+)?(?:screen|computer|pc|laptop)\b"]),
    ("suspend",     [r"(?:suspend|sleep|hibernate)\s+(?:the\s+)?(?:system|computer|pc|laptop)?\b"]),
    ("shutdown",    [r"(?:shut\s+down|shutdown|power\s+off|turn\s+off)\s+(?:the\s+)?(?:system|computer|pc|laptop)?\b"]),
    ("reboot",      [r"(?:reboot|restart)\s+(?:the\s+)?(?:system|computer|pc|laptop)?\b"]),

    # ── Memory / Notes ───────────────────────────────────────
    ("memory_remember", [
        r"^remember\s+(?:that\s+)?(?!to\s)(.+)",
        r"^my\s+name\s+is\s+(.+)",
    ]),
    ("memory_recall",   [
        r"what\s+do\s+you\s+(?:know|remember)\s+about\s+me",
        r"what\s+have\s+you\s+(?:saved|stored)",
        r"tell\s+me\s+what\s+you\s+know\s+about\s+me",
    ]),
    ("note_save",  [r"(?:save|take)\s+a\s+note\s*[:\-]?\s*(.+)", r"^note\s*[:\-]\s*(.+)"]),
    ("note_read",  [r"(?:read|show|list)\s+my\s+notes\b", r"what\s+are\s+my\s+notes\b"]),
    ("knowledge_reload", [r"reload\s+(?:your\s+)?knowledge", r"update\s+knowledge\s+base"]),

    # ── Assistant control ────────────────────────────────────
    ("stop",          [r"^(?:stop|goodbye|bye|exit|quit|that'?s?\s+all)\s*$"]),
    ("clear_history", [r"(?:clear|reset|forget)\s+(?:(?:our|the)\s+)?(?:conversation|history|context|memory)\b"]),
    ("repeat",        [r"(?:repeat\s+that|say\s+that\s+again|what\s+did\s+you\s+say|pardon\??|come\s+again)\s*\??"]),
    ("help",          [r"what\s+can\s+you\s+do\b", r"(?:show\s+)?(?:help|commands|your\s+(?:commands|skills|capabilities))\b"]),

    # ── Web search — LAST, and SPECIFIC only ─────────────────
    # Only matches explicit search requests, NOT conversational ones.
    # "can you guide me", "explain", "how should I" → fall to LLM
    ("web_search", [
        r"^(?:search|look\s+up|find)\s+(?:for\s+)?(.{3,60})\s*$",
        r"^(?:what\s+is|who\s+is|where\s+is|when\s+(?:is|was|did))\s+([A-Z].{2,50})\s*\??$",
        r"^define\s+(\w[\w\s]{1,40})\s*$",
        r"^(?:what\s+does\s+)(\w[\w\s]{1,30})(?:\s+mean)\s*\??$",
    ]),
]


class Router:
    def __init__(self, config: dict = None):
        self.cfg = config or {}
        self._compiled = []
        for intent_name, patterns in INTENTS:
            compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
            self._compiled.append((intent_name, compiled))

    def route(self, text: str) -> Tuple[str, Optional[re.Match]]:
        text = text.strip()
        if not text:
            return ("empty", None)

        logger.debug(f"Routing: '{text}'")

        for intent_name, patterns in self._compiled:
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    logger.debug(f"Intent matched: {intent_name}")
                    return (intent_name, match)

        # Nothing matched → send to LLM
        logger.debug("No pattern match → LLM")
        return ("llm", None)

    def extract_app_name(self, text: str) -> str:
        text = re.sub(
            r"^(?:open|launch|start|run)\s+(?:the\s+)?",
            "", text, flags=re.IGNORECASE
        )
        text = re.sub(r"\s+app(?:lication)?$", "", text, flags=re.IGNORECASE)
        return text.strip()

    def extract_search_query(self, text: str) -> str:
        text = re.sub(
            r"^(?:search(?:\s+the\s+web)?(?:\s+for)?|look\s+up|find|google)\s+",
            "", text, flags=re.IGNORECASE
        )
        return text.strip()