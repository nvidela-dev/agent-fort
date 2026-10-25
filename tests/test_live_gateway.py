import unittest
from unittest.mock import patch
from pathlib import Path
from live_gateway import LiveState,LiveGateway

class LiveTests(unittest.TestCase):
 def setUp(self):
  self.state=LiveState();self.state.listing([dict(id='s',running=True,source='telegram')],100)
 def event(self,kind,payload=None,generation=1):
  self.state.event('s',dict(type=kind,payload=payload or {},execution_generation=generation),101)
  return self.state.public()['s']
 def test_live_thinking_exists_before_any_saved_message(self):
  row=self.event('agent.step',{'iteration':2});self.assertTrue(row['live_running']);self.assertEqual(row['status'],'thinking');self.assertEqual(row['phase'],'thinking')
 def test_parallel_tools_thinking_reply_idle(self):
  self.event('tool.start',{'tool_id':'a','name':'terminal'})
  self.event('tool.start',{'tool_id':'b','name':'read_file'})
  row=self.event('tool.complete',{'tool_id':'a'});self.assertEqual(row['phase'],'working');self.assertIn('read_file',row['action'])
  row=self.event('tool.complete',{'tool_id':'b'});self.assertEqual(row['phase'],'thinking')
  row=self.event('message.delta',{'text':'sensitive response not copied'});self.assertEqual(row['status'],'replying');self.assertNotIn('sensitive',str(row))
  row=self.event('message.complete');self.assertEqual(row['phase'],'idle');self.assertFalse(row['live_running'])
 def test_old_generation_cannot_finish_new_turn(self):
  self.event('message.start',generation=3);row=self.event('message.complete',generation=2);self.assertTrue(row['live_running'])
 def test_idle_runtime_does_not_revive_old_history(self):
  self.state.listing([dict(id='s',running=False)],105);self.assertEqual(self.state.public()['s']['status'],'idle')
 def test_stale_connection_drops_live_claims(self):
  live=LiveGateway(Path('/nonexistent'));live.state=self.state;live.connected=True;live.checked_at=100
  with patch('live_gateway.time.time',return_value=109):snapshot=live.snapshot()
  self.assertFalse(snapshot['connected']);self.assertEqual(snapshot['sessions'],{})

 def test_idle_since_does_not_reset_when_polled(self):
  self.event('message.complete')
  self.assertEqual(self.state.public()['s']['idle_since'],101)
  self.state.listing([dict(id='s',running=False)],300)
  self.assertEqual(self.state.public()['s']['idle_since'],101)
 def test_internal_workers_are_discovered_only_for_current_epoch(self):
  import sqlite3,tempfile
  with tempfile.TemporaryDirectory() as folder:
   home=Path(folder);c=sqlite3.connect(home/'state.db')
   c.execute('CREATE TABLE sessions(id TEXT,title TEXT,source TEXT,started_at REAL)')
   c.execute('CREATE TABLE session_admissions(target_session_id TEXT,status TEXT,owner_epoch INTEGER)')
   c.execute('CREATE TABLE worker_executions(session_id TEXT,status TEXT,owner_epoch INTEGER)')
   c.executemany('INSERT INTO sessions VALUES(?,?,?,?)',[('child','child','subagent',1),('old','old','oneshot',1),('turn','turn','tool',1)])
   c.executemany('INSERT INTO worker_executions VALUES(?,?,?)',[('child','running',4),('old','running',3)])
   c.execute('INSERT INTO session_admissions VALUES(?,?,?)',('turn','started',4));c.commit();c.close()
   rows=LiveGateway(home).active_internal_sessions(4)
   self.assertEqual({r['id'] for r in rows},{'child','turn'})
