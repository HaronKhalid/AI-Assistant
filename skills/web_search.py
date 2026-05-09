"""
skills/web_search.py — Web Search Skill
Uses DuckDuckGo Instant Answer API (free, no API key, no tracking).
Returns a concise spoken-friendly answer.
"""

import requests
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class WebSearchSkill:
    def __init__(self, config: dict):
        self.cfg = config
        self.max_results = config.get("max_results", 3)
        self.ddg_url = "https://api.duckduckgo.com/"

    def search(self, query: str) -> str:
        """
        Search DuckDuckGo and return a spoken-friendly answer.
        Tries Instant Answer first, falls back to web snippets.
        """
        if not query.strip():
            return "What would you like me to search for?"

        # Try DuckDuckGo Instant Answer first
        instant_answer = self._ddg_instant(query)
        if instant_answer:
            return instant_answer

        # Fallback: tell user to check manually
        return (
            f"I searched for '{query}' but couldn't find a quick answer. "
            f"You might want to open a browser and search directly."
        )

    def _ddg_instant(self, query: str) -> Optional[str]:
        """Query DuckDuckGo's Instant Answer API."""
        try:
            params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
                "no_redirect": "1",
            }
            resp = requests.get(
                self.ddg_url,
                params=params,
                timeout=8,
                headers={"User-Agent": "Aria Voice Assistant (open source)"}
            )

            if resp.status_code != 200:
                return None

            data = resp.json()

            # 1. Abstract (Wikipedia-style answer)
            abstract = data.get("AbstractText", "").strip()
            if abstract and len(abstract) > 20:
                # Truncate to a reasonable spoken length
                if len(abstract) > 300:
                    abstract = abstract[:297] + "..."
                return self._clean_for_speech(abstract)

            # 2. Answer (direct fact, e.g., "population of France: 67 million")
            answer = data.get("Answer", "").strip()
            if answer:
                return self._clean_for_speech(answer)

            # 3. Definition
            definition = data.get("Definition", "").strip()
            if definition:
                return self._clean_for_speech(definition)

            # 4. Related topics — take the first one
            topics = data.get("RelatedTopics", [])
            for topic in topics[:1]:
                if isinstance(topic, dict):
                    text = topic.get("Text", "").strip()
                    if text and len(text) > 20:
                        if len(text) > 250:
                            text = text[:247] + "..."
                        return self._clean_for_speech(text)

            return None

        except requests.Timeout:
            logger.warning("DuckDuckGo search timed out")
            return None
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return None

    def _clean_for_speech(self, text: str) -> str:
        """Remove things that don't sound good when spoken."""
        # Remove citations like [1], [citation needed]
        text = re.sub(r'\[\d+\]', '', text)
        text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
        # Remove parenthetical abbreviations
        text = re.sub(r'\([A-Z]{2,6}\)', '', text)
        # Clean whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
