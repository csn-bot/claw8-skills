## Day One sender wrapper (for OpenClaw)

This repo contains a **fixed wrapper** that sends Markdown content to Day One via Gmail API.

### Contract (what OpenClaw should do)

1. Write a payload JSON file into `outbox/`:

```json
{
  "subject": "A good title",
  "body_markdown": "# Heading\n\nMarkdown content here.\n",
  "attachments": ["/absolute/path/to/file.png"]
}
```

2. Run the wrapper with the payload path:

```bash
python3 dayone_send.py --payload outbox/<payload>.json
```

### What the wrapper does

- Sends an email via Gmail API to the Day One email address.
- Archives a copy of exactly what was sent into `sent/`:
  - `*.json` (payload)
  - `*.eml` (the RFC822 email)
  - `*.meta.json` (message id, timestamps, paths)

### Setup

1. Copy `dayone_config.example.json` to `dayone_config.json` and set `sender` and `recipients` (your Day One email-in address).

2. Download a Google Cloud **OAuth desktop** client secret JSON and save it as `credentials.json` in this same directory (`workspace/send/`).

3. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

4. Run the sender once; the browser opens for Gmail OAuth and the refresh token is saved to `token.json` (gitignored).

