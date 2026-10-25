"""Project observed Hermes transcript events into workshop phases."""
import json

def project_activity(messages):
    events=[];pending={};phase='idle';action='Response recorded'
    for m in messages:
        role=m['role'];mid=m['id'];stamp=m['timestamp']
        if role=='user':
            pending.clear();phase='outbound';action='Preparing response'
            events.append(dict(id=f'{mid}:prompt',type='prompt',at=stamp))
        calls=m.get('tool_calls')
        if calls:
            try: calls=json.loads(calls) if isinstance(calls,str) else calls
            except ValueError: calls=[]
            if not isinstance(calls,list): calls=[]
            for i,call in enumerate(calls):
                if not isinstance(call,dict):continue
                cid=call.get('id') or call.get('call_id') or f'{mid}:{i}'
                name=(call.get('function') or {}).get('name') or call.get('name') or 'tool'
                pending[cid]=name;phase='working';action='Executing '+name
                events.append(dict(id=f'{mid}:start:{i}',type='tool_use',name=name,call_id=cid,at=stamp))
        if role=='tool':
            cid=m.get('tool_call_id');name=pending.pop(cid,None) or m.get('tool_name') or 'tool'
            phase='working' if pending else 'returning';action='Executing '+next(iter(pending.values())) if pending else 'Tool result received; preparing reply'
            events.append(dict(id=f'{mid}:result',type='tool_result',name=name,call_id=cid,at=stamp))
        elif role=='assistant' and not calls:
            if not pending:
                phase='idle';action='Response recorded'
                events.append(dict(id=f'{mid}:reply',type='reply',at=stamp))
    return dict(phase=phase,action=action,activity_events=events)
