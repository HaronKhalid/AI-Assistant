"""
core/brain.py — Fixed Brain
Fixes:
  1. max_tokens raised to 1024 — no more truncation
  2. Identity-locked system prompt — model never changes who it is
  3. Knowledge injected cleanly, never overwrites identity
  4. Cache disabled for conversational queries (was causing stale replies)
  5. num_ctx raised to 4096 for proper context window
"""

import logging
import requests
import time
import sqlite3
import os
import hashlib
from typing import Optional, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# MEMORY
# ══════════════════════════════════════════════════════════════
class Memory:
    def __init__(self, db_path: str = "data/memory.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()
        logger.info(f"Memory DB: {db_path}")

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key      TEXT NOT NULL,
                value    TEXT NOT NULL,
                created  TEXT NOT NULL,
                updated  TEXT NOT NULL,
                UNIQUE(category, key)
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                role      TEXT NOT NULL,
                content   TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cache (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash TEXT UNIQUE NOT NULL,
                response   TEXT NOT NULL,
                created    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                title   TEXT NOT NULL,
                content TEXT NOT NULL,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def save_fact(self, category: str, key: str, value: str):
        now = datetime.now().isoformat()
        self.conn.execute("""
            INSERT INTO facts (category,key,value,created,updated)
            VALUES (?,?,?,?,?)
            ON CONFLICT(category,key) DO UPDATE SET value=?,updated=?
        """, (category, key, value, now, now, value, now))
        self.conn.commit()
        logger.debug(f"Fact saved: [{category}] {key}={value}")

    def get_fact(self, category: str, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM facts WHERE category=? AND key=?",
            (category, key)
        ).fetchone()
        return row[0] if row else None

    def get_all_facts(self) -> str:
        rows = self.conn.execute(
            "SELECT category,key,value FROM facts ORDER BY category,key"
        ).fetchall()
        if not rows:
            return ""
        lines = []
        cur_cat = None
        for cat, key, val in rows:
            if cat != cur_cat:
                lines.append(f"[{cat.upper()}]")
                cur_cat = cat
            lines.append(f"  {key}: {val}")
        return "\n".join(lines)

    def delete_fact(self, category: str, key: str):
        self.conn.execute(
            "DELETE FROM facts WHERE category=? AND key=?",
            (category, key)
        )
        self.conn.commit()

    def log_conversation(self, role: str, content: str):
        self.conn.execute(
            "INSERT INTO conversations (role,content,timestamp) VALUES (?,?,?)",
            (role, content, datetime.now().isoformat())
        )
        self.conn.commit()

    def get_recent_conversations(self, limit: int = 20) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT role,content FROM conversations ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def get_cached(self, query: str) -> Optional[str]:
        h = hashlib.md5(query.lower().strip().encode()).hexdigest()
        row = self.conn.execute(
            "SELECT response FROM cache WHERE query_hash=?", (h,)
        ).fetchone()
        return row[0] if row else None

    def save_cache(self, query: str, response: str):
        h = hashlib.md5(query.lower().strip().encode()).hexdigest()
        self.conn.execute(
            "INSERT OR REPLACE INTO cache (query_hash,response,created) VALUES (?,?,?)",
            (h, response, datetime.now().isoformat())
        )
        self.conn.commit()

    def save_note(self, title: str, content: str) -> str:
        now = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO notes (title,content,created,updated) VALUES (?,?,?,?)",
            (title, content, now, now)
        )
        self.conn.commit()
        return f"Note '{title}' saved."

    def get_notes(self) -> str:
        rows = self.conn.execute(
            "SELECT title,content FROM notes ORDER BY id DESC LIMIT 10"
        ).fetchall()
        if not rows:
            return "No notes saved."
        return "\n".join(f"• {t}: {c[:80]}" for t, c in rows)

    def close(self):
        self.conn.close()


# ══════════════════════════════════════════════════════════════
# KNOWLEDGE BASE
# ══════════════════════════════════════════════════════════════
class KnowledgeBase:
    def __init__(self, knowledge_dir: str = "data/knowledge"):
        self.knowledge_dir = knowledge_dir
        os.makedirs(knowledge_dir, exist_ok=True)
        self._docs: Dict[str, str] = {}
        self._load_all()
        self._create_example_knowledge()

    def _load_all(self):
        for fname in os.listdir(self.knowledge_dir):
            if fname.endswith(".txt"):
                path = os.path.join(self.knowledge_dir, fname)
                with open(path, "r", encoding="utf-8") as f:
                    self._docs[fname] = f.read()
        if self._docs:
            logger.info(f"Knowledge loaded: {list(self._docs.keys())}")

    def _create_example_knowledge(self):
        example = os.path.join(self.knowledge_dir, "about_me.txt")
        if not os.path.exists(example):
            with open(example, "w") as f:
                f.write("# Personal Knowledge\n"
                        "# Edit this file — ARIA reads it on startup\n\n"
                        "# Name: your name\n"
                        "# Location: your city\n"
                        "# Occupation: your job\n")

    def search(self, query: str) -> str:
        if not self._docs:
            return ""
        query_words = set(query.lower().split())
        best, best_score = "", 0
        for content in self._docs.values():
            for line in content.split("\n"):
                if line.startswith("#") or not line.strip():
                    continue
                score = len(query_words & set(line.lower().split()))
                if score > best_score:
                    best_score = score
                    best = line.strip()
        return best if best_score >= 2 else ""

    def get_all(self) -> str:
        parts = []
        for content in self._docs.values():
            lines = [l for l in content.split("\n")
                     if not l.startswith("#") and l.strip()]
            if lines:
                parts.append("\n".join(lines))
        return "\n".join(parts)

    def reload(self):
        self._docs.clear()
        self._load_all()


# ══════════════════════════════════════════════════════════════
# BRAIN  — Fixed version
# ══════════════════════════════════════════════════════════════
class Brain:
    def __init__(self, config: dict):
        self.cfg         = config
        self.model       = config.get("model", "phi3")
        self.temperature = config.get("temperature", 0.7)
        self.ollama_url  = "http://localhost:11434/api/chat"

        # ── FIX 1: proper token limits ───────────────────────
        # 1024 gives complete answers; voice TTS will just read it all
        self.max_tokens = config.get("max_tokens", 1024)

        # Memory + Knowledge
        self.memory    = Memory(config.get("memory_db", "data/memory.db"))
        self.knowledge = KnowledgeBase(config.get("knowledge_dir", "data/knowledge"))

        # In-session history
        self._history: List[Dict] = []
        self._max_history = 8

        # ── FIX 2: identity-locked system prompt ────────────
        # The assistant name and identity are ALWAYS first and clear.
        # User facts appended AFTER, clearly labelled.
        # This stops the model from adopting a different persona.
        assistant_name = config.get("assistant_name", "Aria")
        self._base_system = (
            f"Your name is {assistant_name}. "
            f"You are a helpful, honest, and friendly AI voice assistant. "
            f"You were created to run locally on the user's computer. "
            f"Never pretend to be a different assistant, person, or AI. "
            f"Never say you are ChatGPT, Claude, Gemini, or any other AI. "
            f"Always introduce yourself as {assistant_name} if asked. "
            f"Keep answers clear and conversational. "
            f"Do not use markdown, bullet points, or special formatting — "
            f"your response will be spoken aloud by a text-to-speech engine. "
            f"If you don't know something, say so honestly."
        )

        self.system_prompt = self._build_prompt()
        self._check_ollama()

    # ── System prompt builder ─────────────────────────────────
    def _build_prompt(self) -> str:
        """
        Build system prompt with identity FIRST, then user facts.
        This ensures the model never loses track of who it is.
        """
        prompt = self._base_system

        # Append user facts if any exist — clearly scoped
        facts = self.memory.get_all_facts()
        if facts:
            prompt += f"\n\nKnown facts about the user:\n{facts}"

        # Append relevant knowledge — trimmed to avoid bloat
        knowledge = self.knowledge.get_all()
        if knowledge:
            trimmed = knowledge[:400]  # keep prompt lean
            prompt += f"\n\nPersonal knowledge:\n{trimmed}"

        return prompt

    def _check_ollama(self):
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=5)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                matched = [m for m in models if self.model in m]
                if matched:
                    logger.info(f"Ollama ready — model: {matched[0]}")
                else:
                    logger.warning(
                        f"Model '{self.model}' not found in Ollama. "
                        f"Available: {models}. "
                        f"Run: ollama pull {self.model}"
                    )
        except requests.ConnectionError:
            logger.error("Ollama not running. Start with: ollama serve")
        except Exception as e:
            logger.error(f"Ollama check: {e}")

    # ── Main think method ─────────────────────────────────────
    def think(self, user_input: str, context: Optional[str] = None) -> str:
        if not user_input.strip():
            return "I didn't catch that. Could you repeat?"

        # Memory commands bypass LLM entirely
        mem_resp = self._handle_memory_command(user_input)
        if mem_resp:
            return mem_resp

        # ── FIX 3: only use cache for exact factual lookups ──
        # Do NOT cache conversational or guide-type questions.
        # Cache only if the query is short and ends with "?"
        is_cacheable = (
            len(user_input) < 60
            and user_input.strip().endswith("?")
            and not any(w in user_input.lower()
                        for w in ["guide", "explain", "how", "tell", "help",
                                  "what should", "what can", "can you"])
        )
        if is_cacheable:
            cached = self.memory.get_cached(user_input)
            if cached:
                logger.debug("Cache hit")
                return cached

        # Build message content
        content = user_input
        if context:
            content += f" [Additional info: {context}]"

        # Inject relevant knowledge snippet if found
        relevant = self.knowledge.search(user_input)
        if relevant:
            content += f" [From personal knowledge: {relevant}]"

        # Add to session history
        self._history.append({"role": "user", "content": content})
        if len(self._history) > self._max_history * 2:
            self._history = self._history[-(self._max_history * 2):]

        # Rebuild prompt so fresh facts are always included
        current_prompt = self._build_prompt()

        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": current_prompt},
                    *self._history
                ],
                "stream": False,
                "options": {
                    "temperature":    self.temperature,
                    "num_predict":    self.max_tokens,   # FIX: was 150 → now 1024
                    "num_ctx":        4096,              # FIX: was 1024 → proper context
                    "num_thread":     4,
                    "repeat_penalty": 1.1,
                }
            }

            start = time.time()
            resp  = requests.post(self.ollama_url, json=payload, timeout=120)
            elapsed = time.time() - start

            if resp.status_code == 200:
                reply = resp.json()["message"]["content"].strip()

                # ── FIX 4: sanity-check identity in reply ────
                # If model somehow introduces itself as something else, correct it
                assistant_name = self.cfg.get("assistant_name", "Aria")
                bad_ids = ["i am chatgpt", "i'm chatgpt",
                           "i am claude", "i'm claude",
                           "i am gemini", "i'm gemini",
                           "i am an ai assistant created by",
                           "i am google", "i am openai"]
                reply_lower = reply.lower()
                if any(b in reply_lower for b in bad_ids):
                    logger.warning("Model tried to change identity — correcting")
                    reply = (f"I'm {assistant_name}, your local voice assistant. "
                             + reply.split(".", 1)[-1].strip() if "." in reply else
                             f"I'm {assistant_name}, your local voice assistant.")

                logger.info(f"LLM ({elapsed:.1f}s): '{reply[:80]}...'")

                self._history.append({"role": "assistant", "content": reply})
                self.memory.log_conversation("user", user_input)
                self.memory.log_conversation("assistant", reply)

                # Cache only if it was a cacheable factual query
                if is_cacheable and elapsed < 15:
                    self.memory.save_cache(user_input, reply)

                return reply

            else:
                logger.error(f"Ollama error {resp.status_code}: {resp.text[:200]}")
                return "I had trouble thinking. Please try again."

        except requests.Timeout:
            return ("That question took too long to answer. "
                    "Try asking something shorter, or switch to a faster model like phi3.")
        except requests.ConnectionError:
            return "Ollama is not running. Start it with: ollama serve"
        except Exception as e:
            logger.error(f"Brain error: {e}")
            return "Something went wrong on my end."

    # ── Memory command handler ────────────────────────────────
    def _handle_memory_command(self, text: str) -> Optional[str]:
        t = text.lower().strip()
        name = self.cfg.get("assistant_name", "Aria")

        if "my name is" in t:
            val = text.split("is", 1)[-1].strip().rstrip(".")
            self.memory.save_fact("profile", "name", val)
            return f"Got it, I'll remember your name is {val}."

        if t.startswith("i am ") or t.startswith("i'm "):
            info = t.replace("i'm ", "").replace("i am ", "").strip()
            # Don't save empty or trivial things
            if len(info) > 2:
                self.memory.save_fact("profile", "description", info)
                return f"Noted. I'll remember that."

        if t.startswith("remember that ") or t.startswith("remember "):
            content = text.replace("remember that", "").replace("remember", "").strip()
            if content:
                self.memory.save_fact("notes", f"note_{int(time.time())}", content)
                return f"I'll remember: {content}"

        if any(p in t for p in ["what do you know about me",
                                  "what do you remember",
                                  "tell me what you know"]):
            facts = self.memory.get_all_facts()
            if facts:
                return f"Here is what I know about you: {facts[:300]}"
            return "I don't have any saved information about you yet."

        if t.startswith("save a note") or t.startswith("take a note"):
            content = text.split(":", 1)[-1].strip() if ":" in text else text[12:].strip()
            if content:
                self.memory.save_note("note", content)
                return f"Note saved: {content}"
            return "What would you like me to note?"

        if any(p in t for p in ["read my notes", "show my notes", "list my notes"]):
            return self.memory.get_notes()

        if t.startswith("forget my "):
            key = t.replace("forget my ", "").strip()
            self.memory.delete_fact("profile", key)
            return f"I've forgotten your {key}."

        return None

    # ── Utility ───────────────────────────────────────────────
    def clear_history(self):
        self._history = []
        logger.debug("Session history cleared")

    def reload_knowledge(self):
        self.knowledge.reload()
        self.system_prompt = self._build_prompt()
        logger.info("Knowledge reloaded")

    def get_history_summary(self) -> str:
        return f"{len(self._history) // 2} exchanges in memory"