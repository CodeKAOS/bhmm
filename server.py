#!/usr/bin/env python3
import base64, csv, hmac, io, json, os, shutil, sqlite3, threading, time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen

REMOTE=os.getenv('BITCOIN_HERO_API','https://bitcoinhero.me/api/prices')
PORT=int(os.getenv('PORT','8000')); HOST=os.getenv('HOST','0.0.0.0')
AUTH_USER=os.getenv('TRACKER_USERNAME','admin')
AUTH_PASS=os.getenv('TRACKER_PASSWORD','')
DATA_DIR=os.getenv('DATA_DIR','/data' if os.path.isdir('/data') else os.path.join(os.path.dirname(__file__),'data'))
os.makedirs(DATA_DIR, exist_ok=True); DB=os.path.join(DATA_DIR,'bitcoin_hero.sqlite3')
SYMS=['BTC','ETH','SOL','DOGE','XRP','ADA','LINK','AVAX']
BASE={'BTC':(67620.74,97217.60),'ETH':(3867.34,5469.73),'SOL':(654.08,907.18),'DOGE':(.0437,.181773),'XRP':(.483,.9173),'ADA':(.402123,.6635),'LINK':(2.02,4.15),'AVAX':(62.25,135.04356736627548)}
lock=threading.RLock(); runtime={'ok':False,'last_error':None,'last_poll':None,'tick_ms':3000}

def con():
    c=sqlite3.connect(DB, timeout=20); c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA synchronous=NORMAL'); return c

def init_db():
    with con() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS prices(ts INTEGER NOT NULL,symbol TEXT NOT NULL,price REAL NOT NULL,change REAL,PRIMARY KEY(ts,symbol));
        CREATE INDEX IF NOT EXISTS idx_prices_symbol_ts ON prices(symbol,ts);
        CREATE TABLE IF NOT EXISTS records(symbol TEXT PRIMARY KEY,low REAL,low_at INTEGER,high REAL,high_at INTEGER,samples INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,ts INTEGER,symbol TEXT,type TEXT,price REAL);
        CREATE INDEX IF NOT EXISTS idx_events_symbol_ts ON events(symbol,ts);
        ''')
        now=int(time.time()*1000)
        for s,(lo,hi) in BASE.items():
            c.execute('INSERT OR IGNORE INTO records(symbol,low,low_at,high,high_at,samples) VALUES(?,?,?,?,?,0)',(s,lo,None,hi,None))

def ingest(payload):
    ts=int(payload.get('serverTime') or time.time()*1000); coins=payload.get('coins') or {}; tick=int(payload.get('tickMs') or 3000)
    with lock, con() as c:
        for s in SYMS:
            x=coins.get(s) or {}; p=x.get('price')
            try:p=float(p)
            except:continue
            ch=x.get('change'); ch=float(ch) if ch is not None else None
            c.execute('INSERT OR IGNORE INTO prices(ts,symbol,price,change) VALUES(?,?,?,?)',(ts,s,p,ch))
            r=c.execute('SELECT * FROM records WHERE symbol=?',(s,)).fetchone()
            if not r:
                c.execute('INSERT INTO records(symbol,low,low_at,high,high_at,samples) VALUES(?,?,?,?,?,1)',(s,p,ts,p,ts)); continue
            lo,hi=r['low'],r['high']; lat,hat=r['low_at'],r['high_at']
            if p<lo: lo,lat=p,ts; c.execute('INSERT INTO events(ts,symbol,type,price) VALUES(?,?,?,?)',(ts,s,'NEW LOW',p))
            if p>hi: hi,hat=p,ts; c.execute('INSERT INTO events(ts,symbol,type,price) VALUES(?,?,?,?)',(ts,s,'NEW HIGH',p))
            c.execute('UPDATE records SET low=?,low_at=?,high=?,high_at=?,samples=samples+1 WHERE symbol=?',(lo,lat,hi,hat,s))
    runtime.update(ok=True,last_error=None,last_poll=ts,tick_ms=tick)

def collector():
    while True:
        started=time.time()
        try:
            req=Request(REMOTE,headers={'User-Agent':'Mozilla/5.0 BitcoinHeroCloudTracker/10.0','Accept':'application/json','x-avatars':'url','x-bh-platform':'web'})
            with urlopen(req,timeout=12) as r: ingest(json.loads(r.read().decode()))
        except Exception as e:
            runtime.update(ok=False,last_error=str(e),last_poll=int(time.time()*1000))
        time.sleep(max(.25,3-(time.time()-started)))

def latest_state():
    out={'coins':{},'records':{},'events':{},'server':dict(runtime),'database':DB}
    with con() as c:
        for s in SYMS:
            p=c.execute('SELECT ts,price,change FROM prices WHERE symbol=? ORDER BY ts DESC LIMIT 1',(s,)).fetchone()
            r=c.execute('SELECT * FROM records WHERE symbol=?',(s,)).fetchone()
            ev=c.execute('SELECT ts,type,price FROM events WHERE symbol=? ORDER BY ts DESC LIMIT 1',(s,)).fetchone()
            out['coins'][s]=dict(p) if p else {}
            out['records'][s]=dict(r) if r else {}
            out['events'][s]=dict(ev) if ev else {}
    return out

def history(symbol, rng):
    now=int(time.time()*1000); cuts={'live':now-5*60_000,'1h':now-60*60_000,'1d':now-24*60*60_000}
    cut=cuts.get(rng,0)
    with con() as c:
        rows=c.execute('SELECT ts,price FROM prices WHERE symbol=? AND ts>=? ORDER BY ts',(symbol,cut)).fetchall()
    pts=[[r['ts'],r['price']] for r in rows]
    # downsample only for rendering/network; database retains full 3-second observations
    maxpts={'live':300,'1h':1200,'1d':1440,'all':2500}.get(rng,1200)
    if len(pts)>maxpts:
        step=len(pts)/maxpts; pts=[pts[int(i*step)] for i in range(maxpts-1)]+[pts[-1]]
    return pts

def import_csv_bytes(raw):
    text=raw.decode('utf-8-sig',errors='replace')
    reader=csv.DictReader(io.StringIO(text))
    required={'time','symbol','type','price'}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError('Unsupported CSV: expected time, symbol, type and price columns')
    backup=os.path.join(DATA_DIR,'backup-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.sqlite3')
    with lock:
        with con() as src:
            dst=sqlite3.connect(backup); src.backup(dst); dst.close()
        added=dupes=events_added=0; touched=set()
        with con() as c:
            for row in reader:
                sym=(row.get('symbol') or '').strip().upper()
                if sym not in SYMS: continue
                try:
                    ts=int(datetime.fromisoformat((row.get('time') or '').replace('Z','+00:00')).timestamp()*1000)
                    price=float(row.get('price') or row.get('current'))
                except Exception: continue
                typ=(row.get('type') or '').strip().upper(); touched.add(sym)
                ch=None
                try: ch=float(row.get('change')) if row.get('change') not in (None,'') else None
                except: pass
                cur=c.execute('INSERT OR IGNORE INTO prices(ts,symbol,price,change) VALUES(?,?,?,?)',(ts,sym,price,ch))
                if cur.rowcount: added+=1
                else: dupes+=1
                r=c.execute('SELECT * FROM records WHERE symbol=?',(sym,)).fetchone()
                lo=price if not r else r['low']; hi=price if not r else r['high']; lat=ts if not r else r['low_at']; hat=ts if not r else r['high_at']
                vals=[]
                for k in ('observedLow','observedHigh'):
                    try: vals.append(float(row.get(k)))
                    except: vals.append(None)
                ilo,ihi=vals
                if ilo is not None and ilo<lo: lo=ilo; lat=ts if typ=='NEW LOW' else lat
                if ihi is not None and ihi>hi: hi=ihi; hat=ts if typ=='NEW HIGH' else hat
                if price<lo: lo,lat=price,ts
                if price>hi: hi,hat=price,ts
                if not r: c.execute('INSERT INTO records(symbol,low,low_at,high,high_at,samples) VALUES(?,?,?,?,?,1)',(sym,lo,lat,hi,hat))
                else: c.execute('UPDATE records SET low=?,low_at=?,high=?,high_at=?,samples=samples+? WHERE symbol=?',(lo,lat,hi,hat,1 if cur.rowcount else 0,sym))
                if typ in ('NEW HIGH','NEW LOW'):
                    ex=c.execute('SELECT 1 FROM events WHERE ts=? AND symbol=? AND type=? AND price=? LIMIT 1',(ts,sym,typ,price)).fetchone()
                    if not ex: c.execute('INSERT INTO events(ts,symbol,type,price) VALUES(?,?,?,?)',(ts,sym,typ,price)); events_added+=1
    return {'ok':True,'priceRecordsAdded':added,'eventsAdded':events_added,'duplicatesSkipped':dupes,'cryptosUpdated':len(touched),'backup':os.path.basename(backup)}

def csv_bytes():
    b=io.StringIO(); w=csv.writer(b); w.writerow(['time','symbol','type','price','observedLow','observedHigh'])
    with con() as c:
        for r in c.execute('SELECT e.ts,e.symbol,e.type,e.price,r.low,r.high FROM events e JOIN records r USING(symbol) ORDER BY e.ts'):
            w.writerow([datetime.fromtimestamp(r['ts']/1000,timezone.utc).isoformat(),r['symbol'],r['type'],r['price'],r['low'],r['high']])
        for s in SYMS:
            p=c.execute('SELECT ts,price FROM prices WHERE symbol=? ORDER BY ts DESC LIMIT 1',(s,)).fetchone(); r=c.execute('SELECT * FROM records WHERE symbol=?',(s,)).fetchone()
            if p and r:w.writerow([datetime.fromtimestamp(p['ts']/1000,timezone.utc).isoformat(),s,'SNAPSHOT',p['price'],r['low'],r['high']])
    return b.getvalue().encode()

class Handler(SimpleHTTPRequestHandler):
    def authorized(self):
        # Fail closed in cloud deployments: set TRACKER_PASSWORD to enable access.
        if not AUTH_PASS:
            return False
        header=self.headers.get('Authorization','')
        if not header.startswith('Basic '):
            return False
        try:
            raw=base64.b64decode(header[6:], validate=True).decode('utf-8')
            user,password=raw.split(':',1)
        except Exception:
            return False
        return hmac.compare_digest(user,AUTH_USER) and hmac.compare_digest(password,AUTH_PASS)
    def require_auth(self):
        if self.authorized():
            return True
        body=b'Authentication required'
        self.send_response(401)
        self.send_header('WWW-Authenticate','Basic realm="Bitcoin Hero Tracker", charset="UTF-8"')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Type','text/plain; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
        return False
    def log_message(self,fmt,*args): print('%s - %s'%(self.address_string(),fmt%args))
    def send_json(self,obj,code=200):
        body=json.dumps(obj,separators=(',',':')).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        if not self.require_auth(): return
        u=urlparse(self.path)
        if u.path!='/api/import': return self.send_json({'error':'not found'},404)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<=0 or n>25_000_000: return self.send_json({'error':'CSV must be between 1 byte and 25 MB'},400)
            result=import_csv_bytes(self.rfile.read(n))
            return self.send_json(result)
        except Exception as e:
            return self.send_json({'error':str(e)},400)

    def do_GET(self):
        if not self.require_auth(): return
        u=urlparse(self.path)
        if u.path=='/api/state': return self.send_json(latest_state())
        if u.path=='/api/history':
            q=parse_qs(u.query); s=(q.get('symbol') or [''])[0].upper(); rng=(q.get('range') or ['live'])[0]
            if s not in SYMS or rng not in ('live','1h','1d','all'): return self.send_json({'error':'bad parameters'},400)
            return self.send_json({'symbol':s,'range':rng,'points':history(s,rng)})
        if u.path=='/api/export.csv':
            body=csv_bytes(); self.send_response(200); self.send_header('Content-Type','text/csv'); self.send_header('Content-Disposition','attachment; filename="bitcoin-hero-cloud-snapshot.csv"'); self.send_header('Content-Length',str(len(body))); self.end_headers(); return self.wfile.write(body)
        if u.path=='/api/health': return self.send_json({'ok':runtime['ok'],'lastPoll':runtime['last_poll'],'error':runtime['last_error']})
        if u.path=='/': self.path='/tracker.html'
        return super().do_GET()

if __name__=='__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__))); init_db(); threading.Thread(target=collector,daemon=True).start()
    print(f'Bitcoin Hero Northflank Tracker v11 on 0.0.0.0:{PORT}; DB={DB}')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
