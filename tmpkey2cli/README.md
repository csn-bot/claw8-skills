# tmpkey2cli — browser export → Day One (CLI, no email)

Tampermonkey script **`gem2md.js`** posts Markdown to a tiny localhost server; the server runs the official **`dayone`** CLI with that Markdown on **stdin** (same idea as `dayone --journal Work new < file.md`).

**No Gmail, OAuth, or Day One email-in** — only the Day One Mac app CLI.

## Prerequisites

- **Day One** for Mac installed; `dayone` on your `PATH` (or set `DAYONE_BIN` in `.env`).
- **Node.js** (for the bridge).

## 1. Bridge env

```bash
cp .env.example .env
# Edit DAYONE_BRIDGE_TOKEN (random secret) and DAYONE_JOURNAL if not "Work"
```

## 2. Tampermonkey token

Install **`gem2md.js`** from this folder. In the Tampermonkey menu, use **Day One bridge: set shared token** and paste the same value as `DAYONE_BRIDGE_TOKEN`.

Default POST URL is `http://127.0.0.1:8765/dayone` (change port via `PORT` in `.env` if needed).

## 3. Run the bridge

```bash
chmod +x start-bridge.sh
./start-bridge.sh
```

- Health: `GET http://127.0.0.1:8765/health`
- Import: `POST /dayone` with header `X-Bridge-Token` and JSON body:
  - `subject` (string, required — used for validation; body is the full markdown)
  - `body_markdown` (string, required)
  - `attachments` (optional array of **absolute** paths, max 10, passed to `dayone -a`)
  - `tags` (optional string array; merged with comma-separated `DAYONE_TAGS` in `.env`)

## 4. Usage

With the bridge running, **Export MD** in the browser still downloads the `.md` file and also POSTs the same content to the bridge (unless you turn that off in the Tampermonkey menu).

## Optional: start at login (macOS)

Use a `LaunchAgents` plist that runs `start-bridge.sh` after login.

## Files

| File | Role |
|------|------|
| `gem2md.js` | Exporter + `GM_xmlhttpRequest` POST on markdown export |
| `dayone-cli-bridge.js` | `127.0.0.1` HTTP → `dayone -j … -- new` with stdin |
| `start-bridge.sh` | Loads `.env`, starts the bridge |
