#!/usr/bin/env python3
import os
import sys
import time
import threading
import subprocess
import getpass
import shutil
from pathlib import Path
from datetime import datetime
import curses
import hashlib
import json

import face_recognition
import cv2
import numpy as np
curses.initscr()
# --- MODIFICATION: Centralized Configuration Management ---
CONFIG_DIR = Path.home() / ".config" / "face-lock"
CONFIG_FILE = CONFIG_DIR / "config.json"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_config():
    """Loads settings from the JSON config file, with sane defaults."""
    defaults = {
        "camera_index": 0,
        "tolerance": 0.6,
        "enable_animations": True,
        "anim_duration_in": 0.55,
        "anim_duration_out": 0.60,
        "anim_in_style": "bounce",
        "anim_out_style": "slide-up",
        "enable_face_recognition": True,
        "enable_fingerprint": True,
        "clock_font": "digital",
        "hint_text": "Use \u2190/\u2192 to change session. Space for password.",
        "shake_intensity": 3,
        "default_session": "auto"
    }
    if not CONFIG_FILE.exists():
        return defaults
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            # Ensure all keys are present, falling back to defaults
            for key, value in defaults.items():
                config.setdefault(key, value)
            return config
    except (json.JSONDecodeError, TypeError):
        return defaults

CONFIG = load_config()
# --- End of Configuration Management ---

class PopupManager:
    def __init__(self):
        self.message = None
        self.start_time = None

    def show(self, msg):
        self.message = msg
        self.start_time = time.time()

    def render(self, stdscr):
        if not self.message: return
        if time.time() - self.start_time > 1.0: self.message = None; return
        elapsed = time.time() - self.start_time
        attr = curses.A_DIM if elapsed < 0.2 or elapsed > 0.7 else curses.A_NORMAL
        h, w = stdscr.getmaxyx()
        x = w // 2 - len(self.message) // 2
        y = h - 3
        try: stdscr.addstr(y, x, self.message, attr)
        except curses.error: pass

try:
    import pyfiglet
    HAVE_PYFIGLET = True
except Exception:
    HAVE_PYFIGLET = False

try:
    import pam as _pam_pkg
    if hasattr(_pam_pkg, "pam"): _pam_auth_fn = lambda u, p: bool(_pam_pkg.pam().authenticate(u, p))
    elif hasattr(_pam_pkg, "Pam"): _pam_auth_fn = lambda u, p: bool(_pam_pkg.Pam().authenticate(u, p))
    elif hasattr(_pam_pkg, "authenticate"): _pam_auth_fn = lambda u, p: bool(_pam_pkg.authenticate(u, p))
    else: _pam_auth_fn = None
except Exception: _pam_auth_fn = None

# Constants from config or system
PASS_FILE = Path.home() / ".face_lock_pass"
KNOWN_FACES_DIR = Path.home() / ".face_lock_profiles" / "default" / "known_faces"
KNOWN_FACES_DIR.mkdir(parents=True, exist_ok=True)
USERNAME = os.getenv("USER") or getpass.getuser()

# Apply settings from config
CAMERA_INDEX = int(CONFIG["camera_index"])
TOLERANCE = float(CONFIG["tolerance"])
ANIM_ENABLED = bool(CONFIG["enable_animations"])
ANIM_DURATION_IN = float(CONFIG["anim_duration_in"])
ANIM_DURATION_OUT = float(CONFIG["anim_duration_out"])
ANIM_IN_STYLE = CONFIG["anim_in_style"]
ANIM_OUT_STYLE = CONFIG["anim_out_style"]
ENABLE_FACE = bool(CONFIG["enable_face_recognition"])
ENABLE_FINGERPRINT = bool(CONFIG["enable_fingerprint"])
SHAKE_AMPLITUDE = int(CONFIG["shake_intensity"])

UNLOCK_COMMANDS = {
    "gnome-wayland": "dbus-run-session env XDG_SESSION_TYPE=wayland gnome-session",
    "gnome-x11": "dbus-run-session env XDG_SESSION_TYPE=x11 gnome-session",
    "kde": (shutil.which("startplasma-wayland") and "dbus-run-session env XDG_SESSION_TYPE=wayland startplasma-wayland") or \
           (shutil.which("startplasma-x11") and "dbus-run-session env XDG_SESSION_TYPE=x11 startplasma-x11") or \
           (shutil.which("startkde") and "dbus-run-session startkde")
}
UNLOCK_COMMANDS = {k: v for k, v in UNLOCK_COMMANDS.items() if v}

def verify_password(password):
    if PASS_FILE.exists():
        try:
            salt, saved_hash = open(PASS_FILE).read().strip().split(":")
            return hashlib.sha256(salt.encode() + password.encode()).hexdigest() == saved_hash
        except Exception: return False
    elif _pam_auth_fn: return _pam_auth_fn(USERNAME, password)
    return False

class FaceDB:
    def __init__(self, path=KNOWN_FACES_DIR):
        self.path = Path(path)
        self.encodings, self.names = [], []
        self.load()

    def load(self):
        self.encodings, self.names = [], []
        for f in self.path.glob("*.jpg"):
            try:
                img = face_recognition.load_image_file(str(f))
                if encs := face_recognition.face_encodings(img):
                    self.encodings.append(encs[0])
                    self.names.append(f.stem)
            except: pass

face_db = FaceDB()

def fingerprint_verify(username=USERNAME, timeout=30):
    if not (cmd := shutil.which("fprintd-verify")): return False
    try:
        return subprocess.run([cmd, username], stdin=open("/dev/tty", "r"), capture_output=True, timeout=timeout).returncode == 0
    except Exception: return False

class FaceWorker(threading.Thread):
    def __init__(self, on_success, popup):
        super().__init__(daemon=True)
        self.on_success, self.popup = on_success, popup
        self._stop_event, self._shown = threading.Event(), False
        self.cap = None

    def stop(self): self._stop_event.set()

    def run(self):
        if not ENABLE_FACE: return
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        if not self.cap.isOpened(): return
        try:
            while not self._stop_event.is_set():
                ret, frame = self.cap.read()
                if not ret: time.sleep(0.1); continue
                if face_db.encodings:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    if encs := face_recognition.face_encodings(rgb, face_recognition.face_locations(rgb)):
                        if True in face_recognition.compare_faces(face_db.encodings, encs[0], tolerance=TOLERANCE):
                            self.on_success("face", USERNAME); return
                elif not self._shown: self.popup.show("No known faces configured"); self._shown = True
                time.sleep(0.05)
        finally:
            if self.cap and self.cap.isOpened(): self.cap.release()
            cv2.destroyAllWindows()

class FingerprintWorker(threading.Thread):
    def __init__(self, on_success, popup):
        super().__init__(daemon=True)
        self.on_success, self.popup = on_success, popup
        self._stop, self._shown = threading.Event(), False

    def stop(self): self._stop.set()

    def run(self):
        if not ENABLE_FINGERPRINT: return
        while not self._stop.is_set():
            if fingerprint_verify(USERNAME, timeout=10):
                self.on_success("fingerprint", USERNAME); return
            elif not self._shown: self.popup.show("Use fingerprint or press Space"); self._shown = True
            time.sleep(1)

def launch_and_exit(choice_key, stdscr):
    curses.nocbreak(); stdscr.keypad(False); curses.echo(); curses.endwin()
    if not (cmd := UNLOCK_COMMANDS.get(choice_key)):
        print(f"Error: Command for '{choice_key}' not found.", file=sys.stderr); sys.exit(1)
    print(f"Authenticated. Launching: {choice_key}...")
    subprocess.Popen(["/bin/sh", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys.exit(0)

BIG_DIGITS = {"0":[" ███ ","█   █","█   █","█   █"," ███ "],"1":["  █  "," ██  ","  █  ","  █  "," ███ "],"2":[" ███ ","█   █","  ██ "," █   ","█████"],"3":[" ███ ","█   █","  ██ ","█   █"," ███ "],"4":["█  █ ","█  █ ","█████","   █ ","   █ "],"5":["█████","█    ","████ ","    █","████ "],"6":[" ███ ","█    ","████ ","█   █"," ███ "],"7":["█████","    █","   █ ","  █  ","  █  "],"8":[" ███ ","█   █"," ███ ","█   █"," ███ "],"9":[" ███ ","█   █"," ████","    █"," ███ "],":":["     ","  █  ","     ","  █  ","     "]}
def render_big_time(timestr):
    lines = [""] * 5
    for ch in timestr:
        for i, part in enumerate(BIG_DIGITS.get(ch, ["     "]*5)): lines[i] += part + "  "
    return lines

# --- Animation helpers (FIXED & REFORMATTED) ---
def _ease_out_cubic(t):
    """Cubic easing out function."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3

def _ease_out_bounce(t):
    """Bounce easing out function (Penner's)."""
    t = max(0.0, min(1.0, t))
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    elif t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    elif t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    else:
        t -= 2.625 / d1
        return n1 * t * t + 0.984375

def _compute_center(stdscr, lines):
    """Computes the center coordinates for a block of text."""
    h, w = stdscr.getmaxyx()
    text_h = len(lines)
    text_w = max((len(ln) for ln in lines), default=0)
    y = max(0, (h - text_h) // 2)
    x = max(0, (w - text_w) // 2)
    return y, x, text_h, text_w, h, w

def _noise01(r, c):
    """Simple hash function to generate a pseudo-random float [0,1)."""
    v = (r * 73856093) ^ (c * 19349663) ^ 0x9e3779b9
    v &= 0xffffffff
    return v / 0xffffffff

def _draw_lines_mask(stdscr, y, x, lines, visible_fn, attr=0):
    """Draws lines with a visibility mask function."""
    h, w = stdscr.getmaxyx()
    for r, ln in enumerate(lines):
        yy = y + r
        if not (0 <= yy < h):
            continue
        
        # BUG FIX: The second variable in enumerate was also 'c', changed to 'ch'.
        seg = ''.join(ch if visible_fn(r, c) else ' ' for c, ch in enumerate(ln))
        
        xx = x
        if x < 0:
            seg = seg[-x:]
            xx = 0
        
        if xx >= w:
            continue
            
        seg = seg[:max(0, w - xx)]
        
        # SYNTAX FIX: The try/except block was on one line, which is invalid.
        if seg:
            try:
                stdscr.addstr(yy, xx, seg, attr)
            except curses.error:
                # This can happen if the window is resized, just ignore it.
                pass

def _attr_for_fade(t):
    """Returns bold, normal, or dim attribute based on time."""
    return curses.A_BOLD if t < 0.33 else curses.A_NORMAL if t < 0.66 else curses.A_DIM

def anim_slide(stdscr, lines, unlocked_event, duration, fps, mode):
    """Animation: slides content out."""
    if not ANIM_ENABLED: return
    
    y0, x0, th, tw, H, W = _compute_center(stdscr, lines)
    frames = max(1, int(duration * fps))
    
    if mode == "slide-up-out":
        dist = y0 + th + 2
        dx, dy = 0, -1
    else: # Only slide-up-out is implemented in this compact version
        return

    for i in range(frames + 1):
        if unlocked_event.is_set(): return
        t = i / frames
        e = _ease_out_cubic(t)
        stdscr.erase()
        off = int(dist * e)
        x = x0 + dx * off
        y = y0 + dy * off
        vis = 1.0 - t
        attr = _attr_for_fade(t)
        _draw_lines_mask(stdscr, y, x, lines, lambda r, c: _noise01(r, c) < vis, attr)
        stdscr.refresh()
        time.sleep(1.0 / fps)

def anim_bounce_in(stdscr, lines, unlocked_event, duration, fps):
    """Animation: bounces content in from the top."""
    if not ANIM_ENABLED: return
    
    y0, x0, th, tw, H, W = _compute_center(stdscr, lines)
    frames = max(1, int(duration * fps))
    start_y = -th - 2
    span = y0 - start_y
    
    for i in range(frames + 1):
        if unlocked_event.is_set(): return
        t = i / frames
        e = _ease_out_bounce(t)
        y = int(start_y + span * e)
        vis = min(1.0, 0.25 + t)  # Become visible early
        attr = _attr_for_fade(1 - t)
        stdscr.erase()
        _draw_lines_mask(stdscr, y, x0, lines, lambda r, c: _noise01(r, c) < vis, attr)
        stdscr.refresh()
        time.sleep(1.0 / fps)

def play_anim(stdscr, style, lines, unlocked_event, entering, duration, fps):
    """Plays an animation based on the style string."""
    if not ANIM_ENABLED: return
    
    # This simplified version only supports one style for in and out
    if not entering:
        anim_slide(stdscr, lines, unlocked_event, duration, fps, "slide-up-out")
    else:
        anim_bounce_in(stdscr, lines, unlocked_event, duration, fps)

def shake_panel(stdscr, draw_fn, cycles=10, amplitude=2, fps=60, unlocked_event=None):
    """Shakes a panel horizontally to indicate an error."""
    if not ANIM_ENABLED:
        draw_fn(0, 0)
        return
        
    pattern = [0, amplitude, -amplitude, amplitude // 2, -amplitude // 2, 0]
    for i in range(cycles):
        if unlocked_event and unlocked_event.is_set(): return
        dx = pattern[i % len(pattern)]
        stdscr.erase()
        draw_fn(dx, 0)
        stdscr.refresh()
        time.sleep(1.0 / fps)

class TTYSafeLock:
    def __init__(self):
        self.unlocked_event = threading.Event()
        self.desktop_choices = list(UNLOCK_COMMANDS.keys())
        self.desktop_index = 0
        if CONFIG["default_session"] in self.desktop_choices:
            self.desktop_index = self.desktop_choices.index(CONFIG["default_session"])
        self.password_mode = False
        self.password_buffer = ""
        self.message = ""
        self.popup = PopupManager()

    def start_workers(self):
        face_db.load()
        self.face_worker = FaceWorker(self._on_auth_success, self.popup)
        self.fprint_worker = FingerprintWorker(self._on_auth_success, self.popup)
        self.face_worker.start()
        self.fprint_worker.start()

    def stop_workers(self):
        self.face_worker.stop(); self.fprint_worker.stop()
        self.face_worker.join(timeout=1.0); self.fprint_worker.join(timeout=1.0)

    def _on_auth_success(self, method, identity): self.unlocked_event.set()

    def draw_clock(self):
        now = datetime.now().strftime("%H:%M")
        if HAVE_PYFIGLET and CONFIG["clock_font"] == "artistic":
            return pyfiglet.figlet_format(now, font="big").splitlines()
        return render_big_time(now)

    def run(self, stdscr):
        curses.curs_set(0); stdscr.nodelay(True); stdscr.keypad(True)
        if curses.has_colors(): curses.start_color(); curses.use_default_colors()
        self.start_workers()
        try: play_anim(stdscr, ANIM_IN_STYLE, self.draw_clock(), self.unlocked_event, True, ANIM_DURATION_IN, 50)
        except: pass
        while not self.unlocked_event.is_set():
            stdscr.erase(); h, w = stdscr.getmaxyx()
            if self.password_mode: self.draw_password_panel(stdscr, h, w)
            else: self.draw_main_screen(stdscr, h, w)
            self.popup.render(stdscr); stdscr.refresh()
            try:
                if (ch := stdscr.getch()) == -1: time.sleep(0.05); continue
                self.handle_input(ch, stdscr)
            except KeyboardInterrupt: break
        if self.unlocked_event.is_set():
            self.stop_workers()
            if self.desktop_choices: launch_and_exit(self.desktop_choices[self.desktop_index], stdscr)
            else: curses.endwin(); print("Auth OK, but no sessions found.", file=sys.stderr); sys.exit(0)

    def draw_password_panel(self, stdscr, h, w):
        bw,bh=30,7; sx,sy=(w-bw)//2,(h-bh)//2
        try:
            for xi in range(bw):stdscr.addch(sy,sx+xi,curses.ACS_HLINE);stdscr.addch(sy+bh-1,sx+xi,curses.ACS_HLINE)
            for yi in range(bh):stdscr.addch(sy+yi,sx,curses.ACS_VLINE);stdscr.addch(sy+yi,sx+bw-1,curses.ACS_VLINE)
            stdscr.addch(sy,sx,curses.ACS_ULCORNER);stdscr.addch(sy,sx+bw-1,curses.ACS_URCORNER)
            stdscr.addch(sy+bh-1,sx,curses.ACS_LLCORNER);stdscr.addch(sy+bh-1,sx+bw-1,curses.ACS_LRCORNER)
            stdscr.addstr(sy+1,sx+2,"Password:");stdscr.addstr(sy+3,sx+2,"*"*len(self.password_buffer))
            stdscr.addstr(sy+5,sx+2,"Enter to submit, ESC to cancel")
            if self.message:stdscr.addstr(sy+bh,sx+2,self.message,curses.A_BOLD)
        except:pass

    def draw_main_screen(self, stdscr, h, w):
        lines=self.draw_clock(); start_r=(h-len(lines))//2
        for i,ln in enumerate(lines):
            try:stdscr.addstr(start_r+i,(w-len(ln))//2,ln,curses.A_BOLD)
            except:pass
        if self.desktop_choices:
            session_text=f"< {self.desktop_choices[self.desktop_index]} >"
            try:stdscr.addstr(h-4,(w-len(session_text))//2,session_text)
            except:pass
        try:stdscr.addstr(h-2,(w-len(CONFIG["hint_text"]))//2,CONFIG["hint_text"],curses.A_DIM)
        except:pass

    def handle_input(self, ch, stdscr):
        if self.password_mode: self.handle_password_input(ch, stdscr)
        else: self.handle_main_input(ch, stdscr)

    def handle_main_input(self, ch, stdscr):
        if ch == ord(' '):
            play_anim(stdscr, ANIM_OUT_STYLE, self.draw_clock(), self.unlocked_event, False, ANIM_DURATION_OUT, 50)
            self.password_mode=True;self.password_buffer="";self.message="";curses.curs_set(1)
        elif ch==curses.KEY_LEFT: self.desktop_index=(self.desktop_index-1)%len(self.desktop_choices) if self.desktop_choices else 0
        elif ch==curses.KEY_RIGHT: self.desktop_index=(self.desktop_index+1)%len(self.desktop_choices) if self.desktop_choices else 0

    def handle_password_input(self, ch, stdscr):
        if ch==27:
            self.password_mode=False;self.password_buffer="";self.message="";curses.curs_set(0)
            play_anim(stdscr,ANIM_IN_STYLE,self.draw_clock(),self.unlocked_event,True,ANIM_DURATION_IN,50)
        elif ch in(10,13):
            if verify_password(self.password_buffer):self._on_auth_success("password",USERNAME)
            else:
                self.message="Incorrect password"
                h,w=stdscr.getmaxyx()
                shake_panel(stdscr,lambda dx,dy:self.draw_password_panel(stdscr,h,w),a=SHAKE_AMPLITUDE,e=self.unlocked_event)
                self.password_buffer=""
        elif ch in(curses.KEY_BACKSPACE,127,8):self.password_buffer=self.password_buffer[:-1]
        elif 32<=ch<256:self.password_buffer+=chr(ch)

def main():
    if not UNLOCK_COMMANDS:
        print("Error: No launchable desktop sessions found.", file=sys.stderr); sys.exit(1)
    try: curses.wrapper(TTYSafeLock().run)
    except SystemExit as e:
        if e.code != 0: print(f"Exited with code {e.code}", file=sys.stderr)
    except Exception as e:
        curses.endwin(); print(f"An unexpected error occurred: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()

