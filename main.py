#!/usr/bin/env python3
"""
main.py — ARIA Voice Assistant (Full Version)
Usage:
  python main.py              # voice mode (with wake word if available)
  python main.py --no-wake    # voice, press Enter to trigger
  python main.py --text       # text mode (no mic, for testing)
"""

import sys, os, argparse, logging, time, queue, threading
import numpy as np
import sounddevice as sd
import yaml
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Config ────────────────────────────────────────────────────
def load_config() -> dict:
    p = ROOT / "config" / "settings.yaml"
    if not p.exists(): print(f"ERROR: No config at {p}"); sys.exit(1)
    with open(p) as f: return yaml.safe_load(f)

def setup_logging(cfg):
    lc = cfg.get("logging", {})
    lv = getattr(logging, lc.get("level","INFO"))
    lf = lc.get("file","logs/aria.log")
    os.makedirs(os.path.dirname(lf), exist_ok=True)
    os.makedirs("data/knowledge", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    handlers = [logging.FileHandler(lf)]
    if lc.get("console", True): handlers.append(logging.StreamHandler())
    logging.basicConfig(level=lv,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=handlers)

# ── Pretty output ─────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    RICH = True
except ImportError:
    RICH = False

def banner():
    if RICH:
        console.print(Panel.fit(
            "[bold cyan]ARIA[/bold cyan] — Open Source Voice Assistant\n"
            "[dim]Linux · CPU · Offline · Whisper + Phi3 + Kokoro[/dim]",
            border_style="cyan"))
    else:
        print("\n" + "="*50 + "\n  ARIA Voice Assistant\n" + "="*50)

def log_u(msg): print(f"\n  \033[33mYou:\033[0m  {msg}")
def log_a(msg): print(f"  \033[36mARIA:\033[0m {msg}\n")
def log_i(msg): print(f"  \033[90m{msg}\033[0m")


# ── Main assistant ────────────────────────────────────────────
class Aria:
    def __init__(self, cfg, args):
        self.cfg  = cfg
        self.args = args
        self.name = cfg.get("A",{}).get("name","Aria")
        self._running  = False
        self._last_response = ""
        self._audio_queue   = queue.Queue()

        audio_cfg = cfg.get("audio",{})
        self.sample_rate = audio_cfg.get("sample_rate", 16000)
        chunk_ms = audio_cfg.get("chunk_duration_ms", 80)
        self.chunk_size = int(self.sample_rate * chunk_ms / 1000)

        self._listening_for_command = False
        self._load_modules()

    def _load_modules(self):
        from core.tts         import TextToSpeech
        from core.stt         import SpeechToText
        from core.vad         import VoiceActivityDetector
        from core.brain       import Brain
        from core.router      import Router
        from core.wake_word   import WakeWordDetector
        from skills.timer     import TimerSkill
        from skills.weather   import WeatherSkill
        from skills.system_control import SystemControlSkill
        from skills.web_search import WebSearchSkill
        from skills.scheduler  import SchedulerSkill

        c = self.cfg
        log_i("Loading TTS..."); self.tts = TextToSpeech(c.get("tts",{}))
        log_i("Loading STT..."); self.stt = SpeechToText(c.get("stt",{}))
        log_i("Loading VAD..."); self.vad = VoiceActivityDetector(c.get("vad",{}))
        log_i("Loading Brain..."); self.brain = Brain(c.get("brain",{}))
        self.router = Router()
        self.wake   = WakeWordDetector(c.get("wake_word",{}))

        sk = c.get("skills",{})
        self.timer_skill   = TimerSkill(sk.get("timer",{}), self.tts.speak)
        self.weather_skill = WeatherSkill(sk.get("weather",{}))
        self.system_skill  = SystemControlSkill(sk.get("system_control",{}))
        self.search_skill  = WebSearchSkill(sk.get("web_search",{}))
        self.scheduler     = SchedulerSkill(
            sk.get("scheduler",{"db":"data/tasks.db"}),
            self.tts.speak,
            self.system_skill
        )
        log_i("All modules loaded ✓")

    # ── Command handler ───────────────────────────────────────
    def handle(self, text: str):
        if not text.strip(): return
        log_u(text)
        intent, match = self.router.route(text)
        resp = ""

        # ── Timers ──────────────────────────────────────────
        if intent == "timer_set" and match:
            v, u = match.group(1), match.group(2)
            secs = self.timer_skill.parse_duration(v, u)
            resp = self.timer_skill.set_timer(secs)

        elif intent == "timer_cancel":
            resp = self.timer_skill.cancel_timer()

        # ── Scheduler ───────────────────────────────────────
        elif intent == "schedule_task":
            resp = self.scheduler.parse_and_schedule(text)

        elif intent == "schedule_list":
            resp = self.scheduler.list_tasks()

        elif intent == "schedule_cancel":
            kw = match.group(1) if match and match.lastindex else ""
            resp = self.scheduler.cancel_all() if not kw else self.scheduler.cancel_task(kw)

        # ── Weather ─────────────────────────────────────────
        elif intent == "weather_current":
            resp = self.weather_skill.get_current_weather()

        elif intent == "weather_forecast":
            resp = self.weather_skill.get_forecast()

        # ── Volume ──────────────────────────────────────────
        elif intent == "volume_up":
            resp = self.system_skill.volume_up()
        elif intent == "volume_down":
            resp = self.system_skill.volume_down()
        elif intent == "volume_set" and match:
            resp = self.system_skill.volume_set(int(match.group(1)))
        elif intent == "volume_mute":
            resp = self.system_skill.mute()

        # ── Brightness ──────────────────────────────────────
        elif intent == "brightness_up":
            resp = self.system_skill.brightness_up()
        elif intent == "brightness_down":
            resp = self.system_skill.brightness_down()

        # ── Browser ─────────────────────────────────────────
        elif intent == "open_browser":
            resp = self.system_skill.open_browser()

        elif intent == "search_browser":
            q = match.group(1).strip() if match and match.lastindex else text
            resp = self.system_skill.search_in_browser(q)

        elif intent == "open_youtube":
            q = match.group(1).strip() if match and match.lastindex else ""
            resp = self.system_skill.open_youtube(q)

        elif intent == "open_url":
            url = match.group(1).strip() if match and match.lastindex else ""
            resp = self.system_skill.open_browser(url)

        # ── Apps ────────────────────────────────────────────
        elif intent == "open_app":
            app = self.router.extract_app_name(text)
            resp = self.system_skill.open_application(app)

        elif intent == "open_terminal":
            resp = self.system_skill.open_terminal()

        elif intent == "open_files":
            resp = self.system_skill.open_file_manager()

        elif intent == "open_settings":
            resp = self.system_skill.open_settings()

        # ── Screenshot ──────────────────────────────────────
        elif intent == "screenshot":
            resp = self.system_skill.take_screenshot()

        elif intent == "screenshot_region":
            resp = self.system_skill.take_screenshot(region=True)

        # ── Clipboard ───────────────────────────────────────
        elif intent == "clipboard_copy" and match:
            resp = self.system_skill.copy_to_clipboard(match.group(1))

        # ── System info ─────────────────────────────────────
        elif intent == "sys_battery":
            resp = self.system_skill.get_battery()
        elif intent == "sys_ip":
            resp = self.system_skill.get_ip()
        elif intent == "sys_disk":
            resp = self.system_skill.get_disk()
        elif intent == "sys_ram":
            resp = self.system_skill.get_ram()
        elif intent == "sys_temp":
            resp = self.system_skill.get_cpu_temp()
        elif intent == "sys_processes":
            resp = self.system_skill.list_processes()
        elif intent == "sys_kill" and match:
            resp = self.system_skill.kill_process(match.group(1).strip())

        # ── Power ────────────────────────────────────────────
        elif intent == "lock_screen":
            resp = self.system_skill.lock_screen()
        elif intent == "suspend":
            resp = self.system_skill.suspend_system()
        elif intent == "shutdown":
            resp = "Are you sure? Say 'yes shut down' to confirm."
        elif intent == "reboot":
            resp = "Rebooting now."
            self.tts.speak(resp, blocking=True)
            self.system_skill.reboot_system()
            return

        # ── Web search (API) ────────────────────────────────
        elif intent == "web_search":
            q = self.router.extract_search_query(text)
            resp = self.search_skill.search(q or text)

        # ── Memory / Notes ──────────────────────────────────
        elif intent in ("memory_remember","note_save","memory_recall","note_read"):
            resp = self.brain._handle_memory_command(text) or self.brain.think(text)

        elif intent == "knowledge_reload":
            self.brain.reload_knowledge()
            resp = "Knowledge base reloaded."

        # ── Control ─────────────────────────────────────────
        elif intent == "stop":
            resp = "Goodbye! Call me anytime."
            log_a(resp); self.tts.speak(resp, blocking=True)
            self._running = False; return

        elif intent == "clear_history":
            self.brain.clear_history()
            resp = "Conversation history cleared."

        elif intent == "repeat":
            resp = self._last_response or "Nothing to repeat."

        elif intent == "help":
            resp = (
                "I can set timers, schedule reminders, check weather, "
                "control volume and brightness, open any app or website, "
                "search the web, take screenshots, check battery, disk, RAM, "
                "lock or shut down your PC, save notes, and answer questions."
            )

        # ── LLM fallback ────────────────────────────────────
        else:
            resp = self.brain.think(text)

        if resp:
            self._last_response = resp
            log_a(resp)
            self.tts.speak(resp)

    # ── Audio ─────────────────────────────────────────────────
    def _audio_cb(self, indata, frames, t, status):
        self._audio_queue.put(indata[:,0].copy())

    def _listen_once(self):
        log_i(f"[{self.name}] Listening...")
        self.tts.speak("Yes?")
        time.sleep(0.4)
        # flush stale audio
        while not self._audio_queue.empty():
            try: self._audio_queue.get_nowait()
            except: break

        started = False
        timeout_start = time.time()
        while True:
            if not started and (time.time() - timeout_start) > 7:
                log_i("(timeout)"); return
            try:
                chunk = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            event, audio = self.vad.process_chunk(chunk)
            if event == "speech_start":
                started = True; log_i("(recording...)")
            elif event == "speech_end" and audio is not None:
                log_i("(processing...)")
                text = self.stt.transcribe(audio)
                self.handle(text); return

    def _on_wake(self):
        if self._listening_for_command: return
        self._listening_for_command = True
        self._listen_once()
        self._listening_for_command = False

    def run_voice(self):
        use_wake = (
            not self.args.no_wake
            and self.cfg.get("wake_word",{}).get("enabled", False)
            and self.wake.is_available
        )
        if use_wake:
            log_i('Say "Hey Jarvis" to activate ARIA')
            self.wake.start(self._on_wake)
        else:
            log_i("Press ENTER to speak to ARIA (wake word disabled)")

        self.tts.speak(f"Hi, I'm {self.name}. {'Say Hey Jarvis to wake me.' if use_wake else 'Press Enter to talk.'}")
        self._running = True

        with sd.InputStream(
            samplerate=self.sample_rate, channels=1,
            dtype="float32", blocksize=self.chunk_size,
            callback=self._audio_cb
        ):
            while self._running:
                if not use_wake:
                    try:
                        input()
                        if self._running: self._on_wake()
                    except (EOFError, KeyboardInterrupt): break
                else:
                    time.sleep(0.1)

        if use_wake: self.wake.stop()

    def run_text(self):
        self._running = True
        log_i("Text mode — type commands (Ctrl+C to quit)\n")
        self.tts.speak(f"Hi, I'm {self.name}, running in text mode.")
        while self._running:
            try:
                text = input("  You: ").strip()
                if text: self.handle(text)
            except (EOFError, KeyboardInterrupt): break

    def run(self):
        banner()
        if self.args.text: self.run_text()
        else: self.run_voice()
        log_i(f"\n{self.name} shut down. Goodbye!\n")


# ── Entry point ───────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-wake", action="store_true")
    p.add_argument("--text",    action="store_true")
    p.add_argument("--debug",   action="store_true")
    args = p.parse_args()

    cfg = load_config()
    if args.debug: cfg.setdefault("logging",{})["level"] = "DEBUG"
    setup_logging(cfg)

    try:
        Aria(cfg, args).run()
    except KeyboardInterrupt:
        print("\n  Interrupted. Goodbye!\n")
    except Exception as e:
        logging.getLogger(__name__).exception(e)
        print(f"\n  Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()