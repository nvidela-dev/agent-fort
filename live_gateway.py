"""Read-only Hermes runtime observer. Only list and event-replay RPCs are sent.

The bootstrap ticket stays in memory and never crosses the Watch HTTP API.
"""
import copy
import json
import socket
import threading
import time
from urllib.parse import urlsplit

import websocket


class LiveState:
    def __init__(self):
        self.rows = {}

    def listing(self, sessions, now):
        present = set()
        for entry in sessions:
            sid = entry.get('session_id') or entry.get('id')
            if not sid:
                continue
            present.add(sid)
            row = self.rows.setdefault(sid, dict(id=sid, phase='idle', status='idle', action='Idle',
                live_running=False, active_tools={}, generation=None, live_updated=now, idle_since=None))
            row.update(title=entry.get('title') or '', source=entry.get('source') or 'hermes',
                       started_at=entry.get('started_at'), observed_at=now)
            running = bool(entry.get('running'))
            if running and not row['live_running']:
                row.update(phase='thinking', status='thinking', action='Working · awaiting current step',
                           active_tools={}, live_updated=now, idle_since=None)
            elif not running and row['live_running']:
                row.update(phase='idle', status='idle', action='Idle · turn finished',
                           active_tools={}, live_updated=now, idle_since=now)
            row['live_running'] = running
        for sid, row in self.rows.items():
            if sid not in present and row['live_running']:
                row['idle_since']=now
                row.update(live_running=False, phase='idle', status='idle', action='Idle · session closed', active_tools={})

    def event(self, sid, event, now):
        row = self.rows.get(sid)
        if row is None:
            return
        kind = event.get('type', '')
        p = event.get('payload') or {}
        generation = event.get('execution_generation')
        if generation is not None:
            old = row.get('generation')
            if old is not None and generation < old:
                return
            if old != generation:
                row['active_tools'] = {}
            row['generation'] = generation
        phase, status, action = row['phase'], row['status'], row['action']
        if kind in ('message.start', 'agent.step', 'reasoning.delta', 'reasoning.available', 'thinking.delta'):
            row['live_running'] = True
            if not row['active_tools']:
                phase, status, action = 'thinking', 'thinking', 'Thinking'
        elif kind == 'tool.generating':
            row['live_running'] = True
            phase, status, action = 'thinking', 'preparing', 'Preparing ' + str(p.get('name') or 'tool')
        elif kind in ('tool.start', 'tool.started'):
            row['live_running'] = True
            name = str(p.get('name') or p.get('tool_name') or 'tool')[:120]
            cid = str(p.get('tool_id') or p.get('tool_call_id') or name)
            row['active_tools'][cid] = name
            phase, status, action = 'working', 'using tool', 'Using ' + ', '.join(row['active_tools'].values())
        elif kind in ('tool.complete', 'tool.completed'):
            cid = str(p.get('tool_id') or p.get('tool_call_id') or p.get('name') or '')
            row['active_tools'].pop(cid, None)
            if row['active_tools']:
                phase, status, action = 'working', 'using tool', 'Using ' + ', '.join(row['active_tools'].values())
            elif row['live_running']:
                phase, status, action = 'thinking', 'thinking', 'Thinking · processing tool result'
        elif kind in ('message.delta', 'message.interim') and (p.get('text') or p.get('content')):
            row['live_running'] = True
            if not row['active_tools']:
                phase, status, action = 'returning', 'replying', 'Writing reply'
        elif kind == 'message.complete':
            row.update(live_running=False, active_tools={}, idle_since=now)
            failed = bool(p.get('error') or p.get('failed') or p.get('success') is False)
            phase, status, action = ('idle', 'failed', 'Turn failed') if failed else ('idle', 'idle', 'Reply ready')
        elif kind == 'session.info':
            if p.get('running') is True:
                if not row['live_running']:
                    phase, status, action = 'thinking', 'thinking', 'Thinking'
                row['live_running'] = True
            elif p.get('running') is False:
                row.update(live_running=False, active_tools={}, idle_since=now)
                phase, status, action = 'idle', 'idle', 'Idle'
        elif kind in ('approval.request', 'clarify.request'):
            phase, status, action = 'waiting', 'waiting', 'Waiting for your input'
        elif kind == 'error':
            phase, status, action = 'idle', 'failed', 'Agent reported an error'
        if (phase, status, action) != (row['phase'], row['status'], row['action']):
            row['live_updated'] = now
        row.update(phase=phase, status=status, action=action, observed_at=now)

    def public(self):
        return {sid: {k: v for k, v in row.items() if k not in ('active_tools', 'generation')}
                for sid, row in self.rows.items()}


class LiveGateway:
    def __init__(self, home):
        self.home = home
        self.lock = threading.RLock()
        self.state = LiveState()
        self.connected = False
        self.checked_at = 0
        self.error = 'Connecting to Hermes'
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, daemon=True, name='hermes-live-observer')
            self.thread.start()

    def snapshot(self):
        with self.lock:
            healthy = self.connected and time.time() - self.checked_at < 8
            return dict(connected=healthy, checked_at=self.checked_at,
                        error=None if healthy else self.error or 'Live status unavailable',
                        sessions=copy.deepcopy(self.state.public()) if healthy else {})

    def control(self, verb, params=None):
        path = self.home / 'gateway.sock'
        if not path.exists():
            pointer = self.home / 'gateway.sock.path'
            if pointer.exists():
                path = pointer.read_text().strip()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(3)
            sock.connect(str(path))
            sock.sendall((json.dumps(dict(protocol=1, verb=verb, params=params or {})) + '\n').encode())
            with sock.makefile('rb') as stream:
                reply = json.loads(stream.readline(512 * 1024))
            if not reply.get('ok'):
                raise RuntimeError('Gateway refused observer connection')
            return reply['result']

    def active_internal_sessions(self, epoch):
        import sqlite3
        path=self.home/'state.db'
        if not path.exists():return []
        conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
        try:
            conn.row_factory=sqlite3.Row
            return [dict(row) for row in conn.execute("SELECT s.id,s.title,s.source,s.started_at,1 AS running FROM sessions s WHERE EXISTS (SELECT 1 FROM session_admissions a WHERE a.target_session_id=s.id AND a.status='started' AND a.owner_epoch=?) OR EXISTS (SELECT 1 FROM worker_executions w WHERE w.session_id=s.id AND w.status='running' AND w.owner_epoch=?)",(epoch,epoch))]
        except sqlite3.Error:
            return []
        finally:conn.close()

    def run(self):
        while not self.stop.is_set():
            ws = None
            try:
                owner = self.control('identify')
                origin = owner['api_origin']
                if urlsplit(origin).hostname not in ('127.0.0.1', '::1', 'localhost'):
                    raise RuntimeError('Gateway address is not loopback')
                ticket = self.control('session-ticket', dict(profile_id=str(self.home),
                    instance_id=owner['instance_id'], purpose='interactive'))['ticket']
                ws = websocket.create_connection(origin.replace('http:', 'ws:').replace('https:', 'wss:') + '/api/ws',
                    subprotocols=['hermes-gateway-v1', 'hermes-gateway-ticket.' + ticket],
                    suppress_origin=True, timeout=4)
                del ticket
                sequence = 0
                cursors = {}
                def rpc(method, params):
                    nonlocal sequence
                    if method not in ('session.list', 'session.events.since'):
                        raise ValueError('Observer RPC is read-only')
                    sequence += 1
                    ws.send(json.dumps(dict(jsonrpc='2.0', id=sequence, method=method, params=params)))
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        frame = json.loads(ws.recv())
                        if frame.get('id') == sequence:
                            if 'error' in frame:
                                raise RuntimeError('Gateway read failed')
                            return frame.get('result', {})
                    raise TimeoutError('Gateway read timed out')
                with self.lock:
                    self.state = LiveState()
                while not self.stop.is_set():
                    entries = rpc('session.list', {'scope': 'live', 'limit': 200, 'include_hidden':True}).get('sessions', [])
                    entries={e.get('session_id') or e['id']:e for e in entries}
                    for e in self.active_internal_sessions(owner.get('authority_epoch',-1)):
                        entries.setdefault(e['id'],e)
                    entries=list(entries.values())
                    with self.lock:
                        self.state.listing(entries, time.time())
                    for entry in entries:
                        sid = entry.get('session_id') or entry['id']
                        cursor = cursors.get(sid, {})
                        try:
                            replay = rpc('session.events.since', dict(session_id=sid,
                                last_sequence=cursor.get('seq', 0), replay_epoch=cursor.get('epoch')))
                            if replay.get('snapshot_required'):
                                # Recover the latest step on initial connection/reconnect, without
                                # replaying old animations or requiring a viewer attachment.
                                replay = rpc('session.events.since', dict(session_id=sid,
                                    last_sequence=max(0,replay['latest_seq']-50), replay_epoch=replay['replay_epoch']))
                        except RuntimeError:
                            with self.lock:
                                row=self.state.rows[sid]
                                row.update(status='working' if entry.get('running') else 'unknown',action='Active session · live tool detail unavailable' if entry.get('running') else 'Live tool detail unavailable')
                            continue
                        cursors[sid] = dict(seq=replay['latest_seq'], epoch=replay['replay_epoch'])
                        with self.lock:
                            for event in replay.get('events', []):
                                self.state.event(sid, event, time.time())
                            # Initial replay can contain an old turn. The live list is the
                            # authority for an idle session; old events must not revive it.
                            if not entry.get('running') and not cursor:
                                row=self.state.rows[sid]
                                row.update(live_running=False, phase='idle', status='idle', action='Idle', active_tools={}, idle_since=None)
                    with self.lock:
                        self.connected=True; self.checked_at=time.time(); self.error=None
                    self.stop.wait(0.7)
            except Exception as exc:
                with self.lock:
                    self.connected=False
                    self.error='Hermes live connection unavailable (' + type(exc).__name__ + ')'
            finally:
                if ws:
                    ws.close()
            self.stop.wait(2)
