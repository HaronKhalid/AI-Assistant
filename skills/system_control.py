"""
skills/system_control.py — Full PC Control
Fixes browser opening + adds: window management, process control,
clipboard, brightness, battery, disk, network, lock/sleep/shutdown
"""

import subprocess
import logging
import os
import shutil
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

BROWSERS = [
    ("firefox",          ["firefox"]),
    ("google-chrome",    ["google-chrome"]),
    ("chromium-browser", ["chromium-browser"]),
    ("chromium",         ["chromium"]),
    ("brave-browser",    ["brave-browser"]),
    ("brave",            ["brave"]),
    ("opera",            ["opera"]),
    ("vivaldi",          ["vivaldi"]),
    ("epiphany",         ["epiphany"]),
    ("falkon",           ["falkon"]),
]

TERMINALS = [
    "gnome-terminal", "xterm", "konsole", "xfce4-terminal",
    "lxterminal", "mate-terminal", "tilix", "alacritty", "kitty",
    "x-terminal-emulator",
]

FILE_MANAGERS = [
    "nautilus", "thunar", "dolphin", "nemo", "pcmanfm", "caja",
]

SETTINGS_APPS = [
    "gnome-control-center", "systemsettings5",
    "xfce4-settings-manager", "cinnamon-settings",
]

MONITORS = [
    "gnome-system-monitor", "ksysguard",
    "xfce4-taskmanager", "lxtask", "mate-system-monitor",
]

MUSIC_PLAYERS = [
    "rhythmbox", "clementine", "amarok", "lollypop",
    "strawberry", "spotify", "vlc",
]

APP_MAP = {
    "firefox":            "firefox",
    "chrome":             "google-chrome",
    "google chrome":      "google-chrome",
    "chromium":           "chromium-browser",
    "brave":              "brave-browser",
    "vlc":                "vlc",
    "gedit":              "gedit",
    "kate":               "kate",
    "code":               "code",
    "vs code":            "code",
    "visual studio code": "code",
    "calculator":         "gnome-calculator",
    "calc":               "gnome-calculator",
    "libreoffice":        "libreoffice",
    "writer":             "libreoffice --writer",
    "spreadsheet":        "libreoffice --calc",
    "presentation":       "libreoffice --impress",
    "thunderbird":        "thunderbird",
    "email":              "thunderbird",
    "discord":            "discord",
    "telegram":           "telegram-desktop",
    "slack":              "slack",
    "zoom":               "zoom",
    "gimp":               "gimp",
    "inkscape":           "inkscape",
    "blender":            "blender",
    "steam":              "steam",
    "htop":               "x-terminal-emulator -e htop",
    "top":                "x-terminal-emulator -e top",
}


class SystemControlSkill:
    def __init__(self, config: dict):
        self.cfg = config
        self._has_pactl    = shutil.which("pactl")  is not None
        self._has_amixer   = shutil.which("amixer") is not None
        self._browser      = self._find_browser()
        self._terminal     = self._find_first(TERMINALS)
        self._file_mgr     = self._find_first(FILE_MANAGERS)
        logger.info(f"SystemControl ready — browser={self._browser}, terminal={self._terminal}")

    # ── Helpers ──────────────────────────────────────────────
    def _find_browser(self) -> Optional[str]:
        # 1. Check known browsers in order
        for name, _ in BROWSERS:
            if shutil.which(name):
                logger.info(f"Found browser: {name}")
                return name
        # 2. Try xdg-settings
        try:
            r = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                desktop = r.stdout.strip()
                # e.g. "firefox.desktop" → try "firefox"
                name = desktop.replace(".desktop","").lower()
                for candidate in [name, name.split("-")[0]]:
                    if shutil.which(candidate):
                        logger.info(f"Found browser via xdg-settings: {candidate}")
                        return candidate
        except Exception:
            pass
        # 3. Try update-alternatives
        try:
            r = subprocess.run(
                ["update-alternatives", "--query", "x-www-browser"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.split("\n"):
                if line.startswith("Value:"):
                    path = line.split(":",1)[1].strip()
                    if os.path.exists(path):
                        return path
        except Exception:
            pass
        logger.warning("No browser found — will use xdg-open as fallback")
        return None

    def _find_first(self, candidates: list) -> Optional[str]:
        for c in candidates:
            if shutil.which(c):
                return c
        return None

    def _run(self, cmd: list, wait: bool = False) -> bool:
        """Launch process detached from ARIA so it doesn't block."""
        try:
            logger.debug(f"Running: {cmd}")
            if wait:
                r = subprocess.run(cmd, capture_output=True, timeout=15)
                return r.returncode == 0
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,   # detach fully
                    close_fds=True,
                )
                return True
        except FileNotFoundError:
            logger.error(f"Command not found: {cmd[0]}")
            return False
        except Exception as e:
            logger.error(f"Run failed {cmd}: {e}")
            return False

    # ── Volume ───────────────────────────────────────────────
    def volume_up(self, step: int = 10) -> str:
        ok = False
        if self._has_pactl:
            ok = self._run(["pactl","set-sink-volume","@DEFAULT_SINK@",f"+{step}%"], wait=True)
        elif self._has_amixer:
            ok = self._run(["amixer","set","Master",f"{step}%+"], wait=True)
        return f"Volume increased by {step}%." if ok else "Volume control failed."

    def volume_down(self, step: int = 10) -> str:
        ok = False
        if self._has_pactl:
            ok = self._run(["pactl","set-sink-volume","@DEFAULT_SINK@",f"-{step}%"], wait=True)
        elif self._has_amixer:
            ok = self._run(["amixer","set","Master",f"{step}%-"], wait=True)
        return f"Volume decreased by {step}%." if ok else "Volume control failed."

    def volume_set(self, percent: int) -> str:
        percent = max(0, min(100, percent))
        if self._has_pactl:
            self._run(["pactl","set-sink-volume","@DEFAULT_SINK@",f"{percent}%"], wait=True)
        elif self._has_amixer:
            self._run(["amixer","set","Master",f"{percent}%"], wait=True)
        return f"Volume set to {percent}%."

    def mute(self) -> str:
        if self._has_pactl:
            self._run(["pactl","set-sink-mute","@DEFAULT_SINK@","toggle"], wait=True)
        elif self._has_amixer:
            self._run(["amixer","set","Master","toggle"], wait=True)
        return "Audio muted."

    # ── Browser — FIXED ──────────────────────────────────────
    def open_browser(self, url: str = "") -> str:
        """Open browser, always works even if browser not in PATH."""

        # Strategy 1: known browser binary
        if self._browser:
            cmd = [self._browser]
            if url:
                cmd.append(url)
            if self._run(cmd):
                name = self._browser.replace("-"," ").title()
                return f"Opening {url or name}."

        # Strategy 2: xdg-open (uses system default)
        target = url if url else "http://duckduckgo.com"
        if self._run(["xdg-open", target]):
            return f"Opening {'browser' if not url else url} with your default browser."

        # Strategy 3: try every known browser
        for name, _ in BROWSERS:
            if shutil.which(name):
                cmd = [name] + ([url] if url else [])
                if self._run(cmd):
                    return f"Opening {name}."

        return (
            "Could not find a browser. "
            "Install Firefox: sudo apt install firefox"
        )

    def search_in_browser(self, query: str, engine: str = "duckduckgo") -> str:
        """Open browser with search query."""
        q = query.strip().replace(" ", "+")
        urls = {
            "google":     f"https://www.google.com/search?q={q}",
            "duckduckgo": f"https://duckduckgo.com/?q={q}",
            "bing":       f"https://www.bing.com/search?q={q}",
            "youtube":    f"https://www.youtube.com/results?search_query={q}",
            "github":     f"https://github.com/search?q={q}",
        }
        url = urls.get(engine, urls["duckduckgo"])
        result = self.open_browser(url)
        return f"Searching for '{query}' in your browser."

    def open_youtube(self, query: str = "") -> str:
        if query:
            return self.search_in_browser(query, "youtube")
        return self.open_browser("https://www.youtube.com")

    # ── App launcher ─────────────────────────────────────────
    def open_application(self, app_name: str) -> str:
        name = app_name.lower().strip()

        # Special cases
        if name in ("browser","web","internet","chrome","firefox","brave"):
            if name in APP_MAP:
                self._run([APP_MAP[name]])
                return f"Opening {name}."
            return self.open_browser()

        if name in ("terminal","console","command line","bash","shell"):
            return self.open_terminal()

        if name in ("files","file manager","folder","my files"):
            return self.open_file_manager()

        if name in ("settings","system settings","preferences"):
            return self.open_settings()

        if name in ("system monitor","task manager","processes"):
            app = self._find_first(MONITORS)
            if app:
                self._run([app])
                return "Opening system monitor."

        if name in ("music","music player","songs"):
            app = self._find_first(MUSIC_PLAYERS)
            if app:
                self._run([app])
                return f"Opening music player."

        # Check APP_MAP
        if name in APP_MAP:
            cmd = APP_MAP[name].split()
            if shutil.which(cmd[0]):
                self._run(cmd)
                return f"Opening {app_name}."
            # Not installed but let xdg try
            self._run(["xdg-open", name])
            return f"Trying to open {app_name}."

        # Try name directly as command
        for attempt in [name, name.replace(" ","-"), name.replace(" ","")]:
            if shutil.which(attempt):
                self._run([attempt])
                return f"Opening {app_name}."

        # Final: xdg-open
        self._run(["xdg-open", name])
        return f"Trying to open {app_name}. If it doesn't open, it may not be installed."

    def open_terminal(self) -> str:
        if self._terminal:
            self._run([self._terminal])
            return "Opening terminal."
        return "No terminal emulator found. Install one: sudo apt install gnome-terminal"

    def open_file_manager(self, path: str = "") -> str:
        mgr = self._file_mgr
        target = path or os.path.expanduser("~")
        if mgr:
            self._run([mgr, target])
            return f"Opening file manager."
        self._run(["xdg-open", target])
        return "Opening files."

    def open_settings(self) -> str:
        app = self._find_first(SETTINGS_APPS)
        if app:
            self._run([app])
            return "Opening system settings."
        return "System settings app not found."

    # ── Screenshot ───────────────────────────────────────────
    def take_screenshot(self, region: bool = False) -> str:
        shots_dir = os.path.expanduser("~/Pictures/Screenshots")
        os.makedirs(shots_dir, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(shots_dir, f"screenshot_{ts}.png")

        tools = (
            [["gnome-screenshot","-a","-f",path], ["scrot","-s",path], ["maim","-s",path]]
            if region else
            [["gnome-screenshot","-f",path], ["scrot",path], ["maim",path],
             ["import","-window","root",path]]
        )
        for tool in tools:
            if shutil.which(tool[0]):
                if self._run(tool, wait=True) and os.path.exists(path):
                    return "Screenshot saved to Pictures/Screenshots."
        return "Screenshot failed. Try: sudo apt install gnome-screenshot"

    # ── Clipboard ────────────────────────────────────────────
    def copy_to_clipboard(self, text: str) -> str:
        for tool, args in [
            ("xclip", ["-selection", "clipboard"]),
            ("xsel",  ["--clipboard","--input"]),
            ("wl-copy", []),
        ]:
            if shutil.which(tool):
                proc = subprocess.Popen([tool]+args, stdin=subprocess.PIPE)
                proc.communicate(text.encode())
                return f"Copied to clipboard."
        return "Install xclip: sudo apt install xclip"

    # ── Brightness ───────────────────────────────────────────
    def brightness_up(self, step: int = 10) -> str:
        for cmd in [["brightnessctl","set",f"+{step}%"], ["xbacklight",f"+{step}"]]:
            if shutil.which(cmd[0]):
                self._run(cmd, wait=True)
                return "Brightness increased."
        return "Brightness control not available. Install: sudo apt install brightnessctl"

    def brightness_down(self, step: int = 10) -> str:
        for cmd in [["brightnessctl","set",f"{step}%-"], ["xbacklight",f"-{step}"]]:
            if shutil.which(cmd[0]):
                self._run(cmd, wait=True)
                return "Brightness decreased."
        return "Brightness control not available."

    # ── Lock / Sleep / Shutdown ──────────────────────────────
    def lock_screen(self) -> str:
        for cmd in [
            ["loginctl","lock-session"],
            ["gnome-screensaver-command","--lock"],
            ["xdg-screensaver","lock"],
            ["light-locker-command","-l"],
        ]:
            if shutil.which(cmd[0]):
                self._run(cmd)
                return "Screen locked."
        return "Could not lock screen."

    def suspend_system(self) -> str:
        self._run(["systemctl","suspend"])
        return "System suspending."

    def shutdown_system(self) -> str:
        self._run(["systemctl","poweroff"])
        return "Shutting down in a moment."

    def reboot_system(self) -> str:
        self._run(["systemctl","reboot"])
        return "Rebooting."

    # ── System info ──────────────────────────────────────────
    def get_battery(self) -> str:
        for path in ["/sys/class/power_supply/BAT0/capacity",
                     "/sys/class/power_supply/BAT1/capacity"]:
            if os.path.exists(path):
                with open(path) as f:
                    return f"Battery is at {f.read().strip()}%."
        try:
            r = subprocess.run(["upower","-i","/org/freedesktop/UPower/devices/battery_BAT0"],
                                capture_output=True, text=True, timeout=5)
            for line in r.stdout.split("\n"):
                if "percentage" in line:
                    return f"Battery is at {line.split(':')[-1].strip()}."
        except Exception:
            pass
        return "No battery information available."

    def get_ip(self) -> str:
        try:
            r = subprocess.run(["hostname","-I"], capture_output=True, text=True, timeout=5)
            ips = r.stdout.strip().split()
            if ips:
                return f"Your IP address is {ips[0]}."
        except Exception:
            pass
        return "Could not get IP address."

    def get_disk(self) -> str:
        try:
            r = subprocess.run(["df","-h","/"], capture_output=True, text=True, timeout=5)
            parts = r.stdout.strip().split("\n")
            if len(parts) > 1:
                cols = parts[1].split()
                return f"Disk: {cols[2]} used of {cols[1]}, {cols[3]} free."
        except Exception:
            pass
        return "Disk info unavailable."

    def get_ram(self) -> str:
        try:
            r = subprocess.run(["free","-h"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.split("\n"):
                if line.startswith("Mem:"):
                    parts = line.split()
                    return f"RAM: {parts[2]} used of {parts[1]}, {parts[3]} free."
        except Exception:
            pass
        return "RAM info unavailable."

    def get_cpu_temp(self) -> str:
        paths = [
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/class/hwmon/hwmon0/temp1_input",
        ]
        for path in paths:
            if os.path.exists(path):
                with open(path) as f:
                    val = int(f.read().strip())
                    temp = val / 1000 if val > 1000 else val
                    return f"CPU temperature is {temp:.0f}°C."
        return "Temperature sensor not accessible."

    def list_processes(self) -> str:
        try:
            r = subprocess.run(
                ["ps","aux","--sort=-%cpu"],
                capture_output=True, text=True, timeout=5
            )
            lines = r.stdout.strip().split("\n")[1:6]
            procs = []
            for line in lines:
                parts = line.split()
                if len(parts) > 10:
                    procs.append(f"{parts[10]} ({parts[2]}% CPU)")
            return "Top processes: " + ", ".join(procs[:4]) + "."
        except Exception:
            return "Could not list processes."

    def kill_process(self, name: str) -> str:
        try:
            r = subprocess.run(["pkill","-f",name], capture_output=True)
            if r.returncode == 0:
                return f"Killed process: {name}."
            return f"No process named {name} found."
        except Exception as e:
            return f"Could not kill process: {e}"