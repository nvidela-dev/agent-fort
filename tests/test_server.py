import http.client,json,tempfile,threading,time,unittest
from pathlib import Path
from server import Watch,create_server
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);fake=root/'hermes'
  fake.write_text('#!/usr/bin/env python3\nimport sys,json,time\np=sys.stdin.read()\nassert sys.argv[sys.argv.index("--source")+1]=="cli", "unsupported gateway source"\nprint(json.dumps({"type":"tool_use","name":"test"}),flush=True)\ntime.sleep(1 if p=="slow" else .05)\nprint(json.dumps({"type":"tool_result","name":"test"}),flush=True)\nprint(json.dumps({"type":"result","text":p,"session_id":"fake","exit_code":0}),flush=True)\n');fake.chmod(0o700)
  self.watch=Watch(root/'data',root/'missing',str(fake));self.server=create_server(0,self.watch);threading.Thread(target=self.server.serve_forever,daemon=True).start();self.cookie=''
 def tearDown(self):
  for rid in list(self.watch.processes):
   try:self.watch.cancel(rid)
   except ValueError:pass
  deadline=time.time()+3
  while self.watch.processes and time.time()<deadline:time.sleep(.02)
  self.server.shutdown();self.server.server_close();self.tmp.cleanup()
 def req(self,path,body=None,origin=True):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);headers={'Cookie':self.cookie}
  if origin:headers['Origin']=f'http://127.0.0.1:{self.server.server_port}'
  c.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers);r=c.getresponse();raw=r.read();status=r.status;cookie=r.getheader('Set-Cookie');ctype=r.getheader('Content-Type');c.close()
  if cookie:self.cookie=cookie.split(';')[0]
  return status,json.loads(raw) if ctype=='application/json' else raw
 def login(self):self.assertEqual(self.req('/api/login',{'key':self.watch.key})[0],200)
 def test_auth_origin_and_static_isolation(self):
  self.assertEqual(self.req('/api/state')[0],401);self.assertEqual(self.req('/api/login',{'key':self.watch.key},False)[0],403);self.assertEqual(self.req('/.data/access-key')[0],404);self.assertEqual(self.req('/../server.py')[0],404)
  self.login();self.assertEqual(self.req('/api/state')[0],200);self.assertEqual(self.req('/api/runs',{'prompt':'hi'},False)[0],403);self.req('/api/logout',{});self.assertEqual(self.req('/api/state')[0],401)
 def test_literal_dispatch(self):
  self.login();prompt='literal $(touch nope) `id` <script>alert(1)</script>';status,run=self.req('/api/runs',{'prompt':prompt});self.assertEqual(status,202)
  for _ in range(100):
   result=self.watch.runs()[0]
   if result['status']=='finished':break
   time.sleep(.02)
  self.assertEqual(result['text'],prompt);self.assertEqual(result['phase'],'idle');self.assertEqual(result['session_id'],'fake');self.assertEqual([e['type'] for e in result['events']],['tool_use','tool_result','result'])
 def test_cancellation(self):
  self.login();_,run=self.req('/api/runs',{'prompt':'slow'});self.assertEqual(self.req('/api/cancel/'+run['id'],{})[0],200);time.sleep(.15);self.assertEqual(self.watch.runs()[0]['status'],'cancelled')
 def test_restart_and_validation(self):
  self.login();self.assertEqual(self.req('/api/runs',{'prompt':[]})[0],400);self.watch.save(dict(id='old',status='working',started=0));restarted=Watch(self.watch.data,self.watch.home,self.watch.command);self.assertEqual(restarted.runs()[0]['status'],'interrupted')
 def test_pwa(self):
  status,raw=self.req('/manifest.webmanifest');self.assertEqual(status,200);self.assertEqual(json.loads(raw)['display'],'standalone');self.assertIn(b"u.pathname.startsWith('/api/')",self.req('/sw.js')[1])
 def test_six_minute_window_keeps_active_runs_and_expires_at_boundary(self):
  from unittest.mock import patch
  now=10000
  self.watch.save(dict(id='active',status='working',started=1,updated=2))
  self.watch.save(dict(id='stale',status='finished',started=1,updated=9639))
  self.watch.save(dict(id='boundary',status='finished',started=1,updated=9641))
  self.watch.save(dict(id='exactly-six-minutes',status='finished',started=1,updated=9640))
  self.watch.history=lambda: [dict(id='old-open',started_at=1,ended_at=None,last_activity_at=9639),dict(id='recent',started_at=1,last_activity_at=9641),dict(id='just-ended',started_at=1,last_activity_at=1,ended_at=9999)]
  with patch('server.time.time',return_value=now): snapshot=self.watch.snapshot()
  self.assertEqual({r['id'] for r in snapshot['runs']},{'active','boundary'})
  self.assertEqual({s['id'] for s in snapshot['sessions']},{'recent','just-ended'})
 def test_live_runtime_overrides_idle_history_and_keeps_old_active_session(self):
  from unittest.mock import patch
  from types import SimpleNamespace
  self.watch.history=lambda:[dict(id='s',started_at=1,last_activity_at=2,ended_at=None)]
  row=dict(id='s',title='Busy',source='telegram',started_at=1,phase='thinking',status='thinking',action='Thinking',live_running=True,live_updated=9999,observed_at=10000)
  self.watch.live=SimpleNamespace(snapshot=lambda:dict(connected=True,sessions={'s':row},error=None,checked_at=10000))
  with patch('server.time.time',return_value=10000):snapshot=self.watch.snapshot()
  self.assertEqual(len(snapshot['sessions']),1);self.assertEqual(snapshot['sessions'][0]['phase'],'thinking');self.assertTrue(snapshot['sessions'][0]['live'])
 def test_device_diagnostics_require_login_and_report_last_render(self):
  self.assertEqual(self.req('/api/diagnostics')[0],401)
  self.login()
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
  c.request('GET','/api/state',headers={'Cookie':self.cookie,'User-Agent':'Android tablet test','X-Watch-Build':'2026.10.25.10','X-Watch-Mode':'standalone','X-Watch-Rendered-At':'10000','X-Watch-Rendered-Active':'1'})
  r=c.getresponse();r.read();self.assertEqual(r.status,200);c.close()
  status,data=self.req('/api/diagnostics');self.assertEqual(status,200)
  self.assertEqual(data['clients'][0]['build'],'2026.10.25.10');self.assertEqual(data['clients'][0]['rendered_active'],'1');self.assertNotIn(self.cookie,json.dumps(data));self.assertNotIn('Android tablet test',json.dumps(data))

 def test_idle_timeout_starts_when_long_running_turn_finishes(self):
  from unittest.mock import patch
  from types import SimpleNamespace
  self.watch.history=lambda:[dict(id='long',source='telegram',started_at=1,last_activity_at=2,ended_at=None)]
  row=dict(id='long',title='Busy',source='telegram',started_at=1,phase='idle',status='idle',action='Idle',live_running=False,live_updated=9900,observed_at=10000,idle_since=9900)
  self.watch.live=SimpleNamespace(snapshot=lambda:dict(connected=True,sessions={'long':row},error=None,checked_at=10000))
  with patch('server.time.time',return_value=10259):self.assertEqual(len(self.watch.snapshot()['sessions']),1)
  with patch('server.time.time',return_value=10260):self.assertEqual(len(self.watch.snapshot()['sessions']),0)
 def test_all_session_sources_are_kept_when_recent(self):
  from unittest.mock import patch
  self.watch.history=lambda:[dict(id=source,source=source,started_at=9999,last_activity_at=9999) for source in ('telegram','local','gui','cron','subagent','oneshot','kanban','tool')]
  with patch('server.time.time',return_value=10000):snapshot=self.watch.snapshot()
  self.assertEqual(len(snapshot['sessions']),8)
 def test_discovery_has_no_source_hidden_or_sixty_session_limit(self):
  import sqlite3
  from unittest.mock import patch
  self.watch.home.mkdir()
  c=sqlite3.connect(self.watch.home/'state.db')
  c.execute('CREATE TABLE sessions(id TEXT,title TEXT,source TEXT,parent_session_id TEXT,model TEXT,started_at REAL,ended_at REAL,last_activity_at REAL,last_activity_description TEXT,tool_call_count INTEGER,hidden INTEGER)')
  c.execute('CREATE TABLE messages(session_id TEXT,timestamp REAL,active INTEGER)')
  c.executemany('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',[(str(i),'test','subagent' if i%2 else 'telegram',None,None,1,None,9990,'',0,1) for i in range(70)])
  c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',('message-only','test','oneshot',None,None,1,None,1,'',0,1))
  c.execute('INSERT INTO messages VALUES(?,?,?)',('message-only',9995,1))
  c.commit();c.close()
  with patch('server.time.time',return_value=10000):snapshot=self.watch.snapshot()
  self.assertEqual(len(snapshot['sessions']),71)
