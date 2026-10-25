"""Install Agent Fort as a per-user macOS LaunchAgent."""
import os
import pathlib
import plistlib
import shutil
import subprocess
import sys

if sys.platform != 'darwin':
    sys.exit('This installer is for macOS. On Linux, use your preferred user process manager.')
root=pathlib.Path(__file__).resolve().parents[1]
label='local.agent-fort'
folder=pathlib.Path.home()/'Library/LaunchAgents'
folder.mkdir(parents=True,exist_ok=True)
data=root/'.data';data.mkdir(mode=0o700,exist_ok=True)
agent=folder/(label+'.plist')
if agent.exists():
    current=plistlib.loads(agent.read_bytes())
    if pathlib.Path(current.get('WorkingDirectory','/')).resolve()!=root:
        sys.exit('An Agent Fort service already belongs to another checkout; refusing to replace it.')
environment={'PATH':os.environ['PATH'],'HERMES_BIN':os.environ.get('HERMES_BIN') or shutil.which('hermes') or 'hermes'}
for name in ('HERMES_HOME','PORT'):
    if name in os.environ:environment[name]=os.environ[name]
config={'Label':label,'ProgramArguments':[sys.executable,str(root/'server.py')],
        'WorkingDirectory':str(root),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':10,
        'EnvironmentVariables':environment,'StandardOutPath':str(data/'server.log'),
        'StandardErrorPath':str(data/'error.log')}
agent.write_bytes(plistlib.dumps(config));agent.chmod(0o600)
domain='gui/'+str(os.getuid())
# Migrate only this project's old managed service, preserving its plist for recovery.
legacy=folder/'local.hermes-watch.plist'
if legacy.exists():
    old=plistlib.loads(legacy.read_bytes())
    old_root=pathlib.Path(old.get('WorkingDirectory','/')).resolve()
    if old_root in (root,root.parent/'hermes-watch'):
        shutil.copy2(legacy,data/'legacy-launchagent.plist')
        subprocess.run(['launchctl','bootout',domain,str(legacy)],capture_output=True)
        legacy.unlink()
subprocess.run(['launchctl','bootout',domain,str(agent)],capture_output=True)
subprocess.run(['launchctl','bootstrap',domain,str(agent)],check=True)
print('Installed and started '+label)
