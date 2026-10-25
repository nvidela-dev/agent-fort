import unittest
from activity import project_activity
class ActivityTests(unittest.TestCase):
 def msg(self,i,role,**kwargs):return dict(id=i,role=role,timestamp=i,**kwargs)
 def test_start_result_reply(self):
  user=self.msg(1,'user');start=self.msg(2,'assistant',tool_calls='[{"id":"a","function":{"name":"terminal"}}]');result=self.msg(3,'tool',tool_call_id='a');reply=self.msg(4,'assistant')
  self.assertEqual(project_activity([user])['phase'],'outbound')
  self.assertEqual(project_activity([user,start])['phase'],'working')
  self.assertEqual(project_activity([user,start,result])['phase'],'returning')
  projection=project_activity([user,start,result,reply]);self.assertEqual(projection['phase'],'idle');self.assertEqual([e['type'] for e in projection['activity_events']],['prompt','tool_use','tool_result','reply'])
 def test_parallel_calls_wait_for_all_results(self):
  start=self.msg(1,'assistant',tool_calls=[dict(id='a',function={'name':'read'}),dict(id='b',function={'name':'search'})])
  self.assertEqual(project_activity([start,self.msg(2,'tool',tool_call_id='a')])['phase'],'working')
  self.assertEqual(project_activity([start,self.msg(2,'tool',tool_call_id='a'),self.msg(3,'tool',tool_call_id='b')])['phase'],'returning')
 def test_bad_calls_do_not_break_poll(self):
  self.assertEqual(project_activity([self.msg(1,'assistant',tool_calls='invalid')])['phase'],'idle')
