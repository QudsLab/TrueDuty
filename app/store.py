"""Local database of the TrueDuty app. Everything is written here first, with or without a server.

When the app is connected to a team, every change is also appended to a signed log (outbox). Each record carries a
sequence number, the MAC of the record before it and its own HMAC-SHA256 made with the device key, so the server
can tell if anything was removed, edited or reordered while the app was offline."""
import os, json, time, hmac, sqlite3, threading, uuid, calendar
from categories import classify, clean_app, item_of, label_of

SCHEMA = '''
CREATE TABLE IF NOT EXISTS entries(uid TEXT PRIMARY KEY, project_id INTEGER, project TEXT, start INTEGER, stop INTEGER, running INTEGER DEFAULT 0, src TEXT DEFAULT 'app', team TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_entries_start ON entries(start);
CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, entry_uid TEXT, ts INTEGER, k INTEGER, m INTEGER, app TEXT, title TEXT, UNIQUE(entry_uid, ts));
CREATE INDEX IF NOT EXISTS ix_activity_ts ON activity(ts);
CREATE TABLE IF NOT EXISTS breaks(uid TEXT PRIMARY KEY, start INTEGER, stop INTEGER, running INTEGER DEFAULT 0, reason TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS gaps(uid TEXT PRIMARY KEY, start INTEGER, stop INTEGER, status TEXT DEFAULT 'open', created INTEGER);
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, name TEXT, archived INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS outbox(seq INTEGER, device TEXT, kind TEXT, data TEXT, prev TEXT, mac TEXT, sent INTEGER DEFAULT 0, PRIMARY KEY(device, seq));
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
'''
def canon(x): return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
def new_uid(): return uuid.uuid4().hex[:24]

class Store:
    def __init__(self, path):
        self.path = path; self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=20); self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.executescript(SCHEMA)
        if not self.db.execute('SELECT COUNT(*) FROM projects').fetchone()[0]: self.db.execute("INSERT INTO projects(name) VALUES('General')")
        self.db.commit(); self.device = None; self.key = None
    def q(self, sql, *a):
        with self.lock: return [dict(r) for r in self.db.execute(sql, a).fetchall()]
    def q1(self, sql, *a):
        with self.lock:
            r = self.db.execute(sql, a).fetchone(); return dict(r) if r else None
    def ex(self, sql, *a):
        with self.lock:
            c = self.db.execute(sql, a); self.db.commit(); return c.lastrowid
    def kv(self, k, d=None):
        r = self.q1('SELECT v FROM kv WHERE k=?', k); return r['v'] if r else d
    def set_kv(self, k, v): self.ex('INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)', k, str(v))

    # ---------------- signed log ----------------
    def attach(self, device, key):
        """Use the signed log of this device. key: bytes, or None when the app runs locally only."""
        self.device, self.key = (str(device), key) if device and key else (None, None)
    def log(self, kind, data):
        if not self.key: return
        with self.lock:
            last = self.db.execute('SELECT seq, mac FROM outbox WHERE device=? ORDER BY seq DESC LIMIT 1', (self.device,)).fetchone()
            seq, prev = (last['seq'] + 1, last['mac']) if last else (1, '')
            mac = hmac.new(self.key, f'{seq}|{prev}|{kind}|{canon(data)}'.encode(), 'sha256').hexdigest()
            self.db.execute('INSERT INTO outbox(seq,device,kind,data,prev,mac) VALUES(?,?,?,?,?,?)', (seq, self.device, kind, canon(data), prev, mac)); self.db.commit()
    def pending(self, n=400):
        if not self.device: return []
        return [{'seq': r['seq'], 'kind': r['kind'], 'd': json.loads(r['data']), 'prev': r['prev'], 'mac': r['mac']}
                for r in self.q('SELECT * FROM outbox WHERE device=? AND sent=0 ORDER BY seq LIMIT ?', self.device, n)]
    def acked(self, seq):
        if self.device: self.ex('UPDATE outbox SET sent=1 WHERE device=? AND seq<=?', self.device, int(seq))
        if self.device and int(seq) > 0: self.ex('DELETE FROM outbox WHERE device=? AND sent=1 AND seq<?', self.device, int(seq) - 50)
    def unsent(self):
        if not self.device: return 0
        return self.q1('SELECT COUNT(*) c FROM outbox WHERE device=? AND sent=0', self.device)['c']

    # ---------------- time ----------------
    def start_entry(self, project_id, project, src='app', team='', start=None, gap=None):
        uid = new_uid(); t = int(start or time.time())
        self.ex('UPDATE entries SET running=0 WHERE running=1')
        self.ex('INSERT INTO entries(uid,project_id,project,start,stop,running,src,team) VALUES(?,?,?,?,?,?,?,?)', uid, project_id, project, t, t, 1, src, team)
        d = {'u': uid, 'p': project_id, 's': t, 'e': t, 'r': 1}
        if src == 'gap': d.update(src='gap', g=gap)
        self.log('entry', d); return uid
    def touch_entry(self, uid, stop, running=True, log=False):
        e = self.q1('SELECT * FROM entries WHERE uid=?', uid)
        if not e: return
        self.ex('UPDATE entries SET stop=?, running=? WHERE uid=?', int(stop), 1 if running else 0, uid)
        if log or not running:
            d = {'u': uid, 'p': e['project_id'], 's': e['start'], 'e': int(stop), 'r': 1 if running else 0}
            if e['src'] == 'gap': d['src'] = 'gap'
            self.log('entry', d)
    def add_gap_entry(self, gap, project_id, project):
        g = self.q1('SELECT * FROM gaps WHERE uid=?', gap)
        if not g or g['status'] != 'open': return
        uid = new_uid(); stop = g['stop']
        self.ex('INSERT INTO entries(uid,project_id,project,start,stop,running,src) VALUES(?,?,?,?,?,0,?)', uid, project_id, project, g['start'], stop, 'gap')
        self.ex("UPDATE gaps SET status='filled' WHERE uid=?", gap)
        self.log('entry', {'u': uid, 'p': project_id, 's': g['start'], 'e': stop, 'r': 0, 'src': 'gap', 'g': gap})
    def running(self): return self.q1('SELECT * FROM entries WHERE running=1 ORDER BY start DESC LIMIT 1')
    def add_minute(self, entry_uid, ts, k, m, app, title):
        ts = int(ts) - int(ts) % 60
        try: self.ex('INSERT INTO activity(entry_uid,ts,k,m,app,title) VALUES(?,?,?,?,?,?)', entry_uid, ts, int(k), int(m), app or '', title or '')
        except sqlite3.IntegrityError: return
        self.log('act', {'u': entry_uid, 't': ts, 'k': int(k), 'm': int(m), 'a': app or '', 'ti': title or ''})
    def cut_activity(self, entry_uid, after):
        self.ex('DELETE FROM activity WHERE entry_uid=? AND ts>=?', entry_uid, int(after))
    def start_break(self, reason=''):
        uid = new_uid(); t = int(time.time())
        self.ex('INSERT INTO breaks(uid,start,stop,running,reason) VALUES(?,?,?,1,?)', uid, t, t, reason)
        self.log('brk', {'u': uid, 's': t, 'e': t, 'r': 1, 'why': reason}); return uid
    def stop_break(self):
        b = self.q1('SELECT * FROM breaks WHERE running=1')
        if not b: return
        t = int(time.time()); self.ex('UPDATE breaks SET stop=?, running=0 WHERE uid=?', t, b['uid'])
        self.log('brk', {'u': b['uid'], 's': b['start'], 'e': t, 'r': 0, 'why': b['reason']})
    def on_break(self): return self.q1('SELECT * FROM breaks WHERE running=1')
    def touch_break(self):
        b = self.on_break()
        if b: self.ex('UPDATE breaks SET stop=? WHERE uid=?', int(time.time()), b['uid'])
    def add_gap(self, start, stop):
        uid = new_uid(); self.ex('INSERT INTO gaps(uid,start,stop,status,created) VALUES(?,?,?,?,?)', uid, int(start), int(stop), 'open', int(time.time()))
        self.log('gap', {'u': uid, 's': int(start), 'e': int(stop), 'st': 'open'}); return uid
    def grow_gap(self, uid, stop):
        g = self.q1('SELECT * FROM gaps WHERE uid=?', uid)
        if g and g['status'] == 'open':
            self.ex('UPDATE gaps SET stop=? WHERE uid=?', int(stop), uid); self.log('gap', {'u': uid, 's': g['start'], 'e': int(stop), 'st': 'open'})
    def dismiss_gap(self, uid):
        g = self.q1('SELECT * FROM gaps WHERE uid=?', uid)
        if g: self.ex("UPDATE gaps SET status='dismissed' WHERE uid=?", uid); self.log('gap', {'u': uid, 's': g['start'], 'e': g['stop'], 'st': 'dismissed'})
    def open_gaps(self):
        return [g for g in self.q("SELECT * FROM gaps WHERE status='open' AND created>? ORDER BY start DESC", int(time.time()) - 48 * 3600) if g['stop'] - g['start'] >= 60]

    # ---------------- totals and insights ----------------
    def secs(self, a, b):
        r = self.q1('SELECT COALESCE(SUM(MIN(stop,?)-MAX(start,?)),0) s FROM entries WHERE stop>? AND start<?', min(b, int(time.time()) + 1), a, a, b)
        return max(0, int(r['s']))
    def break_secs(self, a):
        r = self.q1('SELECT COALESCE(SUM(MIN(stop,?)-MAX(start,?)),0) s FROM breaks WHERE stop>?', int(time.time()) + 1, a, a); return max(0, int(r['s']))
    def usage(self, a, b, rules=(), tzm=0):
        """Same numbers the server shows: tracked time, work, not work, unrated, categories, apps, days, hours."""
        rules = list(rules or []); act = self.q('SELECT ts,k,m,app,title FROM activity WHERE ts>=? AND ts<? ORDER BY ts', a, b)
        tot = {'work': 0, 'off': 0, 'new': 0}; apps = {}; cats = {}; days = {}; hours = [{'work': 0, 'off': 0, 'new': 0} for _ in range(24)]; active = 0; cache = {}
        dk = lambda ts: time.strftime('%Y-%m-%d', time.gmtime(ts + tzm * 60))
        for r in act:
            key = (r['app'], r['title'])
            if key not in cache: cache[key] = classify(rules, r['app'], r['title'])
            cls, cat = cache[key]; app = clean_app(r['app']) or 'Unknown'
            tot[cls] += 60
            if r['k'] + r['m'] > 0: active += 1
            hours[((r['ts'] + tzm * 60) // 3600) % 24][cls] += 60
            apps.setdefault(app, {'app': app, 'secs': 0})['secs'] += 60
            cats.setdefault(cat, {'category': cat, 'secs': 0})['secs'] += 60
            d = days.setdefault(dk(r['ts']), {'day': dk(r['ts']), 'work': 0, 'off': 0, 'new': 0, 'secs': 0}); d[cls] += 60
        for k, v in apps.items(): v['cls'], v['category'] = classify(rules, k, ''); v['label'] = label_of(k)
        ct = sum(c['secs'] for c in cats.values()) or 1
        for c in cats.values(): c['pct'] = round(100 * c['secs'] / ct)
        rated = tot['work'] + tot['off']
        return {'secs': self.secs(a, b), 'work': tot['work'], 'off': tot['off'], 'new': tot['new'], 'prod': round(100 * tot['work'] / rated) if rated else None,
                'activity': round(100 * active / len(act)) if act else 0, 'apps': sorted(apps.values(), key=lambda x: -x['secs']),
                'cats': sorted(cats.values(), key=lambda x: -x['secs']), 'days': days, 'hours': hours}

    # ---------------- projects (local mode) ----------------
    def projects(self): return self.q('SELECT id,name FROM projects WHERE archived=0 ORDER BY name')
    def add_project(self, name):
        name = (name or '').strip()[:80]
        if name and not self.q1('SELECT id FROM projects WHERE lower(name)=lower(?)', name): self.ex('INSERT INTO projects(name) VALUES(?)', name)
