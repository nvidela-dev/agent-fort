"""Agent Fort: single-origin, authenticated PWA and local Hermes bridge."""
import hashlib, hmac, json, os, secrets, signal, sqlite3, subprocess, threading, time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).parent
IDLE_SECONDS = 360

class Watch:
    def __init__(self, data=None, hermes_home=None, command=None):
        self.data = Path(data or ROOT / '.data'); self.data.mkdir(mode=0o700, exist_ok=True)
        self.home = Path(hermes_home or os.environ.get('HERMES_HOME', str(Path.home()/'.hermes')))
        self.command = command or os.environ.get('HERMES_BIN', 'hermes')
        key = self.data/'access-key'
        if not key.exists():
            fd = os.open(key, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd,'w') as f: f.write(secrets.token_urlsafe(32))
        self.key = key.read_text().strip()
        self.live = None
        self.clients = {}
        self.sessions = {}; self.attempts = {}; self.lock = threading.RLock(); self.processes = {}; self.cancelled = set()
        with self.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            for row in c.execute('SELECT id,body FROM runs'):
                run=json.loads(row[1])
                if run['status'] in ('working','starting'):
                    run.update(status='interrupted', phase='idle', action='Server restarted; run status unknown')
                    c.execute('UPDATE runs SET body=? WHERE id=?',(json.dumps(run),row[0]))
    @contextmanager
    def db(self):
        c=sqlite3.connect(self.data/'watch.db', timeout=5)
        try:
            with c: yield c
        finally: c.close()
    def save(self, run):
        with self.db() as c: c.execute('INSERT OR REPLACE INTO runs VALUES (?,?)',(run['id'],json.dumps(run)))
    def runs(self):
        with self.db() as c: return sorted([json.loads(r[0]) for r in c.execute('SELECT body FROM runs')], key=lambda r:(r.get('status') in ('starting','working'),r['started']), reverse=True)
    def history(self, sid=None):
        p=self.home/'state.db'
        if not p.exists(): return []
        with self.history_connection(p) as c:
            c.row_factory=sqlite3.Row
            if sid:
                return [dict(r) for r in c.execute('SELECT role,content,tool_name,timestamp FROM messages WHERE session_id=? AND active=1 ORDER BY timestamp DESC LIMIT 100',(sid,))][::-1]
            return [dict(r) for r in c.execute("SELECT s.id,s.title,s.source,s.parent_session_id,s.model,s.started_at,s.ended_at,s.last_activity_at,s.last_activity_description,s.tool_call_count,MAX(COALESCE(s.last_activity_at,0),COALESCE(s.ended_at,0),s.started_at,COALESCE((SELECT MAX(m.timestamp) FROM messages m WHERE m.session_id=s.id AND m.active=1),0)) AS activity_at FROM sessions s ORDER BY activity_at DESC")]
    @contextmanager
    def history_connection(self,p):
        c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
        try: yield c
        finally: c.close()
    def snapshot(self):
        error=None
        try: history=self.history()
        except sqlite3.Error: history=[]; error='Hermes session database unavailable or incompatible'
        now=time.time()
        cutoff=now-IDLE_SECONDS
        runs=[r for r in self.runs() if r.get('status') in ('starting','working') or max(r.get('updated') or 0,r.get('started') or 0)>cutoff]
        live=self.live.snapshot() if self.live else dict(connected=False, sessions={}, error='Live observer not started', checked_at=0)
        live_rows=live['sessions']
        known={s['id'] for s in history}
        for sid, row in live_rows.items():
            if row['live_running'] and sid not in known:
                history.append(dict(id=sid,title=row['title'],source=row['source'],started_at=row.get('started_at'),ended_at=None))
        def visible(session):
            runtime=live_rows.get(session['id'],{})
            if runtime.get('live_running'):return True
            idle_at=runtime.get('idle_since')
            if idle_at is None:
                idle_at=max(session.get('activity_at') or 0,session.get('last_activity_at') or 0,session.get('started_at') or 0,session.get('ended_at') or 0)
            return now-idle_at<IDLE_SECONDS
        history=[s for s in history if visible(s)]
        for session in history:
            runtime=live_rows.get(session['id'])
            if runtime:
                # Preserve the stored title and activity time; fresh runtime observations
                # must not make old, idle projects count as recently used.
                session.update({k:runtime[k] for k in ('phase','status','action','live_running','live_updated','observed_at')})
                session.update(live=True,status_source='gateway',idle_since=runtime.get('idle_since'))
            else:
                session.update(live=False,live_running=False,phase='idle' if session.get('ended_at') else 'unknown',
                    status='ended' if session.get('ended_at') else 'unknown',
                    action='Session ended' if session.get('ended_at') else 'Live activity unavailable',status_source='history')
        history.sort(key=lambda s:(s.get('live_running',False),s.get('last_activity_at') or s.get('started_at') or 0),reverse=True)
        return dict(now=now, runs=runs, sessions=history, error=error,
                    gateway={k:v for k,v in live.items() if k!='sessions'})
    def start(self, prompt):
        with self.lock:
            if len(self.processes)>=4: raise ValueError('Four runs are already active')
            run=dict(id=secrets.token_hex(12),prompt=prompt,status='starting',phase='thinking',action='Thinking · starting Hermes',started=time.time(),updated=time.time(),events=[],text='',session_id=None)
            self.save(run); self.processes[run['id']]=None
        threading.Thread(target=self.worker,args=(run,),daemon=True).start()
        return run
    def worker(self,run):
        p=None
        try:
            # stdin keeps prompt text out of shell expansion and process arguments.
            p=subprocess.Popen([self.command,'chat','--query-file','-','--oneshot','--format','stream-json','--source','cli'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True,cwd=self.data)
            with self.lock:
                if run['id'] in self.cancelled:
                    os.killpg(p.pid,signal.SIGTERM); p.wait(); return
                self.processes[run['id']]=p
            p.stdin.write(run['prompt']); p.stdin.close()
            for line in p.stdout:
                try: event=json.loads(line)
                except ValueError: continue
                with self.lock:
                    if run['id'] in self.cancelled: continue
                    kind=event.get('type'); run['status']='working'
                    if event.get('session_id'): run['session_id']=event['session_id']
                    if kind=='system': run.update(phase='thinking',action='Thinking')
                    if kind=='tool_use': run.update(phase='working',action='Executing '+event.get('name','tool'))
                    elif kind=='tool_result': run.update(phase='thinking',action='Thinking · processing tool result')
                    elif kind=='text':
                        run['text']=(run['text']+event.get('text',''))[-100000:]
                        run.update(phase='returning',action='Writing response')
                    elif kind=='result':
                        run.update(text=event.get('text') or run['text'], status='failed' if event.get('exit_code') else 'finished',phase='idle',action=event.get('error') or 'Response ready in app')
                    run['events']=(run['events']+[dict(type=kind,name=event.get('name'),at=time.time())])[-100:]
                    run['updated']=time.time(); self.save(run)
            code=p.wait()
            with self.lock:
                if run['id'] not in self.cancelled and run['status'] in ('starting','working'):
                    run.update(status='failed' if code else 'finished',phase='idle',action='Hermes exited with code '+str(code)); self.save(run)
        except Exception as e:
            with self.lock:
                run.update(status='failed',phase='idle',action='Could not run Hermes: '+type(e).__name__); self.save(run)
        finally:
            if p:
                if p.stdin and not p.stdin.closed: p.stdin.close()
                if p.stdout: p.stdout.close()
            with self.lock: self.processes.pop(run['id'],None)
    def cancel(self,rid):
        with self.lock:
            run=next((r for r in self.runs() if r['id']==rid),None)
            if not run or rid not in self.processes: raise ValueError('Run is not active')
            self.cancelled.add(rid)
            run.update(status='cancelled',phase='idle',action='Cancellation requested'); self.save(run)
            p=self.processes[rid]
            if p:
                os.killpg(p.pid,signal.SIGTERM)
                def kill_later():
                    try: p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(p.pid,signal.SIGKILL)
                        except ProcessLookupError: pass
                threading.Thread(target=kill_later,daemon=True).start()
            return run

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,status,body,ctype='application/json',cookie=None):
        raw=json.dumps(body).encode() if ctype=='application/json' else body
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store' if self.path.startswith('/api/') else 'no-cache')
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers(); self.wfile.write(raw)
    def authorized(self):
        try:
            cookie=SimpleCookie(self.headers.get('Cookie','')); token=cookie['watch'].value
            return self.server.watch.sessions.get(token,0)>time.time()
        except (KeyError,ValueError): return False
    def do_GET(self):
        path=urlsplit(self.path).path
        if path.startswith('/api/'):
            if not self.authorized(): return self.send(401,{'error':'Sign in to continue'})
            if path=='/api/state':
                snapshot=self.server.watch.snapshot()
                user_agent=self.headers.get('User-Agent','')
                client_id=hashlib.sha256((self.headers.get('Cookie','')+user_agent).encode()).hexdigest()[:12]
                platform='Android' if 'Android' in user_agent else 'iPad' if 'iPad' in user_agent else 'iPhone' if 'iPhone' in user_agent else 'Mac' if 'Macintosh' in user_agent else 'Other'
                with self.server.watch.lock:
                    self.server.watch.clients={k:v for k,v in self.server.watch.clients.items() if time.time()-v['last_seen']<600}
                    self.server.watch.clients[client_id]=dict(platform=platform,build=self.headers.get('X-Watch-Build','unreported')[:40],mode=self.headers.get('X-Watch-Mode','unreported')[:20],last_seen=time.time(),rendered_at=self.headers.get('X-Watch-Rendered-At','unreported')[:40],rendered_active=self.headers.get('X-Watch-Rendered-Active','unreported')[:10])
                return self.send(200,snapshot)
            if path=='/api/diagnostics':
                with self.server.watch.lock: clients=list(self.server.watch.clients.values())
                return self.send(200,dict(clients=clients,gateway=self.server.watch.snapshot()['gateway']))
            if path.startswith('/api/session/'):
                try: return self.send(200,self.server.watch.history(unquote(path[13:])))
                except sqlite3.Error: return self.send(503,{'error':'Session history unavailable'})
            return self.send(404,{'error':'Not found'})
        files={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/sw.js':'sw.js','/manifest.webmanifest':'manifest.webmanifest','/dwarves.png':'dwarves.png','/geology.png':'geology.png','/icon.svg':'icon.svg','/icon-192.png':'icon-192.png','/icon-512.png':'icon-512.png'}
        if path not in files: return self.send(404,{'error':'Not found'})
        file=ROOT/'public'/files[path]
        types={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.webmanifest':'application/manifest+json','.svg':'image/svg+xml','.png':'image/png'}
        if not file.is_file():return self.send(404,{'error':'Optional asset not installed'})
        self.send(200,file.read_bytes(),types[file.suffix])
    def do_POST(self):
        # Browsers must send an exact same-origin Origin on every mutation.
        origin=urlsplit(self.headers.get('Origin',''))
        if origin.netloc!=self.headers.get('Host') or origin.scheme not in ('http','https'):
            return self.send(403,{'error':'Same-origin request required'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<0 or size>20000: return self.send(413,{'error':'Request too large'})
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError()
        except (ValueError,TypeError): return self.send(400,{'error':'Invalid JSON'})
        app=self.server.watch; path=urlsplit(self.path).path
        secure='; Secure' if origin.scheme=='https' else ''
        if path=='/api/login':
            ip=self.client_address[0]; now=time.time()
            with app.lock:
                attempts=[t for t in app.attempts.get(ip,[]) if now-t<300]
                if len(attempts)>=10: return self.send(429,{'error':'Too many attempts. Try again in five minutes.'})
                if not hmac.compare_digest(str(data.get('key','')),app.key):
                    app.attempts[ip]=attempts+[now]; return self.send(401,{'error':'Incorrect access key'})
                token=secrets.token_urlsafe(32); app.sessions[token]=now+86400*30; app.attempts.pop(ip,None)
            return self.send(200,{'ok':True},cookie=f'watch={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000{secure}')
        if not self.authorized(): return self.send(401,{'error':'Sign in to continue'})
        try:
            if path=='/api/logout':
                cookie=SimpleCookie(self.headers.get('Cookie','')); app.sessions.pop(cookie['watch'].value,None)
                return self.send(200,{'ok':True},cookie=f'watch=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{secure}')
            if path=='/api/runs':
                prompt=data.get('prompt','')
                if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>16000: raise ValueError('Enter a task under 16,000 characters')
                return self.send(202,app.start(prompt.strip()))
            if path.startswith('/api/cancel/'):
                return self.send(200,app.cancel(path[12:]))
        except ValueError as e: return self.send(400,{'error':str(e)})
        self.send(404,{'error':'Not found'})

def create_server(port=3000,watch=None):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler); server.watch=watch or Watch()
    if watch is None:
        from live_gateway import LiveGateway
        server.watch.live=LiveGateway(server.watch.home)
        server.watch.live.start()
    return server

if __name__=='__main__':
    server=create_server(int(os.environ.get('PORT','3000')))
    print(f'Agent Fort: http://127.0.0.1:{server.server_port}',flush=True)
    print(f'Sign in through the app using the key in {server.watch.data / "access-key"}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: server.shutdown()
