"""
skills/scheduler.py — Task Scheduler
Schedule tasks by voice:
  "remind me in 10 minutes to drink water"
  "schedule a task at 3pm to call Ahmed"
  "every morning at 8am open firefox"
  "list my tasks"
  "cancel all reminders"

Stores tasks in data/tasks.db (SQLite).
Runs a background thread that checks every 30 seconds.
"""

import threading
import logging
import sqlite3
import time
import os
import re
from datetime import datetime, timedelta
from typing import Callable, Optional, List, Dict

logger = logging.getLogger(__name__)


class Task:
    def __init__(self, tid: int, label: str, run_at: float,
                 repeat_secs: int = 0, action: str = "remind",
                 action_arg: str = ""):
        self.tid        = tid
        self.label      = label
        self.run_at     = run_at    # Unix timestamp
        self.repeat_secs = repeat_secs  # 0 = one-shot
        self.action     = action    # "remind" | "open" | "search" | "command"
        self.action_arg = action_arg
        self.done       = False


class SchedulerSkill:
    def __init__(self, config: dict, speak_cb: Callable, system_skill=None):
        self.cfg        = config
        self.speak      = speak_cb
        self.system     = system_skill   # SystemControlSkill reference

        db_path = config.get("db", "data/tasks.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._create_table()
        self._load_tasks()

        # Background checker
        self._running = True
        self._thread = threading.Thread(
            target=self._check_loop, daemon=True, name="SchedulerThread"
        )
        self._thread.start()
        logger.info("Task scheduler started")

    def _create_table(self):
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                label       TEXT NOT NULL,
                run_at      REAL NOT NULL,
                repeat_secs INTEGER DEFAULT 0,
                action      TEXT DEFAULT 'remind',
                action_arg  TEXT DEFAULT '',
                done        INTEGER DEFAULT 0
            )
        """)
        self._db.commit()

    def _load_tasks(self):
        rows = self._db.execute(
            "SELECT id,label,run_at,repeat_secs,action,action_arg FROM tasks WHERE done=0"
        ).fetchall()
        self._tasks: List[Task] = [
            Task(r[0],r[1],r[2],r[3],r[4],r[5]) for r in rows
        ]
        logger.info(f"Loaded {len(self._tasks)} pending tasks")

    # ── Scheduling ────────────────────────────────────────────
    def schedule_reminder(self, label: str, delay_secs: int,
                          repeat_secs: int = 0,
                          action: str = "remind",
                          action_arg: str = "") -> str:
        """Schedule a reminder after delay_secs seconds."""
        run_at = time.time() + delay_secs

        with self._lock:
            cur = self._db.execute(
                "INSERT INTO tasks (label,run_at,repeat_secs,action,action_arg) VALUES (?,?,?,?,?)",
                (label, run_at, repeat_secs, action, action_arg)
            )
            self._db.commit()
            task = Task(cur.lastrowid, label, run_at, repeat_secs, action, action_arg)
            self._tasks.append(task)

        # Human-readable time
        dt = datetime.fromtimestamp(run_at)
        now = datetime.now()
        diff = run_at - time.time()

        if diff < 60:
            time_str = f"in {int(diff)} seconds"
        elif diff < 3600:
            mins = int(diff // 60)
            time_str = f"in {mins} minute{'s' if mins!=1 else ''}"
        elif diff < 86400:
            time_str = f"at {dt.strftime('%I:%M %p')}"
        else:
            time_str = f"on {dt.strftime('%B %d at %I:%M %p')}"

        logger.info(f"Task scheduled: '{label}' {time_str} (id={task.tid})")
        return f"Reminder set: {label} — {time_str}."

    def schedule_at_time(self, label: str, hour: int, minute: int = 0,
                         repeat_daily: bool = False,
                         action: str = "remind",
                         action_arg: str = "") -> str:
        """Schedule at a specific time today (or tomorrow if past)."""
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        delay = (target - now).total_seconds()
        repeat = 86400 if repeat_daily else 0
        return self.schedule_reminder(label, int(delay), repeat, action, action_arg)

    def parse_and_schedule(self, text: str) -> str:
        """Parse natural language scheduling commands."""
        t = text.lower().strip()

        # Extract the label (what to remind about)
        label = self._extract_label(text)

        # ── "in X minutes/hours/seconds" ─────────────────────
        delay_match = re.search(
            r'in\s+(\d+)\s*(second|minute|min|hour|hr)s?',
            t
        )
        if delay_match:
            val  = int(delay_match.group(1))
            unit = delay_match.group(2)
            secs = val * {"second":1,"minute":60,"min":60,"hour":3600,"hr":3600}[unit]
            action, arg = self._extract_action(t)
            return self.schedule_reminder(label, secs, action=action, action_arg=arg)

        # ── "at H:MM am/pm" or "at 3pm" ──────────────────────
        time_match = re.search(
            r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?',
            t
        )
        if time_match:
            hour   = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            ampm   = time_match.group(3)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            daily  = "every" in t or "daily" in t or "every day" in t
            action, arg = self._extract_action(t)
            return self.schedule_at_time(label, hour, minute, daily, action, arg)

        # ── "tomorrow at..." ──────────────────────────────────
        if "tomorrow" in t:
            time_match2 = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', t)
            if time_match2:
                hour   = int(time_match2.group(1))
                minute = int(time_match2.group(2) or 0)
                ampm   = time_match2.group(3)
                if ampm == "pm" and hour < 12: hour += 12
                now    = datetime.now()
                target = (now + timedelta(days=1)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                delay = (target - now).total_seconds()
                action, arg = self._extract_action(t)
                return self.schedule_reminder(label, int(delay), action=action, action_arg=arg)

        # ── "every morning/evening" ───────────────────────────
        if "every morning" in t:
            action, arg = self._extract_action(t)
            return self.schedule_at_time(label, 8, 0, True, action, arg)
        if "every evening" in t or "every night" in t:
            action, arg = self._extract_action(t)
            return self.schedule_at_time(label, 20, 0, True, action, arg)
        if "every noon" in t or "every midday" in t:
            action, arg = self._extract_action(t)
            return self.schedule_at_time(label, 12, 0, True, action, arg)

        return (
            "I couldn't understand the schedule. Try: "
            "'remind me in 10 minutes to drink water' or "
            "'schedule a task at 3pm to open firefox'."
        )

    def _extract_label(self, text: str) -> str:
        """Extract what to remind about from the sentence."""
        t = text.lower()
        # Remove scheduling phrases to get the label
        label = re.sub(
            r'(remind\s+me\s+|schedule\s+a?\s*task\s+|set\s+a?\s*reminder\s+|'
            r'in\s+\d+\s*\w+\s+|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s+|'
            r'every\s+\w+\s*(?:at\s+\d+(?::\d{2})?\s*(?:am|pm)?)?\s+|'
            r'tomorrow\s+at\s+\d+(?::\d{2})?\s*(?:am|pm)?\s+|'
            r'to\s+|for\s+)',
            '', text, flags=re.IGNORECASE
        ).strip().rstrip('.')
        return label or "reminder"

    def _extract_action(self, text: str) -> tuple:
        """Extract what action to perform (open app, search, etc.)."""
        t = text.lower()
        open_match = re.search(r'open\s+(\w[\w\s]*?)(?:\s+and|\s+at|\s+in|$)', t)
        if open_match:
            return ("open", open_match.group(1).strip())
        search_match = re.search(r'search\s+(?:for\s+)?(.+?)(?:\s+at|\s+in|$)', t)
        if search_match:
            return ("search", search_match.group(1).strip())
        return ("remind", "")

    # ── Task management ───────────────────────────────────────
    def list_tasks(self) -> str:
        with self._lock:
            pending = [t for t in self._tasks if not t.done]
        if not pending:
            return "You have no scheduled tasks."
        lines = []
        for task in pending[:5]:
            dt = datetime.fromtimestamp(task.run_at)
            diff = task.run_at - time.time()
            if diff < 60:
                when = f"in {int(diff)}s"
            elif diff < 3600:
                when = f"in {int(diff//60)}m"
            else:
                when = dt.strftime("%I:%M %p")
            repeat = " (daily)" if task.repeat_secs == 86400 else ""
            lines.append(f"{task.label} — {when}{repeat}")
        count = len(pending)
        header = f"You have {count} task{'s' if count!=1 else ''}. "
        return header + ". ".join(lines[:3]) + ("." if len(lines)<=3 else " and more.")

    def cancel_task(self, task_id_or_label: str = "") -> str:
        """Cancel task by ID or label keyword."""
        with self._lock:
            if task_id_or_label.isdigit():
                tid = int(task_id_or_label)
                self._tasks = [t for t in self._tasks if t.tid != tid]
                self._db.execute("UPDATE tasks SET done=1 WHERE id=?", (tid,))
                self._db.commit()
                return f"Task {tid} cancelled."

            keyword = task_id_or_label.lower()
            cancelled = []
            remaining = []
            for t in self._tasks:
                if keyword in t.label.lower():
                    cancelled.append(t)
                    self._db.execute("UPDATE tasks SET done=1 WHERE id=?", (t.tid,))
                else:
                    remaining.append(t)
            self._db.commit()
            self._tasks = remaining

            if cancelled:
                return f"Cancelled {len(cancelled)} task(s) matching '{keyword}'."
            return f"No tasks matching '{keyword}' found."

    def cancel_all(self) -> str:
        with self._lock:
            count = len(self._tasks)
            self._tasks = []
            self._db.execute("UPDATE tasks SET done=1 WHERE done=0")
            self._db.commit()
        return f"Cancelled all {count} task(s)."

    # ── Background checker ────────────────────────────────────
    def _check_loop(self):
        while self._running:
            try:
                self._fire_due_tasks()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            time.sleep(15)  # check every 15 seconds

    def _fire_due_tasks(self):
        now = time.time()
        with self._lock:
            due = [t for t in self._tasks if t.run_at <= now and not t.done]

        for task in due:
            logger.info(f"Task due: '{task.label}' (action={task.action})")
            self._execute_task(task)

            with self._lock:
                if task.repeat_secs > 0:
                    # Reschedule
                    task.run_at = now + task.repeat_secs
                    self._db.execute(
                        "UPDATE tasks SET run_at=? WHERE id=?",
                        (task.run_at, task.tid)
                    )
                else:
                    task.done = True
                    self._db.execute(
                        "UPDATE tasks SET done=1 WHERE id=?", (task.tid,)
                    )
                self._db.commit()

        with self._lock:
            self._tasks = [t for t in self._tasks if not t.done]

    def _execute_task(self, task: Task):
        """Execute a task when it fires."""
        if task.action == "remind":
            self.speak(f"Reminder: {task.label}")

        elif task.action == "open" and self.system:
            self.speak(f"Time to {task.label}. Opening {task.action_arg}.")
            self.system.open_application(task.action_arg)

        elif task.action == "search" and self.system:
            self.speak(f"Reminder: {task.label}. Searching for {task.action_arg}.")
            self.system.search_in_browser(task.action_arg)

        elif task.action == "command":
            try:
                subprocess.Popen(
                    task.action_arg.split(),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self.speak(f"Running scheduled task: {task.label}")
            except Exception as e:
                logger.error(f"Task command failed: {e}")
                self.speak(f"Scheduled task failed: {task.label}")

    def stop(self):
        self._running = False