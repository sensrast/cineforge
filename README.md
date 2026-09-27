# CineForge

CineForge is an asynchronous Telegram MTProto queue worker plus a private control bot. It searches Movie Hunt, selects Hindi/Dual Audio qualities, asks Telegram to copy media server-side into a new channel, builds a file-store batch, shortens its URL, publishes a pinned post, and optionally runs a catalog-bot wizard.

## Important behavior

- **No movie is downloaded to the host.** Stage 6 uses Telegram `copy_message`; Stage 7 uses `forward_messages`. The catalog stage reuses a Telegram cached thumbnail `file_id` when one exists.
- Runtime limits default to off, but Telegram `FloodWait` is always honored for `e.value + 1` seconds.
- Jobs and stage outputs are persisted in SQLite and interrupted active jobs are resumed after restart.
- Bot interfaces are third-party UIs. If their labels or flow change, the relevant job fails with an audit entry rather than guessing destructively.
- Only process content for which you have the necessary rights and follow Telegram and third-party service terms.

## Local setup

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill API_ID, API_HASH and USERBOT_PHONE first
python main.py --generate-session
# Put the printed session in USERBOT_SESSION_STRING and fill remaining values
python main.py
```

Never commit `.env` or a session string. If a token has been pasted into a chat, issue a replacement before production use.

## Control commands

- `/add <title>` or plain text
- `/batch`, then one title per line
- `/status`, `/logs [count]`
- `/settings`, `/toggle_limits`
- `/pause`, `/resume`
- `/cancel <id>`, `/retry <id>`

`/settings` exposes inline toggles and numeric prompts. A max-channel value of `0` means unlimited.

## Render

A `Dockerfile` and `render.yaml` are included. The service exposes:

- `/` — JSON health status
- `/health` — UptimeRobot endpoint

Render environment secrets must include `USERBOT_SESSION_STRING`, `API_ID`, `API_HASH`, `CONTROL_BOT_TOKEN`, and `OWNER_USER_ID`. Add `AROLINKS_API_KEY`, `OWNER_USERNAME`, and `TUTORIAL_LINK` for the full pipeline. The Blueprint provisions a persistent disk for SQLite; this requires a paid Render plan. Telegram login/OTP must be completed locally because Render has no safe interactive first-login flow.

After deployment, use:

```text
https://<your-render-service>.onrender.com/health
```

## Tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

## Known integration constraint

Telegram does not provide a standalone thumbnail upload in every media message. The catalog stage uses an existing remote thumbnail file ID without downloading bytes. If Telegram or the catalog bot rejects that cached media, the job pauses as failed for manual review; it never downloads the movie or silently uploads unrelated imagery.
