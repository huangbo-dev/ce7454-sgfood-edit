"""Self-hosted blinded annotation site for the SgFood-Edit project team (CE7454), adapted from the baseline rating site.

Annotators are project-team members only. No participants outside the team are recruited and no personal data is
collected: running a study on other people would need School ethics (ERC/NTU-IRB) approval obtained BEFORE the study,
which the project timeline does not allow (see plan/DESIGN_REVIEW.md).

Criteria come from site/items.json ("criteria"); everything else (invitation codes, rate limit, admin page) is unchanged.


Binds to 127.0.0.1; start_site.sh exposes it to the tailnet with `tailscale serve` (tailnet only).

  python site_server.py serve [--port 8766]
  python site_server.py add-rater "Rater Name"     # prints that rater's invitation code and link
  python site_server.py revoke "Rater Name"        # disable a code (their saved answers are kept)
  python site_server.py raters                     # list raters, codes and progress

Access: every route except the sign-in page needs a valid invitation code, sent as ?r=CODE or the
HttpOnly cookie set at sign-in. Failed codes are rate-limited. /admin refuses requests that arrive
through Tailscale Funnel (public internet), so it is reachable only from the tailnet or this machine.

Data (all git-ignored):
  site/            page, items.json and images, from build_study.py (no model identities)
  responses/raters.json        token -> {name, created}; names never reach the rating records
  responses/site_ratings.jsonl append-only log; the latest record per (rater, key) wins
  responses/site_profiles.jsonl append-only rater profiles
  responses/admin.key          key for /admin
"""
import argparse, json, re, secrets, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
SITE = HERE / 'site'
RESP = HERE / 'responses'
RATERS = RESP / 'raters.json'
LOG = RESP / 'site_ratings.jsonl'
PROFILES = RESP / 'site_profiles.jsonl'
ADMIN = RESP / 'admin.key'
LOCK = threading.Lock()
TOKEN = re.compile(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$')
ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # no 0/O, 1/I/L
FAILS = []  # timestamps of failed code attempts (global limiter)
KEYRE = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
CRIT = {'edit': (0, 1, 2), 'preserve': (0, 1, 2), 'realism': (1, 2, 3, 4, 5), 'extra': (0, 1)}  # replaced from items.json


def jload(p, default):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, ValueError):
        return default


def jsonl(p):
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def append(p, rec):
    with LOCK, open(p, 'a') as f:
        f.write(json.dumps(rec) + '\n')
        f.flush()


def rater_id(token):
    """Opaque, stable rater id derived from the code; the name stays in raters.json only."""
    import hashlib
    return 'r-' + hashlib.sha256(token.encode()).hexdigest()[:10]


def new_code():
    return '-'.join(''.join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3))


def norm_code(c):
    c = re.sub(r'[^A-Za-z0-9]', '', c or '').upper()
    return f'{c[:4]}-{c[4:8]}-{c[8:12]}' if len(c) == 12 else ''


def throttled():
    now = time.time()
    with LOCK:
        FAILS[:] = [t for t in FAILS if now - t < 60]
        return len(FAILS) >= 20


def failed():
    with LOCK:
        FAILS.append(time.time())


class App:
    def __init__(self):
        RESP.mkdir(exist_ok=True)
        if not ADMIN.exists():
            ADMIN.write_text(secrets.token_urlsafe(18))
            ADMIN.chmod(0o600)
        self.admin = ADMIN.read_text().strip()
        d = json.loads((SITE / 'items.json').read_text())
        global CRIT
        if d.get('criteria'):
            CRIT = {c['key']: tuple(v for v, _ in c['options']) for c in d['criteria']}
        self.n_screens = d.get('n_screens', len(d['items']))
        self.n_main = len(d['items'])
        self.items = {i['id']: i for i in d['items'] + d['checks']}
        self.media = {i[k] for i in self.items.values() for k in ('original', 'A', 'B')}
        self.valid_keys = set(self.items) | {'rep-' + i for i in self.items}

    def raters(self):
        return {t: v for t, v in jload(RATERS, {}).items() if not v.get('revoked')}

    def done(self, rid):
        last = {}
        for r in jsonl(LOG):
            if r.get('rater') == rid:
                last[r['key']] = r
        return last

    def profile(self, rid):
        p = {}
        for r in jsonl(PROFILES):
            if r.get('rater') == rid:
                p = r
        return p


def valid_side(d):
    return isinstance(d, dict) and all(d.get(k) in v for k, v in CRIT.items())


def make_handler(app):
    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            pass

        def send(self, code, body, ctype='application/json', cache=False, cookie=None):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            if cookie is not None:
                self.send_header('Set-Cookie', f'pe_r={cookie}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=2592000')
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'private, max-age=86400' if cache else 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('X-Robots-Tag', 'noindex, nofollow')
            self.end_headers()
            self.wfile.write(body)

        def token(self, q):
            t = norm_code((q.get('r') or [''])[0])
            if not t:
                for part in (self.headers.get('Cookie') or '').split(';'):
                    k, _, v = part.strip().partition('=')
                    if k == 'pe_r':
                        t = norm_code(v)
            if not t:
                return None
            if throttled():
                return None
            if TOKEN.match(t) and t in app.raters():
                return t
            failed()
            return None

        def public(self):
            return self.headers.get('Tailscale-Funnel-Request') is not None

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ('/', '/index.html'):  # the page itself holds no study content
                return self.send(200, (SITE / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            if u.path == '/admin':
                if self.public() or (q.get('key') or [''])[0] != app.admin:
                    return self.send(404, {'error': 'not found'})
                return self.send(200, admin_page(app).encode(), 'text/html; charset=utf-8')
            if u.path == '/robots.txt':
                return self.send(200, b'User-agent: *\nDisallow: /\n', 'text/plain')
            t = self.token(q)
            if not t:
                return self.send(429 if throttled() else 403, {'error': 'invitation code needed'})
            if u.path == '/items.json':
                return self.send(200, (SITE / 'items.json').read_bytes(), cache=False)
            if u.path.startswith('/media/'):
                name = u.path[len('/media/'):]
                if name not in app.media:
                    return self.send(404, {'error': 'not found'})
                return self.send(200, (SITE / 'media' / name).read_bytes(), 'image/jpeg', cache=True)
            if u.path == '/api/state':
                rid = rater_id(t)
                return self.send(200, {'rater': rid, 'profile': app.profile(rid), 'done': app.done(rid)}, cookie=t)
            return self.send(404, {'error': 'not found'})

        def do_POST(self):
            u = urlparse(self.path)
            t = self.token(parse_qs(u.query))
            if not t:
                return self.send(429 if throttled() else 403, {'error': 'invitation code needed'})
            n = int(self.headers.get('Content-Length') or 0)
            if n <= 0 or n > 20000:
                return self.send(413, {'error': 'body too large'})
            try:
                d = json.loads(self.rfile.read(n))
            except ValueError:
                return self.send(400, {'error': 'bad json'})
            rid = rater_id(t)
            now = time.strftime('%Y-%m-%dT%H:%M:%S%z')
            if u.path == '/api/profile':
                rec = {'rater': rid, 'consent': d.get('consent') is True,
                       'rubric': str(d.get('rubric', ''))[:40], 'started_at': str(d.get('started_at', ''))[:40], 'server_ts': now}
                if not rec['consent']:   # annotator confirms team membership and blind, independent annotation
                    return self.send(400, {'error': 'incomplete profile'})
                append(PROFILES, rec)
                return self.send(200, {'ok': True})
            if u.path == '/api/rate':
                key, item = d.get('key'), d.get('item')
                if not (isinstance(key, str) and KEYRE.match(key) and key in app.valid_keys and item in app.items):
                    return self.send(400, {'error': 'unknown item'})
                if not (valid_side(d.get('A')) and valid_side(d.get('B')) and d.get('preference') in ('A', 'B', 'tie')):
                    return self.send(400, {'error': 'incomplete answer'})
                rec = {k: d.get(k) for k in ('item', 'key', 'kind', 'task', 'A', 'B', 'preference', 'flipped',
                                             'seconds', 'position', 'rubric', 'gold_pass', 'revised')}
                rec['A'] = {k: d['A'][k] for k in CRIT}
                rec['B'] = {k: d['B'][k] for k in CRIT}
                rec['note'] = str(d.get('note') or '')[:500]
                rec.update(rater=rid, server_ts=now)
                append(LOG, rec)
                return self.send(200, {'ok': True})
            return self.send(404, {'error': 'not found'})
    return H


def admin_page(app):
    rows = []
    gold_ids = [i for i, v in app.items.items() if v.get('kind') == 'gold']
    for t, info in app.raters().items():
        rid = rater_id(t)
        done = app.done(rid)
        main = sum(r['kind'] == 'main' for r in done.values())
        gold = [r for r in done.values() if r['kind'] == 'gold']
        gp = sum(bool(r.get('gold_pass')) for r in gold)
        secs = sorted(r.get('seconds') or 0 for r in done.values())
        med = secs[len(secs) // 2] if secs else '-'
        rows.append(f"<tr><td>{esc(info['name'])}</td><td>{rid}</td><td>{len(done)} / {app.n_screens}</td><td>{main} / {app.n_main}</td>"
                    f"<td>{gp} / {len(gold)} of {len(gold_ids)}</td><td>{med}</td></tr>")
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Study progress</title><style>body{font:15px system-ui;margin:24px;color:#1d221c;background:#f5f6f2}"
            "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px 10px;text-align:left}"
            "th{background:#e3eee2}</style><h1>SgFood-Edit study progress</h1><table><tr><th>Rater</th><th>Id</th><th>Screens</th>"
            "<th>Main pairs</th><th>Checks passed</th><th>Median s</th></tr>" + ''.join(rows) + "</table>")


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('serve')
    s.add_argument('--port', type=int, default=8766)
    a = sub.add_parser('add-rater')
    a.add_argument('name')
    v = sub.add_parser('revoke')
    v.add_argument('name')
    sub.add_parser('raters')
    args = ap.parse_args()
    RESP.mkdir(exist_ok=True)
    if args.cmd == 'add-rater':
        r = jload(RATERS, {})
        t = new_code()
        r[t] = {'name': args.name, 'created': time.strftime('%Y-%m-%d %H:%M')}
        RATERS.write_text(json.dumps(r, indent=1))
        RATERS.chmod(0o600)
        print(f'{args.name}: code {t}   link <site URL>/?r={t}')
        return
    if args.cmd == 'revoke':
        r = jload(RATERS, {})
        hit = [t for t, v in r.items() if v['name'] == args.name and not v.get('revoked')]
        for t in hit:
            r[t]['revoked'] = time.strftime('%Y-%m-%d %H:%M')
        RATERS.write_text(json.dumps(r, indent=1))
        print(f'revoked {len(hit)} code(s) for {args.name}')
        return
    app = App()
    if args.cmd == 'raters':
        for t, info in app.raters().items():
            print(f"{info['name']:<20} {t}  {rater_id(t)}  screens {len(app.done(rater_id(t)))}")
        print(f'admin page (tailnet or this machine only): /admin?key={app.admin}')
        return
    srv = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(app))
    print(f'serving on http://127.0.0.1:{args.port}', flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
