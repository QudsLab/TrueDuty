"""Input counters, active window, screenshots. Everything is local until the user starts the timer."""
import io, os, sys, time, shutil, subprocess, threading, platform

OS = platform.system()

class InputMonitor:
    """Counts key presses / mouse events only (never which keys). Falls back to pointer polling."""
    def __init__(self, tk_root=None):
        self.keys = 0; self.mouse = 0; self.last = time.time(); self.ok = False; self.root = tk_root; self._lk = threading.Lock(); self._pos = None
        try:
            from pynput import keyboard, mouse
            self._kl = keyboard.Listener(on_press=self._k); self._ml = mouse.Listener(on_move=self._m, on_click=self._m, on_scroll=self._m)
            self._kl.daemon = self._ml.daemon = True; self._kl.start(); self._ml.start(); self.ok = True
        except Exception:
            self.ok = False
    def _k(self, *a):
        with self._lk: self.keys += 1; self.last = time.time()
    def _m(self, *a):
        with self._lk: self.mouse += 1; self.last = time.time()
    def poll_pointer(self):
        """Fallback (no pynput, e.g. Wayland): detect pointer movement via Tk."""
        if self.ok or not self.root: return
        try:
            p = self.root.winfo_pointerxy()
            if self._pos is not None and p != self._pos:
                with self._lk: self.mouse += 1; self.last = time.time()
            self._pos = p
        except Exception: pass
    def take(self):
        with self._lk:
            k, m = self.keys, self.mouse; self.keys = self.mouse = 0; return k, m
    def idle_secs(self): return time.time() - self.last

def active_window():
    """-> (app, title). Best effort, empty strings if unavailable."""
    try:
        if OS == 'Windows':
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32; k = ctypes.windll.kernel32
            h = u.GetForegroundWindow(); n = u.GetWindowTextLengthW(h); buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
            pid = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            ph = k.OpenProcess(0x1000, False, pid.value); app = ''
            if ph:
                sz = wintypes.DWORD(260); b2 = ctypes.create_unicode_buffer(260)
                if k.QueryFullProcessImageNameW(ph, 0, b2, ctypes.byref(sz)): app = os.path.basename(b2.value)
                k.CloseHandle(ph)
            return app, buf.value
        if OS == 'Darwin':
            r = subprocess.run(['osascript', '-e', 'tell application "System Events" to get name of first application process whose frontmost is true'], capture_output=True, text=True, timeout=3)
            return r.stdout.strip(), ''
        if shutil.which('xdotool'):
            t = subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'], capture_output=True, text=True, timeout=3).stdout.strip()
            c = subprocess.run(['xdotool', 'getactivewindow', 'getwindowclassname'], capture_output=True, text=True, timeout=3).stdout.strip()
            return c, t
    except Exception: pass
    return '', ''

def screenshot_jpeg(blur=False, maxw=1600, quality=55):
    """-> JPEG bytes of all monitors, or raises."""
    from PIL import Image, ImageFilter
    img = None
    try:
        import mss
        with mss.mss() as s:
            g = s.grab(s.monitors[0]); img = Image.frombytes('RGB', g.size, g.bgra, 'raw', 'BGRX')
    except Exception:
        if OS == 'Linux':                      # Wayland fallbacks
            for cmd in (['grim', '-'], ['gnome-screenshot', '-f', '/dev/stdout'], ['spectacle', '-b', '-n', '-o', '/dev/stdout']):
                if shutil.which(cmd[0]):
                    try:
                        r = subprocess.run(cmd, capture_output=True, timeout=15)
                        if r.returncode == 0 and r.stdout: img = Image.open(io.BytesIO(r.stdout)).convert('RGB'); break
                    except Exception: pass
        if img is None:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True).convert('RGB')
    if img.width > maxw: img = img.resize((maxw, int(img.height * maxw / img.width)))
    if blur: img = img.filter(ImageFilter.GaussianBlur(10))
    b = io.BytesIO(); img.save(b, 'JPEG', quality=quality, optimize=True); return b.getvalue()
