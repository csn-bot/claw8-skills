---
name: ppt2markdown
description: Convert a PPTX slide deck into slide-ready Markdown and post it to Day One (Work journal) via the dayone-crud workflow.
user-invocable: true
---

## Purpose

Take a `.pptx` slide deck, extract slide text (dropping common footer/copyright lines), detect code-like blocks, and convert the deck into **slide-ready Markdown**.

Then, post that Markdown directly into **Day One** using the existing `dayone-crud` skill workflow.

## Day One entry header (top of body)

The generated Markdown must start with:

1. **H1** — short title derived from the `.pptx` stem (underscores → spaces).
2. **Plain text** — the source filename only (e.g. `sorting_and_searching.pptx`).
3. **H7** — `####### <ENTRY_UUID>` (Day One entry id), on its own line.

Then a blank line, then slide sections: each slide starts with **`___`** on its own line, then **`## <slide title>`** on the next line (not `## Slide: …`—that older pattern required brittle post-hoc regex that could break `` ``` `` blocks if applied without **`--outside-fences-only`**). With **`--post`**, the script runs `dayone new` (body without line 3), parses the new UUID, then calls **`dayone_crud.py update`** once so line 3 is correct. Convert-only (**stdout**) prints lines 1–2 and omits line 3.

### Legacy `## Slide:` in the conversion pipeline

**`ppt2markdown.py`** runs **`finalize_slide_markdown`** on the assembled note: any line matching **`## Slide n:`** or **`## Slide:`** (outside `` ``` `` fences only) is rewritten to **`___`** then **`## <title>`** on the next line—the same rule as **`dayone_crud`** **`replace --outside-fences-only`**, built in so agents do not hand-roll regex on fenced decks.

For notes already in Day One (not re-imported from PPTX), use **`dayone_crud.py replace --outside-fences-only`** as in **`dayone-crud/SKILL.md`**.

## Tables → Day One (pipe text in a code fence)

This matches **`dayone-crud`** / user preference: **do not** emit GFM pipe tables at column 0 for Day One. When the extractor detects a small “name / use” table from the slide, it renders **pipe rows inside a single triple-backtick fenced block** (header + separator + rows), monospace preformatted. See **`dayone-crud/SKILL.md`** (“User preference — how tables must look in Day One Markdown”) for the full rationale (sync/rendering).

## Hard rules

- Do **not** write a permanent `.md` file into this repo.
- Markdown should be generated in-memory and sent directly to Day One; **`--post`** may use a **temporary** `.md` only for `dayone_crud.py update` (not a repo path).
- Always drop footer lines like `© A+ Computer Science - www.apluscompsci.com` (and similar variants).
- Code-looking content should be fenced as Markdown code blocks (triple backticks).
- **Tables** extracted from slides must use that same pattern: **pipe lines inside one fenced ` ``` ` block**, not a rendered Markdown table.

## Script location

`ppt2markdown/scripts/ppt2markdown.py`

## Run (post to Day One)

This is the default intended workflow: convert the PPTX to slide-ready Markdown **and post directly to Day One** (no saved `.md` file).

```bash
python3 "/Users/smh/Documents/GitHub/claw8/skills/ppt2markdown/scripts/ppt2markdown.py" \
  "/path/to/deck.pptx" \
  --post
```

## Run (convert only / stdout)

```bash
python3 "/Users/smh/Documents/GitHub/claw8/skills/ppt2markdown/scripts/ppt2markdown.py" \
  "/path/to/deck.pptx"
```

This prints slide-ready Markdown to stdout.

## Embed images in Markdown as data-URI `<img/>` (optional)

For notes that already contain `![alt](url)` or `<img src="…">`, **`embed_markdown_images_as_data_uris`** in **`ppt2markdown.py`** replaces them with `<img alt="…" src="data:image/…;base64,…" />` (stdlib: HTTP(S) and local paths). **`dayone-moment://`** and other non-file URLs are skipped unless you pass a custom **`fetcher`** (e.g. the agent loads attachment bytes via Day One MCP / CLI and maps URL → bytes).

```bash
python3 ".../ppt2markdown.py" --embed-images /path/to/note.md > /path/to/embedded.md
```

## Agent workflow (convert + post)

1. Prefer `--post` to send directly to Day One (Work journal, tag `cursor`) via the Day One CLI; the script sets the **H1 / filename / H7** header via **`dayone new`** + **`dayone_crud.py update`**.
2. If posting via CLI is unavailable or fails, fall back to the `dayone-crud` workflow using MCP `create_entry` (and `update_entry` if needed).
3. Do not save the Markdown as a repo file; if a staging file is absolutely necessary for a CLI fallback, use a temporary path under `/tmp`.
4. After the entry exists in Day One, run **`dayone-crud`** **`normalize-note --apply -v`** then **`format-java-fences --apply -v`** on that **`entry_id`** so escapes are stripped **before** fence consolidation, **`OUTPUT`** / trace lines are moved out of code fences into blockquotes (part of **`normalize-note`** unless **`--skip-output-extract`**), and Java is one block + formatted (see **`dayone-crud/SKILL.md`** — never **`consolidate-fences` alone** on still-escaped text). New exports use **`___`** + **`## title`** for each slide—no regex step needed for headings.

