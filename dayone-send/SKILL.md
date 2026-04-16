---
name: dayone-send
description: Package Markdown reports into a payload JSON and send to Day One via the fixed wrapper (no code edits).
user-invocable: true
---

## Purpose

This skill defines a **trigger phrase** and a **non-interactive** procedure for packaging content into clean Markdown and sending it to Day One immediately.

## Trigger phrases (act immediately, no confirmation)

If the user message contains an instruction like any of the following (case-insensitive), you must **package and send immediately**:

- "send to day one"
- "report this to day one"
- "wrap it up and forward to day one"
- "forward to day one"
- "move it to day one"
- "send that to day one"

Do **not** ask "Should I send this?" or request confirmation. Sending is the requested action.

## Hard rules (do not violate)

- **Never edit any `*.py` files.** Especially do not modify `dayone_send.py` or any wrapper scripts.
- **Never change paths inside scripts** and never generate alternate email formats (no ad-hoc `.eml` creation). The wrapper handles archiving.
- **Only update these payload fields**: `subject`, `body_markdown`, `attachments`.
- **Write exactly one payload JSON** into `outbox/` per send.
- **Send only by running the wrapper command** shown below.

## Inputs you must produce

Create a JSON file with this exact shape:

```json
{
  "subject": "Concise title (<= ~60 chars)",
  "body_markdown": "# Title\\n\\nWell-formed Markdown...\\n",
  "attachments": ["/absolute/path/to/file1", "/absolute/path/to/file2"]
}
```

Constraints:
- `subject` is required and must be non-empty.
- `body_markdown` is required and must be non-empty Markdown.
- `attachments` is optional; when present it must be a list of **absolute** file paths. If there are no attachments, use an empty list.

### Valid JSON (apostrophes / LLM traps)

- JSON strings use **double quotes** only. Apostrophes inside Markdown (e.g. **it's**, **don't**) are **plain characters** — **do not** write `\'` inside the JSON.
- Wrong (invalid JSON, breaks `json.loads`): `"body_markdown": "It\'s done"`
- Right: `"body_markdown": "It's done"`
- Newlines in `body_markdown` may be real newlines in the file, or `\n` escapes — both are valid if the whole file is valid JSON.
- After writing the file, sanity-check: the file must parse as JSON (no Python `repr()` wrappers, no single-quoted whole document).
- `dayone_send.py` will try to repair stray `\'` sequences, but you should still emit correct JSON to avoid ambiguity.

## Title + Markdown quality bar

- Choose a **decent, informative title** that helps future search.
- `body_markdown` must be clean Markdown:
  - Start with a single `#` title line (can match subject).
  - Use short paragraphs, bullets, and code fences where helpful.
  - Prefer clarity over verbosity.

## Packaging template (default)

Unless the user explicitly requests a different structure, format the body like:

```markdown
# <Title>

## Summary
- <3–7 bullets>

## Details
<short paragraphs / lists / code blocks as needed>

## Source
- Channel: <where this came from>
- Date: <local date>
```

Keep it tight and readable.

## Attachments (images/files)

- If there are images/files that materially improve the entry (screenshots, charts, exported reports), attach them.
- Only attach files that already exist and whose paths are **absolute**.
- If attachments are mentioned but not available as files, do not fabricate paths; mention this in the Markdown instead.

## Procedure (always the same)

1. **Write payload file** into `outbox/` with a unique timestamped name, e.g.:
   - `outbox/2026-04-02T120501Z-daily-report.json`
2. **Run the wrapper** (and only this wrapper) to send:

```bash
python3 dayone_send.py --payload outbox/<payload>.json
```

Notes:
- If you want to validate without sending, use:

```bash
python3 dayone_send.py --payload outbox/<payload>.json --dry-run
```

## Examples

### Example: web-scrape report

Subject:
- `OpenClaw web scrape report — Project X`

Body (snippet):

```markdown
# OpenClaw web scrape report — Project X

## Summary
- 3 pages scraped
- 2 key issues found

## Findings
1. ...
```

Attachments:
- Provide only if files already exist and paths are absolute.

## Failure handling

- If attachments are requested but you do not have valid absolute paths, **omit them** and mention in the Markdown that attachments were unavailable.
- If sending fails, do not modify scripts. Re-run with `--dry-run` to validate payload, then retry the send.

