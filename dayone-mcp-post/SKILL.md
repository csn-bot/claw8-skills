---
name: dayone-mcp-post
description: Post well-formed Markdown notes to the Day One Work journal via MCP (no email).
user-invocable: true
---

## Purpose

When the user says **"send to day one"**, **"move it to day one"**, **"report this to day one"**, or similar, immediately post the current content as a new Day One entry using the Day One MCP server.

## Hard rules

- Do **not** ask for confirmation (no "Should I send this?"). Posting is the requested action.
- Post to journal: **Work**
- The entry body must be **clean, well-formed Markdown**.
- If there are attachments, only attach **existing absolute paths**. Never fabricate paths.
- Prefer MCP posting over email when MCP is available.
- Always tag every entry with: **cursor**

## Entry format (default)

Create the entry text in this structure unless the user requests otherwise:

```markdown
# <Title>

## Meta
- Timestamp: <local datetime and timezone> (UTC: <utc datetime>)

## Summary
- <3–7 bullets>

## Details
<short paragraphs / lists / code blocks as needed>

---

Location (best-effort): <approx city/region/country OR unavailable>
```

## Timestamp + location (best-effort)

- **Timestamp**: always include a Timestamp line in `## Meta` even if the user didn’t specify a date.
- **Location** (best-effort, non-blocking): include a location line at the **bottom** of the Markdown (after a divider).
  - Prefer an IP-based approximation (city/region/country) if available.
  - If unavailable, write `Location (best-effort): unavailable`.
  - Do not block posting and do not ask for extra permission/confirmation.

## MCP call

Use `create_entry` with:

- `journal_name`: `Work`
- `text`: the Markdown body
- `attachments`: comma-separated absolute paths (optional)
- `tags`: always include `cursor` (optionally add others)
- `date`: optional ISO8601 if user specifies a date/time (otherwise omit; Timestamp still goes in body)

