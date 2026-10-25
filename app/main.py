#!/usr/bin/env python3
"""TrueDuty desktop tracker (Windows / Linux / macOS). Works on its own; connects to a TaskDash team when you want.
Run: python main.py"""
import os, sys, json, time, base64, random, queue, platform, threading, collections, webbrowser, calendar, re, socket, secrets, http.server, urllib.parse
import tkinter as tk
import customtkinter as ctk
from net import Client, NetError, KeyChanged, pretty_fp
from store import Store
import tracker

APP = 'TrueDuty'; VERSION = '2.0.0'  # CI replaces this with the release number
OS = platform.system()
HERE = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, 'frozen', False) else __file__))
ASSETS = os.path.join(HERE, 'assets')
# Portable build: the file name contains "portable", or a file named "portable" sits next to it. Data then lives next to the app.
EXE = os.path.abspath(sys.argv[0]) if getattr(sys, 'frozen', False) or '__compiled__' in globals() else ''
PORTABLE = bool(EXE) and ('portable' in os.path.basename(EXE).lower() or os.path.exists(os.path.join(os.path.dirname(EXE), 'portable'))) or os.environ.get('TRUEDUTY_PORTABLE') == '1'
def cfg_dir():
    if PORTABLE: d = os.path.join(os.path.dirname(EXE) if EXE else HERE, 'TrueDuty-data')
    else: d = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~/.config'), APP.lower())
    os.makedirs(d, exist_ok=True); return d
CFG_FILE = os.path.join(cfg_dir(), 'config.json')
def load_cfg():
    try:
        with open(CFG_FILE) as f: return json.load(f)
    except Exception: return {}
def save_cfg(c):
    with open(CFG_FILE, 'w') as f: json.dump(c, f)
    try: os.chmod(CFG_FILE, 0o600)
    except Exception: pass

# Secrets on disk are wrapped with Windows DPAPI (tied to the Windows account). Elsewhere the file is readable only by you.
def protect(b):
    if OS == 'Windows':
        try:
            import ctypes, ctypes.wintypes as w
            class B(ctypes.Structure): _fields_ = [('n', w.DWORD), ('p', ctypes.POINTER(ctypes.c_char))]
            i = B(len(b), ctypes.create_string_buffer(b, len(b))); o = B()
            if ctypes.windll.crypt32.CryptProtectData(ctypes.byref(i), None, None, None, None, 0, ctypes.byref(o)):
                r = ctypes.string_at(o.p, o.n); ctypes.windll.kernel32.LocalFree(o.p); return 'dp:' + base64.b64encode(r).decode()
        except Exception: pass
    return 'b64:' + base64.b64encode(b).decode()
def unprotect(s):
    if not s: return b''
    kind, _, v = s.partition(':'); raw = base64.b64decode(v)
    if kind == 'dp':
        import ctypes, ctypes.wintypes as w
        class B(ctypes.Structure): _fields_ = [('n', w.DWORD), ('p', ctypes.POINTER(ctypes.c_char))]
        i = B(len(raw), ctypes.create_string_buffer(raw, len(raw))); o = B()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(i), None, None, None, None, 0, ctypes.byref(o)): raise ValueError('cannot read the device key')
        r = ctypes.string_at(o.p, o.n); ctypes.windll.kernel32.LocalFree(o.p); return r
    return raw

def local_midnight(ts=None):
    t = time.localtime(ts or time.time()); return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)))
def tzmin(): return -(time.altzone if time.daylight and time.localtime().tm_isdst > 0 else time.timezone) // 60
def hms(s): s = max(0, int(s)); return f'{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}'
def hm(s): s = max(0, int(s)); return f'{s//3600}h {s%3600//60:02d}m'
def clock_of(t): return time.strftime('%H:%M', time.localtime(t))
LOCAL_POLICY = {'idle_max': 10, 'idle_policy': 'max', 'break_limit': 0, 'gap_fill': True, 'daily_target': 8, 'break_used': 0,
                'shots': {'allowed': False, 'mode': 'off', 'consent': False, 'team_mode': 'off', 'interval': 10, 'pause_until': 0, 'pause_allowed': False}}


class Engine:
    """Tracks into the local database, keeps the signed log, and syncs with the server when one is connected."""
    def __init__(self, ev):
        self.ev = ev; self.cfg = load_cfg(); self.store = Store(os.path.join(cfg_dir(), 'trueduty.db'))
        self.client = None; self.lock = threading.Lock(); self.inp = None; self.stop_flag = False; self.ev_root = None
        self.online = False; self.act = collections.deque(maxlen=120); self.last_min = 0; self.next_shot = 0; self.win_start = 0
        self.policy = dict(LOCAL_POLICY, **(self.cfg.get('policy') or {})); self.rules = self.cfg.get('rules') or []
        self.idle_gap = None; self.auto_resume = False; self.chain_ok = True; self.last_sync = 0; self.last_reason = ''; self.today_server = None
        self.last_shot = 0; self.last_pause_note = 0; self.wake = threading.Event(); self.sync_lock = threading.Lock()
        self.attach(); threading.Thread(target=self.sync_worker, daemon=True).start()
    # ---- connection state ----
    @property
    def connected(self): return bool(self.cfg.get('token') and self.cfg.get('server'))
    def attach(self):
        if self.connected:
            try: self.store.attach(self.cfg.get('device_id'), unprotect(self.cfg.get('device_key', '')))
            except Exception: self.store.attach(None, None)
        else: self.store.attach(None, None)
    def token(self):
        try: return unprotect(self.cfg.get('token', '')).decode()
        except Exception: return ''
    def call(self, path, body=None, tok=True, endpoint='/sec/msg'):
        with self.lock:
            if not self.client: self.client = Client(self.cfg['server'], self.cfg.get('pin')); self.client.connect()
            return self.client.call(path, body, self.token() if tok else None, endpoint)
    def open_server(self, url, trust_cb):
        c = Client(url); base = c.base
        c = Client(base, self.cfg.get('pin') if self.cfg.get('server') == base else None); fp = c.connect()
        if self.cfg.get('server') != base or not self.cfg.get('pin'):
            if not trust_cb(pretty_fp(fp)): raise NetError('Connection cancelled.')
        self.client = c; self.cfg['pending_server'] = base; self.cfg['pending_pin'] = c.pin; return fp
    def login(self, body):
        with self.lock: r = self.client.call('/connect', dict(body, name=platform.node() or 'computer', platform=platform.system()), None)
        self.finish(r)
    def browser_begin(self):
        """Browser sign-in. A one-shot web server listens on 127.0.0.1 only. The person signs in on the website (Google or
        e-mail and password) and approves; the website sends the browser to http://127.0.0.1:<port>/callback with a one-time
        grant and our state. The grant is then checked by the server over the encrypted channel before anything is saved."""
        state = secrets.token_urlsafe(18); got = {}; ev = threading.Event()
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
                ok = u.path == '/callback' and q.get('state', [''])[0] == state and q.get('grant')
                if ok and not ev.is_set(): got['grant'] = q['grant'][0]; ev.set()
                body = ('<!doctype html><meta charset="utf-8"><title>TrueDuty</title><body style="font:16px system-ui;background:#0b0e0d;color:#f4f8f6;display:grid;place-items:center;height:90vh">'
                        '<div style="text-align:center"><h2>' + ('TrueDuty is finishing sign-in' if ok else 'This link is not for this app') + '</h2><p style="color:#bec9c4">'
                        + ('You can close this tab and go back to the app.' if ok else 'Start again from TrueDuty.') + '</p></div>').encode()
                self.send_response(200 if ok else 400); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(body)
        srv = http.server.HTTPServer(('127.0.0.1', 0), H); srv.timeout = 1
        def serve():
            while not ev.is_set() and not getattr(srv, 'done', False): srv.handle_request()
        threading.Thread(target=serve, daemon=True).start()
        with self.lock: r = self.client.call('/connect/begin', {'name': platform.node() or 'computer', 'platform': platform.system(), 'port': srv.server_address[1], 'state': state}, None)
        r.update(_srv=srv, _ev=ev, _got=got); return r
    def browser_wait(self, r, give_up):
        """Wait for the local callback (or, if the browser could not reach it, for the approval by polling). -> True when connected."""
        t0 = time.time(); last_poll = 0
        try:
            while time.time() - t0 < r.get('expires', 600) and not give_up():
                if r['_ev'].wait(1):
                    with self.lock: res = self.client.call('/connect/grant', {'nonce': r['nonce'], 'grant': r['_got']['grant']}, None)
                    self.finish(res); return True
                if time.time() - last_poll > 6:
                    last_poll = time.time()
                    with self.lock: res = self.client.call('/connect/poll', {'nonce': r['nonce']}, None)
                    if not res.get('pending'): self.finish(res); return True
            return False
        finally:
            r['_srv'].done = True
            try: r['_srv'].server_close()
            except Exception: pass
    def finish(self, r):
        if self.running(): self.stop('stopped')
        self.cfg.update(server=self.cfg.pop('pending_server'), pin=self.cfg.pop('pending_pin'), token=protect(r['token'].encode()),
                        device_key=protect(bytes.fromhex(r['device_key'])), device_id=str(r['device_id']), user=r['name'], email=r['email'])
        if r.get('team'): self.cfg['team'] = r['team']
        save_cfg(self.cfg); self.attach(); self.refresh()
    def disconnect(self):
        try:
            if self.connected: self.sync(); self.call('/logout')
        except Exception: pass
        if self.running(): self.stop('stopped')
        for k in ('token', 'device_key', 'device_id', 'pin', 'user', 'team', 'policy', 'rules', 'projects', 'role'): self.cfg.pop(k, None)
        save_cfg(self.cfg); self.client = None; self.attach(); self.policy = dict(LOCAL_POLICY); self.rules = []; self.online = False
    # ---- server config and sync ----
    def refresh(self):
        c = self.call('/config', {'since': local_midnight()})
        self.cfg.update(projects=c['projects'], rules=c['rules'], policy=c['policy'], team=c['team'], user=c['user']['name'], role=c['user']['role'], upload=c.get('upload', '/sec/msg'))
        save_cfg(self.cfg); self.policy = dict(LOCAL_POLICY, **c['policy']); self.rules = c['rules']; self.chain_ok = c['chain']['ok']; self.online = True
        self.ev('config', None); return c
    def live(self):
        e = self.running(); b = self.store.on_break()
        if e: return {'state': 'working', 'project_id': e['project_id'], 'since': e['start']}
        if b: return {'state': 'break', 'since': b['start']}
        return {'state': '', 'reason': self.last_reason}
    def reachable(self):
        """Cheap check before syncing: can a TCP connection to the server be opened? No data is sent."""
        try:
            u = urllib.parse.urlparse(self.cfg.get('server', '')); host = u.hostname
            if not host: return False
            with socket.create_connection((host, u.port or (443 if u.scheme == 'https' else 80)), timeout=4): return True
        except OSError: return False
    def kick(self): self.wake.set()
    def sync_worker(self):
        """Uploads in the background. With no network it keeps everything on this computer and checks again every 15 s
        (backing off to 2 minutes); as soon as the server answers, the waiting records go up. Nothing is dropped meanwhile."""
        wait = 15
        while not self.stop_flag:
            self.wake.wait(30 if self.online else wait); self.wake.clear()
            if self.stop_flag or not self.connected: continue
            if not self.reachable():
                if self.online: self.online = False; self.ev('tick', None)
                wait = min(120, wait * 2); continue
            wait = 15; self.sync()
    def sync(self):
        if not self.connected: return
        with self.sync_lock: self._sync()
    def _sync(self):
        try:
            for _ in range(10):
                log = self.store.pending(400)
                r = self.call('/sync', {'since': local_midnight(), 'log': log, 'live': self.live()})
                self.store.acked(r['acked']); self.online = True; self.last_sync = time.time(); self.today_server = r['today']
                self.policy = dict(LOCAL_POLICY, **r['policy']); self.cfg['policy'] = r['policy']
                if not r['chain_ok'] and self.chain_ok: self.chain_ok = False; self.ev('chain', r.get('broken_at'))
                for n in r.get('notices', []): self.ev('notice', n)
                if len(log) < 400 or not r['chain_ok']: break
            self.ev('tick', None)
        except KeyChanged: raise
        except NetError as e:
            if 'not authorized' in str(e) or 'disabled' in str(e): self.ev('revoked', str(e)); self.disconnect(); return
            self.online = False; self.client = None if 'expired' in str(e) else self.client
    # ---- projects ----
    def projects(self):
        return self.cfg.get('projects') or [] if self.connected else self.store.projects()
    def running(self): return self.store.running()
    # ---- tracking ----
    def _arm(self):
        self.last_min = int(time.time() // 60) * 60; self.win_start = time.time(); self._plan_shot()
        if not self.inp: self.inp = tracker.InputMonitor(self.ev_root)
        self.inp.take(); self.inp.last = time.time()
    def start(self, project_id, project):
        self.store.stop_break(); self.auto_resume = False; self.idle_gap = None
        self.store.start_entry(project_id, project, team=self.cfg.get('team', '') if self.connected else '')
        self._arm(); self.last_reason = ''; self.ev('state', None); self.kick()
    def stop(self, reason='stopped', at=None):
        e = self.running()
        if not e: return
        self.store.touch_entry(e['uid'], at or time.time(), running=False); self.last_reason = reason; self.auto_resume = False
        self.ev('state', None); self.kick()
    def break_start(self):
        e = self.running()
        if e: self.store.touch_entry(e['uid'], time.time(), running=False)
        self.store.start_break(); self.last_reason = 'break'; self.ev('state', None); self.kick()
    def break_stop(self, resume=None):
        self.store.stop_break()
        if resume: self.start(*resume)
        else: self.ev('state', None); self.kick()
    def _plan_shot(self):
        iv = max(1, int(self.policy['shots'].get('interval') or 10)) * 60; self.next_shot = self.win_start + random.uniform(0.1, 0.9) * iv
    def shots_on(self):
        s = self.policy['shots']; return self.connected and s.get('allowed') and not (s.get('pause_until') and s['pause_until'] > time.time())
    def take_shot(self):
        try:
            mode = self.policy['shots'].get('mode', 'on'); jpg = tracker.screenshot_jpeg(blur=(mode == 'blur'))
            iv = max(1, int(self.policy['shots'].get('interval') or 10)); act = list(self.act)[-iv:]; pct = round(100 * sum(act) / len(act)) if act else 0
            body = {'jpg': base64.b64encode(jpg).decode(), 'pct': pct}
            try: self.call('/shot', body, endpoint=self.cfg.get('upload', '/sec/msg'))
            except NetError as e:
                if '404' in str(e) or 'not found' in str(e).lower(): self.refresh(); self.call('/shot', body, endpoint=self.cfg.get('upload'))
                else: raise
            self.last_shot = time.time(); self.ev('shot', mode)
        except NetError as e: self.ev('error', 'Screenshot not sent: ' + str(e))
        except Exception as e: self.ev('error', 'Screenshot failed: ' + str(e))
    def pause_shots(self, minutes):
        r = self.call('/ss/pause', {'minutes': minutes}); self.policy['shots']['pause_until'] = r['pause_until']; self.ev('state', None); return r
    def go_idle(self):
        """The team's idle rule decides how much of the idle stretch still counts. The rest becomes a gap."""
        e = self.running(); last = self.inp.last; lim = int(self.policy['idle_max']) * 60; pol = self.policy['idle_policy']
        credit = max(e['start'], last + lim if pol == 'max' else last)
        self.store.touch_entry(e['uid'], credit, running=False); self.store.cut_activity(e['uid'], credit)
        now = time.time(); gap = self.store.add_gap(credit, now) if now - credit >= 60 else None
        self.idle_gap = gap; self.auto_resume = pol == 'auto'; self.last_reason = 'idle'
        self.ev('idle', {'policy': pol, 'mins': int((now - last) // 60), 'gap': gap}); self.kick()
    def fill_gap(self, uid, project_id, project): self.store.add_gap_entry(uid, project_id, project); self.ev('gaps', None); self.kick()
    def dismiss_gap(self, uid): self.store.dismiss_gap(uid); self.ev('gaps', None); self.kick()
    def change_password(self, old, new): self.call('/password', {'old': old, 'code': old, 'new': new})
    def loop(self):
        tick = 0
        while not self.stop_flag:
            time.sleep(1); tick += 1
            try:
                if self.inp: self.inp.poll_pointer()
                e = self.running(); now = time.time()
                if not e:
                    if self.idle_gap and self.inp and self.inp.idle_secs() < 3:          # back from idle: close the growing gap
                        self.store.grow_gap(self.idle_gap, now)
                        if self.auto_resume and self.cfg.get('project_id'):
                            g = self.idle_gap; self.idle_gap = None; self.start(self.cfg['project_id'], self.cfg.get('project', '')); self.ev('resumed', g)
                        else: self.idle_gap = None
                    if self.store.on_break() and tick % 30 == 0: self.store.touch_break()
                    continue
                if not self.inp: self._arm()
                if int(now // 60) * 60 != self.last_min:                                # minute boundary: store the finished minute
                    n = self.inp.take(); app, title = tracker.active_window()
                    if not self.cfg.get('titles', True): title = ''
                    self.store.add_minute(e['uid'], self.last_min, n, app, title); self.act.append(round(n['as'] / 60, 2) if n['as'] else (1 if n['k'] + n['m'] else 0))
                    self.last_min = int(now // 60) * 60; self.store.touch_entry(e['uid'], now, True, log=(tick % 300 < 60)); self.ev('activity', list(self.act)[-10:])
                lim = int(self.policy.get('idle_max') or 0) * 60
                if lim and self.inp.idle_secs() > lim: self.go_idle(); continue
                s = self.policy['shots']
                if s.get('pause_until') and s['pause_until'] > now and now - self.last_pause_note > 1800: self.last_pause_note = now; self.ev('ss_reminder', None)
                if self.shots_on() and now >= self.next_shot:
                    if self.online: threading.Thread(target=self.take_shot, daemon=True).start()
                    self.win_start += max(1, int(s.get('interval') or 10)) * 60
                    if self.win_start < now - 600: self.win_start = now
                    self._plan_shot()
            except KeyChanged as x: self.ev('error', str(x))
            except Exception as x: self.ev('error', str(x))

# ---------------- look ----------------
# Two independent switches: dark or light, and color or grayscale. Each colour is (light, dark).
PAL = {
 'color': dict(BG=('#EEF2F0', '#0B0E0D'), PANEL=('#FFFFFF', '#161C1A'), PANEL2=('#E1E8E4', '#212A27'), LINE=('#B9C6BF', '#3C4A44'), LINE2=('#8FA097', '#5C6D66'),
               INK=('#0B100E', '#F4F8F6'), MUT=('#3B4742', '#BEC9C4'),
               ACC=('#0B7340', '#21EB98'), ACC_H=('#095F35', '#5CF5B6'), ON=('#FFFFFF', '#04261A'), BAD=('#B52F22', '#FF7A6B'), BAD_H=('#962519', '#FF9A8E'), WARN=('#8F5000', '#F7BA5E'),
               WORK=('#0B7340', '#21EB98'), OFF=('#C2571A', '#F0924E'), UNR=('#9FADA6', '#5C6D66')),
 'gray': dict(BG=('#EDEDED', '#0E0E0E'), PANEL=('#FFFFFF', '#1A1A1A'), PANEL2=('#E0E0E0', '#262626'), LINE=('#BDBDBD', '#454545'), LINE2=('#8C8C8C', '#6A6A6A'),
              INK=('#0F0F0F', '#F5F5F5'), MUT=('#474747', '#C2C2C2'),
              ACC=('#1F1F1F', '#F0F0F0'), ACC_H=('#3A3A3A', '#FFFFFF'), ON=('#FAFAFA', '#0E0E0E'), BAD=('#1F1F1F', '#E6E6E6'), BAD_H=('#3A3A3A', '#FFFFFF'), WARN=('#4A4A4A', '#C8C8C8'),
              WORK=('#1F1F1F', '#F0F0F0'), OFF=('#7A7A7A', '#9A9A9A'), UNR=('#B5B5B5', '#555555'))}
C = dict(PAL['color'])
def set_look(mode, tone):
    C.clear(); C.update(PAL['gray' if tone == 'gray' else 'color'])
    ctk.set_appearance_mode(mode if mode in ('light', 'dark') else 'system')
def col(k): t = C[k]; return t[1] if ctk.get_appearance_mode() == 'Dark' else t[0]
FONTS_OK = {'sg': False, 'rm': False}
def load_fonts():
    for key, fn in (('sg', 'SpaceGrotesk-Regular.ttf'), ('sg', 'SpaceGrotesk-Bold.ttf'), ('rm', 'RobotoMono-Regular.ttf'), ('rm', 'RobotoMono-Bold.ttf')):
        try:
            if ctk.FontManager.load_font(os.path.join(ASSETS, 'fonts', fn)): FONTS_OK[key] = True
        except Exception: pass
def font(n=13, b=False): return ctk.CTkFont(family='Space Grotesk' if FONTS_OK['sg'] else None, size=n, weight='bold' if b else 'normal')
def mono(n=13, b=False): return ctk.CTkFont(family='Roboto Mono' if FONTS_OK['rm'] else 'Courier', size=n, weight='bold' if b else 'normal')
_icons = []
def brand_icon(w):
    """CTk sets its own blue icon on every window shortly after it opens, so ours goes on afterwards."""
    def go():
        try:
            if not w.winfo_exists(): return
            if OS == 'Windows': w.iconbitmap(os.path.join(ASSETS, 'icon.ico'))
            else:
                im = tk.PhotoImage(file=os.path.join(ASSETS, 'app-icon.png')); _icons.append(im); w.iconphoto(True, im)
        except Exception: pass
    w.after(300, go); w.after(900, go)

class Seg(ctk.CTkFrame):
    """Segmented control with readable text on the selected item in every look."""
    def __init__(self, parent, values, command=None, height=34, font_=None):
        super().__init__(parent, fg_color=C['PANEL2'], corner_radius=999, height=height + 6, border_width=1, border_color=C['LINE']); self.command = command; self.value = None; self.b = {}
        for i, v in enumerate(values):
            self.columnconfigure(i, weight=1, uniform='s')
            b = ctk.CTkButton(self, text=v, height=height - 2, corner_radius=999, font=font_ or font(13, True), border_width=0, command=lambda v=v: self.pick(v)); b.grid(row=0, column=i, sticky='ew', padx=3, pady=3); self.b[v] = b
    def set(self, v):
        self.value = v
        for k, b in self.b.items():
            on = k == v; b.configure(fg_color=C['ACC'] if on else C['PANEL2'], hover_color=C['ACC_H'] if on else C['LINE'], text_color=C['ON'] if on else C['INK'])
    def get(self): return self.value
    def pick(self, v):
        self.set(v)
        if self.command: self.command(v)

class Dialog(ctk.CTkToplevel):
    """Branded popup with the TrueDuty logo. Used for every message instead of the system message boxes."""
    def __init__(self, ui, title, text='', buttons=(('OK', 'acc', None),), body=None, width=430, on_close=None):
        super().__init__(ui.root, fg_color=C['BG']); self.withdraw(); self.ui = ui; self.on_close = on_close; self.done = False
        self.title(title); self.resizable(False, False); self.transient(ui.root); brand_icon(self)
        pad = ctk.CTkFrame(self, fg_color='transparent'); pad.pack(fill='both', expand=True, padx=26, pady=22)
        head = ctk.CTkFrame(pad, fg_color='transparent'); head.pack(fill='x')
        if ui.logo_s: ctk.CTkLabel(head, image=ui.logo_s, text='').pack(side='left', padx=(0, 12))
        ctk.CTkLabel(head, text=title, font=font(18, True), text_color=C['INK'], anchor='w', justify='left', wraplength=width - 110).pack(side='left', fill='x', expand=True)
        if text: ctk.CTkLabel(pad, text=text, font=font(13), text_color=C['MUT'], anchor='w', justify='left', wraplength=width - 52).pack(fill='x', pady=(14, 0))
        self.box = ctk.CTkFrame(pad, fg_color='transparent', height=0); self.box.pack(fill='x')
        if body: body(self.box, self)
        row = ctk.CTkFrame(pad, fg_color='transparent', height=0); row.pack(fill='x', pady=(20, 0)); self.btns = []
        for label, kind, cb in reversed(buttons):
            b = ui.button(label, (lambda c=cb: self.finish(c)), kind, parent=row, height=40, width=112 if len(buttons) > 1 else 140); b.pack(side='right', padx=(8, 0)); self.btns.append(b)
        self.protocol('WM_DELETE_WINDOW', lambda: self.finish(None)); self.place(width)
    def place(self, width=430):
        self.update_idletasks(); h = self.winfo_reqheight(); r = self.ui.root
        x = r.winfo_rootx() + (r.winfo_width() - width) // 2; y = r.winfo_rooty() + max(30, (r.winfo_height() - h) // 3)
        self.geometry(f'{width}x{h}+{max(0, x)}+{max(0, y)}'); self.deiconify(); self.after(120, self.hold)
    def hold(self):
        try: self.lift(); self.grab_set(); self.focus_force()
        except Exception: pass
    def finish(self, cb):
        if self.done: return
        if cb and cb(self) is False: return
        self.done = True
        try: self.grab_release()
        except Exception: pass
        self.destroy()
        if self.on_close: self.on_close()

class Toast(ctk.CTkToplevel):
    """Small branded notice in the bottom right corner. Fades in, stays a few seconds, fades out."""
    def __init__(self, ui, title, text='', kind='info'):
        super().__init__(ui.root, fg_color=C['LINE']); self.withdraw(); self.ui = ui; self.overrideredirect(True)
        try: self.attributes('-topmost', True); self.attributes('-alpha', 0.0)
        except Exception: pass
        accent = {'info': 'ACC', 'warn': 'WARN', 'bad': 'BAD'}[kind]; w = 350
        card = ctk.CTkFrame(self, fg_color=C['PANEL'], corner_radius=0); card.pack(fill='both', expand=True, padx=1, pady=1)
        ctk.CTkFrame(card, width=5, height=1, fg_color=C[accent], corner_radius=0).pack(side='left', fill='y')
        if ui.logo_m: ctk.CTkLabel(card, image=ui.logo_m, text='').pack(side='left', padx=(14, 4), pady=12, anchor='n')
        tx = ctk.CTkFrame(card, fg_color='transparent'); tx.pack(side='left', fill='both', expand=True, padx=(8, 14), pady=12)
        ctk.CTkLabel(tx, text=title, font=font(14, True), text_color=C['INK'], anchor='w', justify='left', wraplength=w - 100).pack(fill='x')
        if text: ctk.CTkLabel(tx, text=text, font=font(12), text_color=C['MUT'], anchor='w', justify='left', wraplength=w - 100).pack(fill='x', pady=(2, 0))
        for wd in (self, card, tx): wd.bind('<Button-1>', lambda e: self.close())
        self.update_idletasks(); h = self.winfo_reqheight(); self.h = h
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight(); slot = sum(t.h + 10 for t in ui.toasts)
        self.geometry(f'{w}x{h}+{sw - w - 24}+{max(10, sh - h - 70 - slot)}'); ui.toasts.append(self); self.deiconify(); self.fade(0)
        self.after(6500, self.close)
    def fade(self, i):
        try:
            if i <= 8: self.attributes('-alpha', i / 8 * 0.98); self.after(20, lambda: self.fade(i + 1))
        except Exception: pass
    def close(self, i=8):
        try:
            if not self.winfo_exists(): return
            if i <= 0:
                if self in self.ui.toasts: self.ui.toasts.remove(self)
                return self.destroy()
            self.attributes('-alpha', i / 8 * 0.98); self.after(25, lambda: self.close(i - 1))
        except Exception: pass


class UI:
    def __init__(self):
        c0 = load_cfg(); self.mode = c0.get('mode', 'system'); self.tone = c0.get('tone', 'color'); set_look(self.mode, self.tone); load_fonts()
        self.root = ctk.CTk(fg_color=C['BG']); self.root.title(APP); self.root.geometry('470x820'); self.root.minsize(450, 780); brand_icon(self.root)
        self.q = queue.Queue(); self.eng = Engine(lambda k, v: self.q.put((k, v))); self.eng.ev_root = self.root
        self.toasts = []; self.tab = 'Track'; self.period = 'Week'; self.poff = 0; self.listmode = 'Categories'; self.last_ins = 0; self.act = []
        self.load_logos()
        self.body = ctk.CTkFrame(self.root, fg_color='transparent'); self.body.pack(fill='both', expand=True, padx=26, pady=22)
        threading.Thread(target=self.eng.loop, daemon=True).start()
        self.root.after(200, self.pump); self.root.after(1000, self.clock); self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.main()
        if self.eng.connected: self.bg(self.eng.refresh, lambda r, e: self.refresh_ui())
    def load_logos(self):
        try:
            from PIL import Image, ImageOps
            def im(name):
                i = Image.open(os.path.join(ASSETS, name)).convert('RGBA')
                if self.tone == 'gray': g = ImageOps.grayscale(i).convert('RGBA'); g.putalpha(i.getchannel('A')); i = g
                return i
            mk = lambda s: ctk.CTkImage(light_image=im('dark.png'), dark_image=im('light.png'), size=s)
            self.logo_img, self.logo_s = mk((62, 42)), mk((44, 30)); m = im('logo.png'); self.logo_m = ctk.CTkImage(light_image=m, dark_image=m, size=(40, 28))
        except Exception: self.logo_img = self.logo_s = self.logo_m = None

    # ---- helpers ----
    def lab(self, text, size=13, color='INK', bold=False, parent=None, **kw):
        return ctk.CTkLabel(parent or self.body, text=text, font=font(size, bold), text_color=C[color], anchor='w', justify='left', **kw)
    def entry(self, ph='', parent=None, **kw):
        return ctk.CTkEntry(parent or self.body, placeholder_text=ph, height=kw.pop('height', 42), corner_radius=10, border_width=2, border_color=C['LINE'], fg_color=C['PANEL'], text_color=C['INK'],
                            placeholder_text_color=C['MUT'], **{'font': font(13), **kw})
    def button(self, text, cmd, kind='acc', parent=None, **kw):
        c = {'acc': dict(fg_color=C['ACC'], hover_color=C['ACC_H'], text_color=C['ON']), 'bad': dict(fg_color=C['BAD'], hover_color=C['BAD_H'], text_color=C['ON']),
             'ghost': dict(fg_color=C['PANEL'], hover_color=C['PANEL2'], text_color=C['INK'], border_width=2, border_color=C['LINE2'])}[kind]
        return ctk.CTkButton(parent or self.body, text=text, command=cmd, height=kw.pop('height', 44), corner_radius=999, font=font(14, True), **c, **kw)
    def switch(self, parent, text, var, sub=''):
        f = ctk.CTkFrame(parent, fg_color='transparent'); f.pack(fill='x', pady=5)
        ctk.CTkSwitch(f, text='', variable=var, width=46, height=24, switch_width=46, switch_height=24, progress_color=C['ACC'], button_color=('#FFFFFF', '#F4F8F6'), button_hover_color=('#F0F0F0', '#FFFFFF'), fg_color=C['LINE2']).pack(side='left', anchor='n', pady=2)
        t = ctk.CTkFrame(f, fg_color='transparent'); t.pack(side='left', fill='x', expand=True, padx=(8, 0))
        self.lab(text, 13, bold=True, parent=t).pack(anchor='w')
        if sub: self.lab(sub, 11, 'MUT', parent=t, wraplength=320).pack(anchor='w')
        return f
    def bg(self, fn, done=None):
        def run():
            try: r = fn(); self.q.put(('done', (done, r, None)))
            except Exception as e: self.q.put(('done', (done, None, e)))
        threading.Thread(target=run, daemon=True).start()
    def alive(self, w):
        try: return w is not None and w.winfo_exists()
        except Exception: return False
    def alert(self, title, text=''): Dialog(self, title, text)
    def confirm(self, title, text, ok, cb, danger=False, no='Cancel'):
        Dialog(self, title, text, buttons=((no, 'ghost', None), (ok, 'bad' if danger else 'acc', lambda d: cb())))
    def toast(self, title, text='', kind='info'):
        try: Toast(self, title, text, kind)
        except Exception: pass

    # ---- main window ----
    def main(self):
        for w in self.body.winfo_children(): w.destroy()
        e = self.eng; top = ctk.CTkFrame(self.body, fg_color='transparent'); top.pack(fill='x')
        if self.logo_img: ctk.CTkLabel(top, image=self.logo_img, text='').pack(side='left')
        who = ctk.CTkFrame(top, fg_color='transparent'); who.pack(side='right')
        if e.connected:
            self.lab(e.cfg.get('user', ''), 13, bold=True, parent=who).pack(anchor='e'); self.lab(f"{e.cfg.get('role', '')} at {e.cfg.get('team', '')}".strip(), 11, 'MUT', parent=who).pack(anchor='e')
        else:
            self.lab('Local mode', 13, bold=True, parent=who).pack(anchor='e'); self.lab('Your time stays on this computer', 11, 'MUT', parent=who).pack(anchor='e')
        self.tabs = Seg(self.body, ['Track', 'Insights'], self.set_tab); self.tabs.set(self.tab); self.tabs.pack(fill='x', pady=(16, 12))
        bf = ctk.CTkFrame(self.body, fg_color='transparent', height=0); bf.pack(side='bottom', fill='x', pady=(10, 0))
        self.button('Settings', self.settings, 'ghost', parent=bf, height=36, width=110).pack(side='left')
        if not e.connected: self.button('Connect to a team', self.connect_dialog, 'ghost', parent=bf, height=36, width=170).pack(side='right')
        self.page = ctk.CTkFrame(self.body, fg_color='transparent'); self.page.pack(fill='both', expand=True)
        self.show_tab()
    def set_tab(self, v): self.tab = v; self.show_tab()
    def show_tab(self):
        for w in self.page.winfo_children(): w.destroy()
        self.ringc = self.btn = self.brk = self.bars = self.stat = self.shotl = self.gapbox = self.proj = self.sub = self.ins = None
        (self.track if self.tab == 'Track' else self.insights)()
    def refresh_ui(self):
        if self.tab == 'Track' and self.alive(self.proj): self.main()
        elif self.tab == 'Track': self.state_ui()

    # ---- track ----
    def track(self):
        e = self.eng; p = self.page
        self.ringc = tk.Canvas(p, width=230, height=230, highlightthickness=0, bd=0, bg=col('BG')); self.ringc.pack(pady=(2, 4))
        self.sub = self.lab('', 12, 'MUT', parent=p); self.sub.pack(anchor='center')
        projs = e.projects(); self.proj_names = {x['name']: x['id'] for x in projs}
        self.lab('Project', 12, 'MUT', parent=p).pack(anchor='w', pady=(12, 4))
        self.proj = ctk.CTkOptionMenu(p, values=list(self.proj_names) or ['No projects'], height=44, corner_radius=10, fg_color=C['PANEL2'], button_color=C['LINE'], button_hover_color=C['LINE2'],
                                      text_color=C['INK'], dropdown_fg_color=C['PANEL'], dropdown_text_color=C['INK'], dropdown_hover_color=C['PANEL2'], font=font(13), dropdown_font=font(13), dynamic_resizing=False, anchor='w')
        self.proj.pack(fill='x'); last = e.cfg.get('project'); self.proj.set(last if last in self.proj_names else (list(self.proj_names)[0] if self.proj_names else 'No projects'))
        self.btn = self.button('Start tracking', self.toggle, parent=p, height=52); self.btn.pack(fill='x', pady=(14, 0))
        self.brk = self.button('Take a break', self.toggle_break, 'ghost', parent=p, height=40); self.brk.pack(fill='x', pady=(10, 0))
        self.gapbox = ctk.CTkFrame(p, fg_color='transparent', height=0); self.gapbox.pack(fill='x', pady=(10, 0))
        self.lab('Activity, last 10 minutes', 12, 'MUT', parent=p).pack(anchor='w', pady=(10, 4))
        self.bars = tk.Canvas(p, height=28, highlightthickness=0, bd=0, bg=col('BG')); self.bars.pack(fill='x'); self.draw_bars()
        self.shotl = self.lab('', 12, 'MUT', parent=p, wraplength=410); self.shotl.pack(anchor='w', pady=(10, 0))
        self.stat = self.lab('', 12, 'MUT', parent=p, wraplength=410); self.stat.pack(anchor='w', pady=(2, 0))
        self.state_ui(); self.draw_gaps(); self.draw_ring()
    def today(self):
        e = self.eng; return e.store.secs(local_midnight(), int(time.time()) + 1)
    def draw_ring(self):
        c = self.ringc
        if not self.alive(c): return
        e = self.eng; c.delete('all'); cx = cy = 115; r = 100; run = e.running(); br = e.store.on_break()
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col('LINE'), width=9)
        if run: c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-359.9 * ((time.time() % 60) / 60), style='arc', outline=col('ACC'), width=9)
        elif br:
            used = e.store.break_secs(local_midnight()); lim = int(e.policy.get('break_limit') or 0) * 60
            if lim: c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-359.9 * min(1, used / lim), style='arc', outline=col('BAD' if used > lim else 'WARN'), width=9)
        tgt = float(e.policy.get('daily_target') or 8) * 3600; t = self.today()
        if not run and not br and t: c.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-359.9 * min(1, t / tgt), style='arc', outline=col('ACC'), width=9)
        c.create_text(cx, cy - 28, text='Break' if br else 'Today', font=font(12), fill=col('MUT'))
        c.create_text(cx, cy + 4, text=hms(time.time() - br['start']) if br else hms(t), font=mono(30, True), fill=col('INK'))
        lim = int(e.policy.get('break_limit') or 0)
        c.create_text(cx, cy + 40, text=(f'of {lim} min allowed today' if lim else 'on a break') if br else (f"{int(100 * t / tgt)}% of {e.policy.get('daily_target', 8):g}h"), font=font(12), fill=col('MUT'))
    def draw_bars(self):
        c = self.bars
        if not self.alive(c): return
        c.delete('all'); w = max(c.winfo_width(), 410); n = 10; gap = 5; bw = (w - gap * (n - 1)) / n; data = ([0] * n + self.act)[-n:]
        for i, v in enumerate(data):
            x = i * (bw + gap); c.create_rectangle(x, 26 - max(4, 22 * min(1, v)) if v else 22, x + bw, 26, fill=col('ACC') if v else col('LINE'), width=0)
    def state_ui(self):
        e = self.eng
        if not self.alive(self.btn): return
        run = e.running(); br = e.store.on_break()
        if br: self.btn.configure(text='End break and resume', fg_color=C['ACC'], hover_color=C['ACC_H'], text_color=C['ON'])
        else: self.btn.configure(text='Stop' if run else 'Start tracking', fg_color=C['BAD' if run else 'ACC'], hover_color=C['BAD_H' if run else 'ACC_H'], text_color=C['ON'])
        self.proj.configure(state='disabled' if run else 'normal')
        self.brk.configure(text='On a break' if br else 'Take a break', state='disabled' if br else 'normal')
        s = e.policy['shots']
        if not e.connected: msg, color = 'Local mode. Nothing leaves this computer.', 'MUT'
        elif not e.chain_ok: msg, color = 'The server flagged this device. Disconnect and connect again in Settings.', 'BAD'
        elif not e.online: msg, color = f'No network. {e.store.unsent()} records are saved here and go up when the connection is back.', 'WARN'
        elif not s.get('allowed') and s.get('team_mode', 'off') != 'off' and not s.get('consent'): msg, color = 'Your team allows screenshots. None are taken until you agree in Privacy on the web panel.', 'MUT'
        elif not s.get('allowed'): msg, color = 'No screenshots are taken.', 'MUT'
        elif s.get('pause_until') and s['pause_until'] > time.time(): msg, color = f"Screenshots paused until {clock_of(s['pause_until'])}. Your admins can see the pause.", 'WARN'
        else: msg, color = f"Screenshots about every {s.get('interval', 10)} min" + (', blurred' if s.get('mode') == 'blur' else '') + f", kept {s.get('retention_days', 60)} days.", 'MUT'
        self.stat.configure(text=msg, text_color=C[color])
    def draw_gaps(self):
        g = self.gapbox
        if not self.alive(g): return
        for w in g.winfo_children(): w.destroy()
        e = self.eng; gaps = e.store.open_gaps()
        if not gaps or not e.policy.get('gap_fill', True): return
        x = gaps[0]; card = ctk.CTkFrame(g, fg_color=C['PANEL'], corner_radius=14, border_width=1, border_color=C['LINE']); card.pack(fill='x')
        mins = max(1, int((x['stop'] - x['start']) // 60)); more = len(gaps) - 1
        self.lab(f'{mins} minutes without activity', 13, bold=True, parent=card).pack(anchor='w', padx=14, pady=(12, 0))
        self.lab(f"{clock_of(x['start'])} to {clock_of(x['stop'])}. Add it if you were working away from the computer." + (f' {more} more waiting.' if more else ''), 11, 'MUT', parent=card, wraplength=380).pack(anchor='w', padx=14, pady=(2, 8))
        r = ctk.CTkFrame(card, fg_color='transparent'); r.pack(fill='x', padx=14, pady=(0, 12))
        self.button('Add to my time', lambda: self.fill_gap(x), parent=r, height=34, width=140).pack(side='left')
        self.button('Dismiss', lambda: self.eng.dismiss_gap(x['uid']), 'ghost', parent=r, height=34, width=90).pack(side='left', padx=8)
    def cur_project(self):
        name = self.proj.get() if self.alive(self.proj) else self.eng.cfg.get('project')
        pid = self.proj_names.get(name) if hasattr(self, 'proj_names') else None
        return (pid, name) if pid else (None, None)
    def fill_gap(self, x):
        pid, name = self.cur_project()
        if not pid: return self.alert('Choose a project', 'Pick a project first so the time has a place to go.')
        self.eng.fill_gap(x['uid'], pid, name); self.toast('Time added', f"{int((x['stop'] - x['start']) // 60)} minutes added to your day.")
    def toggle(self):
        e = self.eng
        if e.store.on_break():
            pid, name = self.cur_project(); return e.break_stop((pid, name) if pid else None)
        if e.running(): return e.stop('stopped')
        pid, name = self.cur_project()
        if not pid: return self.alert('Choose a project first', 'Ask your admin to create one, or add one in Settings when you track locally.')
        e.cfg['project'] = name; e.cfg['project_id'] = pid; save_cfg(e.cfg); e.start(pid, name)
    def toggle_break(self):
        e = self.eng; lim = int(e.policy.get('break_limit') or 0); used = e.store.break_secs(local_midnight()) // 60
        txt = ('Your timer stops while you are away. ' + (f'Your team allows {lim} minutes of breaks a day, {used} used so far. Going over is never blocked; admins are just told.' if lim else 'Your team sees that you are on a break.')) if e.connected else 'Your timer stops while you are away. Breaks show up in Insights.'
        self.confirm('Take a break?', txt, 'Start break', e.break_start)

    # ---- insights (fits the window, no scrolling) ----
    def insights(self):
        p = self.page; self.ins = p
        Seg(p, ['Day', 'Week', 'Month', 'Year', 'Custom'], self.set_period, height=30, font_=font(12, True)).pack(fill='x'); p.winfo_children()[-1].set(self.period)
        nav = ctk.CTkFrame(p, fg_color='transparent'); nav.pack(fill='x', pady=(8, 0))
        if self.period == 'Custom':
            self.ca = self.entry('2026-10-01', parent=nav, width=120, height=34); self.cb = self.entry('2026-10-25', parent=nav, width=120, height=34)
            self.ca.insert(0, getattr(self, 'cust_a', time.strftime('%Y-%m-%d', time.localtime(time.time() - 29 * 86400)))); self.cb.insert(0, getattr(self, 'cust_b', time.strftime('%Y-%m-%d')))
            self.ca.pack(side='left'); self.lab('to', 12, 'MUT', parent=nav).pack(side='left', padx=8); self.cb.pack(side='left')
            self.button('Apply', self.apply_custom, parent=nav, height=34, width=80).pack(side='right')
        else:
            self.button('<', lambda: self.shift(-1), 'ghost', parent=nav, height=30, width=36).pack(side='left')
            self.button('>', lambda: self.shift(1), 'ghost', parent=nav, height=30, width=36, state='disabled' if self.poff >= 0 else 'normal').pack(side='right')
            self.plabel = self.lab('', 13, bold=True, parent=nav); self.plabel.pack(side='top', anchor='center', pady=4)
        a, b, label, kind = self.range()
        if self.period != 'Custom': self.plabel.configure(text=label)
        u = self.eng.store.usage(a, b, self.eng.rules, tzmin())
        tiles = ctk.CTkFrame(p, fg_color='transparent'); tiles.pack(fill='x', pady=(10, 0)); tiles.columnconfigure((0, 1, 2), weight=1, uniform='t')
        for i, (v, l) in enumerate(((hm(u['secs']), 'Tracked'), ('-' if u['prod'] is None else f"{u['prod']}%", 'Work-related'), (f"{u['activity']}%", 'Activity'))):
            f = ctk.CTkFrame(tiles, fg_color=C['PANEL'], corner_radius=14, border_width=1, border_color=C['LINE2']); f.grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 4, 0 if i == 2 else 4))
            ctk.CTkLabel(f, text=v, font=mono(16, True), text_color=C['INK']).pack(pady=(10, 0)); ctk.CTkLabel(f, text=l, font=font(11), text_color=C['MUT']).pack(pady=(0, 10))
        cv = tk.Canvas(p, height=170, highlightthickness=0, bd=0, bg=col('BG')); cv.pack(fill='x', pady=(12, 0))
        cv.update_idletasks(); self.chart(cv, u, a, b, kind)
        lg = ctk.CTkFrame(p, fg_color='transparent'); lg.pack(anchor='w', pady=(4, 0))
        for k, t in (('WORK', 'Work'), ('OFF', 'Not work'), ('UNR', 'Unrated')):
            ctk.CTkFrame(lg, width=10, height=10, fg_color=C[k], corner_radius=3).pack(side='left', padx=(0, 5)); self.lab(t, 11, 'MUT', parent=lg).pack(side='left', padx=(0, 12))
        sw = Seg(p, ['Categories', 'Apps'], self.set_list, height=28, font_=font(12, True)); sw.pack(fill='x', pady=(10, 4)); sw.set(self.listmode)
        rows = [(c['category'], c['secs'], 'WORK' if c['category'] not in ('Entertainment', 'Other') else ('OFF' if c['category'] == 'Entertainment' else 'UNR')) for c in u['cats']] if self.listmode == 'Categories' \
            else [(a_['label'], a_['secs'], {'work': 'WORK', 'off': 'OFF'}.get(a_['cls'], 'UNR')) for a_ in u['apps']]
        if not rows: self.lab('Nothing tracked in this period yet.', 12, 'MUT', parent=p).pack(anchor='w', pady=8)
        mx = max([r[1] for r in rows] or [1])
        for name, secs, key in rows[:5]:
            r = ctk.CTkFrame(p, fg_color='transparent'); r.pack(fill='x', pady=2); r.columnconfigure(1, weight=1)
            self.lab(name[:20], 12, parent=r, width=130).grid(row=0, column=0, sticky='w')
            pb = ctk.CTkProgressBar(r, height=8, corner_radius=4, fg_color=C['PANEL2'], progress_color=C[key]); pb.set(max(0.03, secs / mx)); pb.grid(row=0, column=1, sticky='ew', padx=8)
            self.lab(hm(secs), 11, 'MUT', parent=r).grid(row=0, column=2)
    def set_period(self, v): self.period = v; self.poff = 0; self.show_tab()
    def set_list(self, v): self.listmode = v; self.show_tab()
    def shift(self, d): self.poff = min(0, self.poff + d); self.show_tab()
    def apply_custom(self):
        self.cust_a, self.cust_b = self.ca.get().strip(), self.cb.get().strip(); self.show_tab()
    def range(self):
        lt = time.localtime(); o = self.poff
        if self.period == 'Day':
            a = local_midnight(time.time() + o * 86400); return a, a + 86400, time.strftime('%A %d %b', time.localtime(a)), 'hours'
        if self.period == 'Week':
            d0 = local_midnight() - lt.tm_wday * 86400 + o * 7 * 86400; return d0, d0 + 7 * 86400, 'Week of ' + time.strftime('%d %b', time.localtime(d0)), 'days'
        if self.period == 'Month':
            y, m = lt.tm_year, lt.tm_mon + o
            while m < 1: m += 12; y -= 1
            a = int(time.mktime((y, m, 1, 0, 0, 0, 0, 0, -1))); b = int(time.mktime((y + (m == 12), m % 12 + 1, 1, 0, 0, 0, 0, 0, -1)))
            return a, b, time.strftime('%B %Y', time.localtime(a)), 'line'
        if self.period == 'Year':
            y = lt.tm_year + o; return int(time.mktime((y, 1, 1, 0, 0, 0, 0, 0, -1))), int(time.mktime((y + 1, 1, 1, 0, 0, 0, 0, 0, -1))), str(y), 'weeks'
        try:
            a = int(time.mktime(time.strptime(getattr(self, 'cust_a', ''), '%Y-%m-%d'))); b = int(time.mktime(time.strptime(getattr(self, 'cust_b', ''), '%Y-%m-%d'))) + 86400
        except ValueError:
            b = local_midnight() + 86400; a = b - 30 * 86400
        if b <= a: b = a + 86400
        return a, b, '', 'days' if b - a <= 15 * 86400 else ('line' if b - a <= 120 * 86400 else 'weeks')
    def chart(self, cv, u, a, b, kind):
        W = max(cv.winfo_width(), 418); H = 170; B = 18; T = 20; ph = H - B - T
        if kind == 'hours':
            rows = [dict(u['hours'][h], label=f'{h:02d}' if h % 6 == 0 else '') for h in range(24)]
        else:
            rows = []; t = a
            while t < b and len(rows) < 400:
                k = time.strftime('%Y-%m-%d', time.localtime(t + 43200)); d = u['days'].get(k, {'work': 0, 'off': 0, 'new': 0})
                rows.append({'work': d['work'], 'off': d['off'], 'new': d['new'], 'label': time.strftime('%a' if kind == 'days' and b - a <= 8 * 86400 else '%d', time.localtime(t + 43200))}); t += 86400
            if kind == 'weeks':
                wk = []
                for i in range(0, len(rows), 7):
                    ch = rows[i:i + 7]; wk.append({'work': sum(x['work'] for x in ch), 'off': sum(x['off'] for x in ch), 'new': sum(x['new'] for x in ch), 'label': time.strftime('%b', time.localtime(a + i * 86400 + 43200)) if (i // 7) % 5 == 0 else ''})
                rows = wk
        n = len(rows) or 1; mx = max([r['work'] + r['off'] + r['new'] for r in rows] + [600])
        cv.create_line(0, H - B, W, H - B, fill=col('LINE'))
        if kind in ('hours', 'days'):
            bw = W / n; gw = max(2, min(bw * 0.62, 34))
            for i, r in enumerate(rows):
                x = bw * i + (bw - gw) / 2; y = H - B
                for k, key in (('work', 'WORK'), ('off', 'OFF'), ('new', 'UNR')):
                    h = ph * r[k] / mx
                    if h > 0: cv.create_rectangle(x, y - h, x + gw, y, fill=col(key), width=0); y -= h
                if r['label'] and (n <= 14 or i % max(1, n // 8) == 0 or kind == 'hours'): cv.create_text(x + gw / 2, H - 7, text=r['label'], font=font(9), fill=col('MUT'))
        else:
            X = lambda i: (W - 8) * i / max(1, n - 1) + 4; Y = lambda v: H - B - ph * v / mx
            for lo, hi, key in ((lambda r: 0, lambda r: r['work'], 'WORK'), (lambda r: r['work'], lambda r: r['work'] + r['off'], 'OFF'), (lambda r: r['work'] + r['off'], lambda r: r['work'] + r['off'] + r['new'], 'UNR')):
                pts = [(X(i), Y(hi(r))) for i, r in enumerate(rows)] + [(X(i), Y(lo(r))) for i, r in reversed(list(enumerate(rows)))]
                if len(pts) >= 3: cv.create_polygon(*[c for p_ in pts for c in p_], fill=col(key), outline='')
            cv.create_line(*[c for i, r in enumerate(rows) for c in (X(i), Y(r['work'] + r['off'] + r['new']))], fill=col('INK'), width=1) if n > 1 else None
            for i, r in enumerate(rows):
                if r['label'] and i % max(1, n // 7) == 0: cv.create_text(X(i), H - 7, text=r['label'], font=font(9), fill=col('MUT'), anchor='w' if i == 0 else 'center')
        cv.create_line(0, T, W, T, fill=col('LINE'), dash=(2, 4)); cv.create_text(W - 2, T - 8, text=hm(mx).replace(' 00m', 'h').replace('h 00m', 'h'), font=mono(9), fill=col('MUT'), anchor='e')

    # ---- clock / events ----
    def clock(self):
        e = self.eng
        if self.alive(self.ringc):
            self.draw_ring(); run = e.running(); br = e.store.on_break()
            if self.alive(self.sub): self.sub.configure(text=('Session ' + hms(time.time() - run['start'])) if run else ('On a break' if br else 'Not tracking'))
            if br and int(e.policy.get('break_limit') or 0) and not getattr(self, 'brk_warned', False) and e.store.break_secs(local_midnight()) > int(e.policy['break_limit']) * 60:
                self.brk_warned = True; self.toast('Break allowance passed', 'You are over today\'s break allowance. You can keep going; your admins are told.', 'warn')
            if not br: self.brk_warned = False
        if self.tab == 'Insights' and time.time() - self.last_ins > 60: self.last_ins = time.time(); self.show_tab()
        self.root.after(1000, self.clock)
    def pump(self):
        try:
            while True:
                k, v = self.q.get_nowait()
                if k == 'done':
                    cb, r, err = v
                    if cb: cb(r, err)
                    elif err: self.alert('Something went wrong', str(err))
                elif k == 'call': v()
                elif k in ('state', 'gaps', 'tick'):
                    if self.tab == 'Track': self.state_ui(); self.draw_gaps()
                elif k == 'config': self.main()
                elif k == 'idle':
                    pol = {'pause': 'The timer stays stopped until you start it again.', 'auto': 'It starts again by itself when you are back.',
                           'max': 'The first part of the idle time still counts. The rest is a gap you can add back.'}[v['policy']]
                    self.state_ui(); self.draw_gaps(); self.alert(f"Stopped: no activity for {v['mins']} minutes", pol)
                elif k == 'resumed': self.state_ui(); self.draw_gaps(); self.toast('Tracking resumed', 'Welcome back. The idle stretch is waiting as a gap.')
                elif k == 'activity': self.act = v; self.draw_bars()
                elif k == 'shot':
                    if self.alive(self.shotl): self.shotl.configure(text='Screenshot taken at ' + time.strftime('%H:%M') + (', blurred' if v == 'blur' else ''), text_color=C['MUT'])
                    if self.eng.cfg.get('notify_shots', True): self.toast('Screenshot taken', 'Taken at ' + time.strftime('%H:%M') + (' and blurred' if v == 'blur' else '') + '. Opening it is logged and you are told.')
                elif k == 'notice':
                    t = {'view': 'Your screenshot was opened', 'view_self': 'You opened your screenshot', 'pay': 'Pay update', 'time': 'Time update', 'ss': 'Screenshots', 'delete': 'Screenshot deleted'}.get(v.get('kind'), 'Notice')
                    self.toast(t, v.get('text', ''), 'warn' if v.get('kind') == 'view' else 'info')
                elif k == 'ss_reminder': self.toast('Screenshots are paused', 'They come back on by themselves when the hour is over.', 'warn')
                elif k == 'chain': self.state_ui(); self.alert('This device was flagged', 'The server found that the offline log on this computer does not match its signatures. Your admins were told. Disconnect and connect again in Settings to start a new log.')
                elif k == 'error' and self.alive(self.shotl): self.shotl.configure(text=v[:160], text_color=C['BAD'])
                elif k == 'revoked': self.alert('This device was disconnected', 'Your time keeps being saved here in local mode. Connect again from Settings.'); self.main()
        except queue.Empty: pass
        self.root.after(200, self.pump)

    # ---- settings ----
    def settings(self):
        e = self.eng; c = e.cfg
        dark = ctk.BooleanVar(value=ctk.get_appearance_mode() == 'Dark'); gray = ctk.BooleanVar(value=self.tone == 'gray')
        titles = ctk.BooleanVar(value=c.get('titles', True)); notify = ctk.BooleanVar(value=c.get('notify_shots', True)); proj = {}
        def body(p, d):
            self.lab('Appearance', 12, 'MUT', parent=p).pack(anchor='w', pady=(14, 2))
            self.switch(p, 'Dark mode', dark, 'Off means light. Starts from your system.'); self.switch(p, 'Grayscale', gray, 'Everything in shades of gray, in either mode.')
            self.lab('Tracking', 12, 'MUT', parent=p).pack(anchor='w', pady=(12, 2))
            self.switch(p, 'Record window titles', titles, 'Shows files and documents in Insights.'); self.switch(p, 'Tell me when a screenshot is taken', notify)
            if e.connected:
                pol = {'pause': 'keeps the timer paused', 'auto': 'starts again from the stop point', 'max': 'starts again from the max point'}.get(e.policy['idle_policy'], '')
                self.lab('Team', 12, 'MUT', parent=p).pack(anchor='w', pady=(12, 2))
                self.lab(f"{c.get('team', '')}: idle limit {e.policy['idle_max']} min, {pol}. Daily target {e.policy.get('daily_target', 8):g}h.", 12, parent=p, wraplength=380).pack(anchor='w')
                self.lab(f"Server {c.get('server')}\nKey {pretty_fp(c.get('pin', {}).get('fp', ''))}", 11, 'MUT', parent=p, wraplength=380).pack(anchor='w', pady=(6, 0))
                s = e.policy['shots']; row = ctk.CTkFrame(p, fg_color='transparent'); row.pack(fill='x', pady=(12, 0)); row.columnconfigure((0, 1), weight=1, uniform='r')
                if s.get('allowed') and s.get('pause_allowed'):
                    paused = s.get('pause_until') and s['pause_until'] > time.time()
                    self.button('Screenshots back on' if paused else 'Pause screenshots 1h', lambda: (d.finish(None), self.pause_shots(0 if paused else 60)), 'ghost', parent=row, height=38).grid(row=0, column=0, sticky='ew', padx=(0, 4))
                self.button('Change password', lambda: (d.finish(None), self.pw_dialog()), 'ghost', parent=row, height=38).grid(row=0, column=1, sticky='ew', padx=(4, 0))
                self.button('Disconnect this computer', lambda: (d.finish(None), self.ask_disconnect()), 'ghost', parent=p, height=38).pack(fill='x', pady=(8, 0))
            else:
                self.lab('Projects on this computer', 12, 'MUT', parent=p).pack(anchor='w', pady=(12, 4))
                r = ctk.CTkFrame(p, fg_color='transparent'); r.pack(fill='x'); proj['e'] = self.entry('New project name', parent=r, height=38); proj['e'].pack(side='left', fill='x', expand=True)
                self.button('Add', lambda: (e.store.add_project(proj['e'].get()), proj['e'].delete(0, 'end'), self.toast('Project added')), parent=r, height=38, width=70).pack(side='left', padx=(8, 0))
                self.button('Connect to a team', lambda: (d.finish(None), self.connect_dialog()), parent=p, height=40).pack(fill='x', pady=(12, 0))
            self.lab(f'TrueDuty {VERSION}', 11, 'MUT', parent=p).pack(anchor='w', pady=(12, 0))
        def save(d):
            c['titles'] = titles.get(); c['notify_shots'] = notify.get()
            mode = 'dark' if dark.get() else 'light'; tone = 'gray' if gray.get() else 'color'
            changed = (mode == 'dark') != (ctk.get_appearance_mode() == 'Dark') or tone != self.tone
            if changed: c['mode'] = self.mode = mode; c['tone'] = self.tone = tone; set_look(mode, tone); self.load_logos(); self.root.configure(fg_color=C['BG'])
            save_cfg(c)
            if changed or not e.connected: self.main()
        Dialog(self, 'Settings', '', buttons=(('Cancel', 'ghost', None), ('Save', 'acc', save)), body=body, width=450)
    def pause_shots(self, minutes):
        self.bg(lambda: self.eng.pause_shots(minutes), lambda r, er: self.alert('Could not change screenshots', str(er)) if er else self.toast('Screenshots paused for an hour' if minutes else 'Screenshots are back on', 'The pause is logged and your admins are told.' if minutes else ''))
    def pw_dialog(self):
        ents = {}
        def body(p, d):
            for k, lbl in (('old', 'Current password (or a six digit code if you never set one)'), ('new', 'New password, at least 8 characters'), ('new2', 'Repeat the new password')):
                self.lab(lbl, 12, 'MUT', parent=p).pack(anchor='w', pady=(10, 4)); ents[k] = self.entry(parent=p, show='*'); ents[k].pack(fill='x')
            d.err = self.lab('', 12, 'BAD', parent=p, wraplength=370); d.err.pack(anchor='w', pady=(8, 0))
        def go(d):
            o, n1, n2 = ents['old'].get(), ents['new'].get(), ents['new2'].get()
            if not o or len(n1) < 8: d.err.configure(text='Type your current password and a new one with 8 or more characters.'); return False
            if n1 != n2: d.err.configure(text='The new passwords do not match.'); return False
            d.err.configure(text='Checking with the server', text_color=C['MUT'])
            def done(r, er):
                if er: d.err.configure(text=str(er)[:160], text_color=C['BAD'])
                else: d.finish(None); self.toast('Password changed', 'Your other devices and browser sessions were signed out.')
            self.bg(lambda: self.eng.change_password(o, n1), done); return False
        Dialog(self, 'Change password', 'The server checks your current password first.', buttons=(('Cancel', 'ghost', None), ('Change', 'acc', go)), body=body, width=440)
    def ask_disconnect(self):
        n = self.eng.store.unsent(); extra = f' {n} records have not reached the server yet; TrueDuty tries to send them first.' if n else ''
        self.confirm('Disconnect this computer?', 'Tracking keeps working in local mode and your history stays here. Your team stops getting new time from this computer.' + extra, 'Disconnect',
                     lambda: self.bg(self.eng.disconnect, lambda r, er: self.main()), danger=True)

    # ---- connect to a team ----
    def connect_dialog(self):
        e = self.eng; st = {'mode': 'Browser', 'busy': False}; w = {}
        def body(p, d):
            self.lab('Server address', 12, 'MUT', parent=p).pack(anchor='w', pady=(14, 4)); w['url'] = self.entry('taskdash.example.com', parent=p); w['url'].pack(fill='x'); w['url'].insert(0, e.cfg.get('server', ''))
            seg = Seg(p, ['Browser', 'Code', 'Password'], lambda v: (st.update(mode=v), show()), height=32, font_=font(12, True)); seg.pack(fill='x', pady=(14, 0)); seg.set('Browser')
            w['area'] = ctk.CTkFrame(p, fg_color='transparent', height=0); w['area'].pack(fill='x')
            d.msg = self.lab('', 12, 'MUT', parent=p, wraplength=380); d.msg.pack(anchor='w', pady=(10, 0))
            def show():
                for x in w['area'].winfo_children(): x.destroy()
                a = w['area']
                if st['mode'] == 'Code':
                    self.lab('Six digit code from Settings in the panel, or the team code your admin sent (XXXX-XXXX)', 11, 'MUT', parent=a, wraplength=380).pack(anchor='w', pady=(12, 4))
                    w['code'] = self.entry('123456 or ABCD-EFGH', parent=a, font=mono(16, True)); w['code'].pack(fill='x'); w['code'].bind('<KeyRelease>', lambda ev: team_fields())
                    w['team'] = ctk.CTkFrame(a, fg_color='transparent', height=0); w['team'].pack(fill='x')
                elif st['mode'] == 'Password':
                    self.lab('E-mail', 12, 'MUT', parent=a).pack(anchor='w', pady=(12, 4)); w['email'] = self.entry('you@example.com', parent=a); w['email'].pack(fill='x'); w['email'].insert(0, e.cfg.get('email', ''))
                    self.lab('Password', 12, 'MUT', parent=a).pack(anchor='w', pady=(10, 4)); w['pw'] = self.entry(parent=a, show='*'); w['pw'].pack(fill='x')
                else:
                    self.lab('Your browser opens the team website. Sign in there with Google or your e-mail and password, then approve this computer. The website hands a one-time pass back to TrueDuty on this computer, TrueDuty checks it with the server, and you are connected.', 12, 'MUT', parent=a, wraplength=380).pack(anchor='w', pady=(12, 0))
                d.update_idletasks(); d.place(460)
            def team_fields():
                code = w['code'].get().strip(); is_team = bool(re.fullmatch(r'[A-Za-z0-9]{4}-?[A-Za-z0-9]{4}', code)) and not code.replace('-', '').isdigit()
                t = w['team']
                if is_team and not t.winfo_children():
                    self.lab('New here? Create your account', 12, 'INK', True, parent=t).pack(anchor='w', pady=(12, 0))
                    for k, lbl, show_ in (('full_name', 'Your name', ''), ('email', 'E-mail', ''), ('password', 'Password, at least 8 characters', '*')):
                        self.lab(lbl, 12, 'MUT', parent=t).pack(anchor='w', pady=(8, 4)); w[k] = self.entry(parent=t, show=show_); w[k].pack(fill='x')
                    d.update_idletasks(); d.place(460)
                elif not is_team and t.winfo_children():
                    for x in t.winfo_children(): x.destroy()
                    d.update_idletasks(); d.place(460)
            show()
        def trust(fp):
            ev = threading.Event(); res = {'ok': False}
            def ask():
                Dialog(self, 'Trust this server?', 'Compare this key with the fingerprint in Settings, App and devices, in the panel. They must match.', buttons=(('Cancel', 'ghost', None), ('Trust', 'acc', lambda d_: res.update(ok=True))),
                       body=lambda p, d_: ctk.CTkLabel(p, text=fp, font=mono(13, True), text_color=C['INK'], wraplength=360, justify='left', anchor='w').pack(fill='x', pady=(12, 0)), on_close=ev.set)
            self.q.put(('call', ask)); ev.wait(); return res['ok']
        def go(d):
            if st['busy']: return False
            url = w['url'].get().strip()
            if not url: d.msg.configure(text='Type the server address first.', text_color=C['BAD']); return False
            if st['mode'] == 'Code':
                code = w['code'].get().strip()
                if code.isdigit() and len(code) == 6: body_ = {'code': code}
                elif 'full_name' in w and w['full_name'].winfo_exists():
                    body_ = {'team_code': code, 'full_name': w['full_name'].get().strip(), 'email': w['email'].get().strip(), 'password': w['password'].get()}
                    if not body_['full_name'] or '@' not in body_['email'] or len(body_['password']) < 8: d.msg.configure(text='Fill in your name, e-mail and a password of 8 or more characters.', text_color=C['BAD']); return False
                else: d.msg.configure(text='The code is six digits, or a team code like ABCD-EFGH.', text_color=C['BAD']); return False
            elif st['mode'] == 'Password':
                body_ = {'email': w['email'].get().strip().lower(), 'password': w['pw'].get()}
                if not body_['email'] or not body_['password']: d.msg.configure(text='Type your e-mail and password.', text_color=C['BAD']); return False
            else: body_ = None
            st['busy'] = True; d.msg.configure(text='Connecting', text_color=C['MUT']); e.cfg['email'] = (body_ or {}).get('email', e.cfg.get('email', ''))
            def work():
                e.open_server(url, trust)
                if body_ is not None: e.login(body_); return True
                r = e.browser_begin(); self.q.put(('call', lambda: (d.msg.configure(text='Waiting for you to sign in and approve this computer in your browser.', text_color=C['MUT']))))
                webbrowser.open(r['url'])
                if e.browser_wait(r, lambda: d.done): return True
                raise NetError('Sign-in was not approved in time. Try again.')
            def done(r, er):
                st['busy'] = False
                if er:
                    if self.alive(d): d.msg.configure(text=str(er)[:200], text_color=C['BAD'])
                    return
                if self.alive(d): d.finish(None)
                self.main(); self.toast('Connected', f"Time from this computer now goes to {e.cfg.get('team', 'your team')}.")
            self.bg(work, done); return False
        Dialog(self, 'Connect to a team', 'Your time keeps being saved on this computer. Connecting also sends it to your team.', buttons=(('Cancel', 'ghost', None), ('Connect', 'acc', go)), body=body, width=460)

    def close(self):
        if self.eng.running() or self.eng.store.on_break():
            def quit_():
                if self.eng.running(): self.eng.stop('stopped')
                self.eng.store.stop_break(); threading.Thread(target=self.eng.sync, daemon=True).start()
                self.root.after(1500, lambda: (setattr(self.eng, 'stop_flag', True), self.root.destroy()))
            return self.confirm('Quit TrueDuty?', 'Your timer is running. It stops when you quit.', 'Stop and quit', quit_, danger=True)
        self.eng.stop_flag = True; self.root.destroy()

if __name__ == '__main__':
    UI().root.mainloop()
