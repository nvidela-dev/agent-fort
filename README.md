<div align="center">

# Agent Fort

**Your Hermes agents, at work in a tiny fortress.**

A private, self-hosted PWA for watching agents think, use tools, and reply—from your phone, tablet, or computer.

[Get started](#quick-start) · [Phone & tablet](#phone--tablet) · [How it works](#how-it-works) · [Troubleshooting](#troubleshooting)

</div>

https://github.com/user-attachments/assets/90c78d43-603c-4f0c-b350-09a245d37205

*Actual app recording: two real Hermes terminal tasks, live activity labels, and walking dwarves. A quiet wait near the end is shortened. [Download the MP4](docs/agent-fort-demo.mp4).*

Agent Fort turns each Hermes session into a dwarf on a horizontal lane. The map occupies almost the entire screen. Thin status bars, pixel graphics, and labels above working dwarves keep the important part visible: what your agents are doing right now.

- **Live activity:** Thinking, Using tool, Replying, Waiting, Idle, or Unknown.
- **Visible travel:** dwarves walk to the workshop and back, including brief tasks.
- **Every session type:** Telegram, CLI, Desktop, cron, subagents, and other stored sessions in the selected Hermes home. The observer also discovers current-epoch internal workers omitted from Hermes's conversation picker.
- **Automatic cleanup:** active agents stay; dwarves leave after **six idle minutes**. This only removes them from the map—Hermes history is preserved.
- **Subtle channels:** teal **TG** markers identify Telegram; other sessions use a muted source marker.
- **Installable PWA:** add it to your Home Screen for a glanceable agent monitor.
- **Private by default:** one loopback server, an access key, authenticated APIs, and optional private HTTPS through Tailscale.

## Quick start

### Requirements

- macOS or Linux, Python **3.10+**.
- A working [Hermes Agent](https://hermes-agent.nousresearch.com/docs) installation and a running Hermes gateway on the **same machine/user**.
- The Hermes CLI available on `PATH`, or configured with `HERMES_BIN`.

The live adapter was tested against **Hermes 0.22.5**, using its `hermes-gateway-v1` protocol. It needs the gateway's local control socket, runtime tickets, `session.list`, and `session.events.since`. Older Hermes builds without these capabilities show unavailable live status; saved chat history alone cannot supply live thinking/tool status. Native Windows is not currently supported by the Unix-socket adapter.

```sh
git clone https://github.com/nvidela-dev/agent-fort.git
cd agent-fort
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Make sure Hermes's gateway is running:

```sh
hermes gateway status
# If you have installed Hermes's gateway service:
hermes gateway start
# Or run it in another terminal:
# hermes gateway run
```

Start Agent Fort:

```sh
.venv/bin/python server.py
```

Open **http://127.0.0.1:3000**. On the first run, the server generates a key at `.data/access-key`. Read that file locally and enter its contents in the app:

```sh
cat .data/access-key
```

No frontend build, Node installation, cloud account, or external database is required to run the app. The supplied dwarf and geology tilesheets are included and used automatically. Original procedural graphics remain available as a fallback.

### Connect another Hermes home

```sh
HERMES_HOME="$HOME/.hermes/profiles/work" \
HERMES_BIN="$HOME/.local/bin/hermes" \
PORT=3000 \
.venv/bin/python server.py
```

The selected home's gateway must serve that profile. Each Agent Fort server watches one Hermes home. Keep credentials in your own Hermes configuration; Agent Fort does not need a copy of your model API keys.

## Phone & tablet

The simplest private setup uses [Tailscale](https://tailscale.com/download).

1. Install Tailscale on the host computer **and** your phone/tablet. Sign into the same tailnet and connect each device.
2. Keep Agent Fort running, then run this on the host:

   ```sh
   tailscale serve --bg http://localhost:3000
   ```

3. If prompted, use the account-specific link to enable HTTPS/Serve, then rerun the command.
4. Open the HTTPS URL Tailscale prints on your phone/tablet and enter your Agent Fort access key.
5. Install the PWA with **Add to Home Screen** or your browser's **Install app** option.

A changing home internet IP is fine: your Tailscale address stays stable. The host needs to remain awake. This setup is tailnet-private; it does not enable public Tailscale Funnel or expose your Hermes administration server.

## Controls

| Control | Action |
| --- | --- |
| Tap a dwarf or lane | Open its conversation or run details |
| `+` / `−` | Change tile scale |
| `?` | Legend, app version, and last successful sync |
| Command bar | Start a new task using your Hermes configuration |
| Stop, inside an app-run detail | Terminate the process group of that app-started run |
| Update | Fetch the newest PWA version |
| Lock | Sign out |

The command bar starts a new Hermes CLI session; it does not send a message into an existing Telegram conversation. Interactive approvals and session continuation are not yet implemented. No approval-bypass flags are added. Non-interactive approval behavior follows your Hermes configuration.

## How it works

```text
Hermes gateway ── authenticated local WebSocket ──┐
                                                ├─ Agent Fort ── HTTPS/Tailscale ── PWA
Hermes state.db ─────── read-only SQLite ─────────┘
```

A local observer obtains a short-lived ticket through `gateway.sock`, reads live execution status and replay events over a loopback WebSocket, and reconnects after gateway restarts. It also reads current-epoch worker/admission records to discover internal sessions. Saved sessions supply titles, parent links, and timestamps. Session discovery has no source or 60-session cutoff.

The map follows these phases:

| Hermes activity | Dwarf behavior |
| --- | --- |
| Turn starts / model step | Walk to the workshop; **Thinking** |
| Tool starts | Work at the workshop; show the tool name |
| Tool completes | Continue thinking, or keep working while parallel tools remain |
| Reply text streams | Walk back toward chat; **Replying** |
| Turn completes | **Idle**; remove from the map after six minutes |
| Live feed is unavailable | **Unknown**; freeze the last known position |

Each crossing lasts about 1.8 seconds with a brief pause at its destination. Short state changes queue complete crossings; labels always show the current activity, even while a prior crossing finishes. Dwarves stay on their horizontal lane.

The idle timer starts when an observed live turn becomes idle. For previously idle sessions, it uses the newest saved message/activity/end timestamp. Repeated observer polls do not keep an idle session alive. Active sessions remain visible regardless of age. A completion event means a reply is ready; it does not prove delivery to Telegram.

### Privacy and access

- The HTTP server binds only to `127.0.0.1`.
- API requests need an authenticated HttpOnly cookie. Mutations require a same-origin request.
- `.data/`, virtual environments, credentials, and logs are Git-ignored.
- The observer sends no prompts or session-control RPCs. Monitoring does not stop, resume, or alter existing Hermes sessions.
- Activity projection forwards tool names and status, not reasoning text or tool arguments/results. Opening conversation history deliberately retrieves stored messages to your authenticated browser.
- Private API/history responses are never service-worker cached. The app shell can open offline; private history is not available on a fresh offline launch.
- Authentication currently resets on server restart. Rotate the access key by stopping the app, deleting `.data/access-key`, and restarting.

## Automatic startup on macOS

```sh
.venv/bin/python scripts/install-service.py
```

This installs a per-user LaunchAgent named `local.agent-fort`, starts it now, and restarts it at login or after a crash. The installer copies the app and its WebSocket dependency into `~/Library/Application Support/Agent Fort/` so background startup does not depend on launching code from a protected Documents folder. The access key, run database and logs live in that runtime's `.data/` folder. An existing checkout key/database are imported on first installation; later installs preserve runtime data. It starts after login, not before the macOS login screen. Keep the host awake for remote access.

After pulling new source or changing custom tiles, rerun the installer to update the installed runtime. For foreground development, continue using `.venv/bin/python server.py` from the checkout instead.

```sh
# Stop the user service:
launchctl bootout gui/$(id -u)/local.agent-fort

# Start/reinstall it:
.venv/bin/python scripts/install-service.py
```

On Linux, run the foreground command under your preferred process manager. Run it as the same user who owns the Hermes gateway socket; do not run it as root to work around socket permissions.

## Included tiles and custom graphics

The character and geology PNGs used in the app are bundled in `public/`, so a clone or release download includes the same look. See [graphics attribution](public/ASSETS.md) and [custom graphics](docs/custom-graphics.md). The renderer samples 16×16 characters and 32×32 terrain regions with pixel smoothing disabled.

## Troubleshooting

**The link does not open on a phone/tablet**

Check that Tailscale is connected on both devices, the host is awake, and `tailscale serve status` points to the correct local port. A `.ts.net` link is private and will not work from a device outside your tailnet.

**Dwarves appear but live status says Unknown/offline**

Check `hermes gateway status`, the selected `HERMES_HOME`, and Hermes's version/protocol compatibility. Your account must have access to that home's local socket. Reading stored sessions is possible even when the live gateway is unavailable; it does not prove live monitoring is connected.

**The map is empty**

It may be correct: only active sessions and sessions idle for less than six minutes appear. Send a tool-using task to your own Hermes and watch the state change. Telegram tasks must reach the bot associated with the selected Hermes home.

**The installed PWA looks old or stops updating**

Tap **Update**, or fully close it from the device's app switcher and reopen. The connection bar includes a revision, currently `r10`. Status reads time out and retry, and the app checks for service-worker updates. The `?` panel shows the last successful sync. Signing in again may be necessary after a server restart.

**Local diagnostics**

An authenticated `GET /api/diagnostics` shows the gateway connection and recent clients' platform category, app revision, display mode, last poll, and last render acknowledgment. These diagnostics stay in memory for ten minutes; they contain no cookies, full user agents, task text, or tool output.

## Development

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/movement.test.cjs
node --check public/app.js
node --check public/sw.js
```

Node 20+ is needed only for the JavaScript tests. See [CONTRIBUTING.md](CONTRIBUTING.md) for the layout and contribution workflow.

## License

[MIT](LICENSE) for Agent Fort code and original built-in artwork. The bundled third-party tilesheets are excluded from the MIT grant; see [asset attribution](public/ASSETS.md). Agent Fort is an independent project and is not affiliated with Nous Research or Dwarf Fortress.
