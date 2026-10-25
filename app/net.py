"""TrueDuty secure client: X25519 + ML-KEM-768 hybrid handshake, AES-256-GCM messages, server key pinning."""
import json, os, time, hmac, hashlib, base64, ssl, urllib.request, urllib.error, urllib.parse
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import serialization
from kyber_py.ml_kem import ML_KEM_768

b64e = lambda b: base64.b64encode(b).decode()
b64d = lambda s: base64.b64decode(s)

class NetError(Exception): pass
class KeyChanged(NetError): pass

def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

def hkdf(ikm, salt, info, n):
    prk = hmac.new(salt, ikm, 'sha256').digest(); out = b''; t = b''; i = 1
    while len(out) < n:
        t = hmac.new(prk, t + info + bytes([i]), 'sha256').digest(); out += t; i += 1
    return out[:n]

class Client:
    def __init__(self, base, pin=None):
        base = base.strip().rstrip('/')
        if not base.startswith('http'): base = 'https://' + base
        host = urllib.parse.urlparse(base).hostname or ''
        if base.startswith('http://') and host not in ('localhost', '127.0.0.1', '::1'):
            raise NetError('Use https:// for remote servers (plain http is only allowed for localhost).')
        self.base = base; self.pin = pin or {}      # {'fp','x25519','mlkem'} pinned after first connect
        self.sid = None; self.k1 = self.k2 = None; self.seq = 0; self.ctx = _ctx()

    # ---- plain http ----
    def _url(self, path):
        return self.base + '/api' + path
    def _http(self, method, path, body=None, timeout=25):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self._url(path), data, {'Content-Type': 'application/json', 'User-Agent': 'TrueDuty-App'}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r: return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try: msg = json.loads(e.read()).get('error', '')
            except Exception: msg = ''
            raise NetError(msg or f'server error {e.code}')
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise NetError(f'cannot reach server: {getattr(e, "reason", e)}')

    def detect(self):
        try:
            j = self._http('GET', '/sec/pk', timeout=12)
            if 'mlkem' in j: return j
        except NetError as e:
            if 'cannot reach' in str(e): raise
        raise NetError('this address is not a TaskDash server')

    # ---- secure channel ----
    def connect(self):
        pk = self.detect()
        fp = hashlib.sha256(b64d(pk['x25519']) + b64d(pk['mlkem'])).hexdigest()[:32]
        if self.pin.get('fp') and self.pin['fp'] != fp:
            raise KeyChanged('SERVER KEY CHANGED - possible man-in-the-middle. Connection refused.')
        self.pin = {'fp': fp, 'x25519': pk['x25519'], 'mlkem': pk['mlkem']}
        self.handshake()
        return fp

    def handshake(self):
        x_pk = b64d(self.pin['x25519']); ek = b64d(self.pin['mlkem'])
        eph = X25519PrivateKey.generate(); epk = eph.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        ss, ct = ML_KEM_768.encaps(ek)
        r = self._http('POST', '/sec/hs', {'epk': b64e(epk), 'ct': b64e(ct)})
        spk = b64d(r['spk'])
        ikm = ss + eph.exchange(X25519PublicKey.from_public_bytes(x_pk)) + eph.exchange(X25519PublicKey.from_public_bytes(spk))
        salt = hashlib.sha256(epk + ct + x_pk + spk).digest()
        okm = hkdf(ikm, salt, b'trueduty-v1', 64)
        if not hmac.compare_digest(hmac.new(okm[32:], b'conf' + salt, 'sha256').digest(), b64d(r['conf'])):
            raise KeyChanged('Server failed key confirmation - connection refused.')
        self.sid = r['sid']; self.k1, self.k2 = okm[:32], okm[32:]; self.seq = 0

    def call(self, path, body=None, tok=None, endpoint='/sec/msg', _retry=True):
        if not self.sid: self.handshake()
        self.seq += 1; sid = self.sid.encode()
        pt = json.dumps({'seq': self.seq, 'ts': int(time.time()), 'path': path, 'tok': tok, 'body': body or {}}).encode()
        n = os.urandom(12)
        try:
            r = self._http('POST', endpoint, {'sid': self.sid, 'n': b64e(n), 'c': b64e(AESGCM(self.k1).encrypt(n, pt, sid + b'c2s'))}, timeout=60)
        except NetError as e:
            if _retry and ('expired' in str(e) or 'replay' in str(e)):
                self.sid = None; return self.call(path, body, tok, endpoint, False)
            raise
        res = json.loads(AESGCM(self.k2).decrypt(b64d(r['n']), b64d(r['c']), sid + b's2c'))
        if not res.get('ok'): raise NetError(res.get('err', 'error'))
        return res['data']

def pretty_fp(fp): return ' '.join(fp[i:i+4] for i in range(0, len(fp), 4))
