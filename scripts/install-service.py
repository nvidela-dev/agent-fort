"""Install an isolated Agent Fort runtime as a per-user macOS LaunchAgent."""
import importlib.util
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
runtime=pathlib.Path.home()/'Library/Application Support/Agent Fort'
marker=runtime/'source-checkout'
agent=folder/(label+'.plist')
if agent.exists():
    current=plistlib.loads(agent.read_bytes())
    old_root=pathlib.Path(current.get('WorkingDirectory','/')).resolve()
    if old_root not in (root,runtime) or (marker.exists() and pathlib.Path(marker.read_text().strip()).resolve()!=root):
        sys.exit('An Agent Fort service already belongs to another checkout; refusing to replace it.')
spec=importlib.util.find_spec('websocket')
if spec is None or not spec.submodule_search_locations:
    sys.exit('Install requirements.txt into your virtualenv before installing the service.')
domain='gui/'+str(os.getuid())
subprocess.run(['launchctl','bootout',domain,str(agent)],capture_output=True)
# Use the standard Application Support location: launchd may refuse execution,
# working directories, or log paths inside protected Documents folders.
runtime.mkdir(parents=True,exist_ok=True)
for name in ('server.py','live_gateway.py'):
    shutil.copy2(root/name,runtime/name)
shutil.copytree(root/'public',runtime/'public',dirs_exist_ok=True)
vendor=runtime/'vendor';vendor.mkdir(exist_ok=True)
if (vendor/'websocket').exists():shutil.rmtree(vendor/'websocket')
shutil.copytree(pathlib.Path(next(iter(spec.submodule_search_locations))),vendor/'websocket',ignore=shutil.ignore_patterns('__pycache__'))
data=runtime/'.data';data.mkdir(mode=0o700,exist_ok=True)
for name in ('access-key','watch.db'):
    source=root/'.data'/name
    if source.exists() and not (data/name).exists():shutil.copy2(source,data/name)
marker.write_text(str(root)+'\n')
environment={'PATH':os.environ['PATH'],'PYTHONPATH':str(vendor),
             'HERMES_BIN':os.environ.get('HERMES_BIN') or shutil.which('hermes') or 'hermes'}
for name in ('HERMES_HOME','PORT'):
    if name in os.environ:environment[name]=os.environ[name]
config={'Label':label,'ProgramArguments':[str(pathlib.Path(sys.executable).resolve()),str(runtime/'server.py')],
        'WorkingDirectory':str(runtime),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':10,
        'EnvironmentVariables':environment,'StandardOutPath':str(data/'server.log'),
        'StandardErrorPath':str(data/'error.log')}
agent.write_bytes(plistlib.dumps(config));agent.chmod(0o600)
legacy=folder/'local.hermes-watch.plist'
if legacy.exists():
    old=plistlib.loads(legacy.read_bytes())
    old_root=pathlib.Path(old.get('WorkingDirectory','/')).resolve()
    if old_root in (root,root.parent/'hermes-watch'):
        shutil.copy2(legacy,data/'legacy-launchagent.plist')
        subprocess.run(['launchctl','bootout',domain,str(legacy)],capture_output=True)
        legacy.unlink()
subprocess.run(['launchctl','bootstrap',domain,str(agent)],check=True)
print('Installed and started '+label)
print('Runtime: '+str(runtime))
print('Access key: '+str(data/'access-key'))
