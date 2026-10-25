# Contributing to Agent Fort

Use a virtual environment, install `requirements.txt`, and run the checks in the README before opening a pull request.

- `server.py`: authenticated same-origin HTTP server, session discovery, six-minute idle filtering, and app-started runs.
- `live_gateway.py`: read-only Hermes runtime transport and activity projection.
- `public/app.js`: canvas map, sprite sampling, walk state machine, activity bubbles, and PWA controls.
- `public/sw.js`: app-shell caching; never cache authenticated API responses.
- `scripts/install-service.py`: optional macOS user-service installation.
- `tests/`: server, event projection, idle expiry, and walk behavior checks.

Keep the interface compact and map-first. Show observed activity, label unknown state explicitly, and preserve horizontal travel. Do not infer live thinking from an old transcript or refresh an idle timer merely because the observer polled a session.

Use fake gateway/session fixtures for tests. Avoid model calls, Telegram sends, or reads from your real Hermes home in automated tests. Never commit `.data/`, credentials, logs, private session screenshots, or additional third-party assets without attribution and reuse terms. Include a reproducible test for behavioral bugs and clear validation notes in a pull request.
