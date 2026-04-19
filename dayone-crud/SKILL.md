---
name: dayone-crud
description: >-
  Create, read, and update Day One journal entries (Work journal) via MCP and optional SQLite text extraction; post well-formed Markdown without email. User prefers tabular content as Markdown code blocks (4-space indented or consolidated ``` fences) in Day One. Bundled dayone_crud.py can normalize stacked backslashes (whole note + fences by default), merge fragmented one-line fences including ```lang (normalize-note), and reformat Java (format-java-fences; optional google-java-format).
user-invocable: true
---

## Purpose

When the user wants content in **Day One**—**new entries** (“send to day one”, “report this to day one”) or **reading/updating existing entries**—use the Day One MCP server (`user-dayone-cli`) and the patterns below.

Default journal: **Work**.

## User preference — how tables must look in Day One Markdown

**Assume this for every agent-authored note** unless the user explicitly asks for something else (e.g. native rendered tables).

- **Preferred presentation:** Tabular / pipe-style content should appear **inside a code block** in Day One—monospace, preformatted—**not** as a raw GFM pipe table at column 0.
- **How to author it (reliable with Day One sync):** use a **Markdown indented code block**: prefix **every** table line (including `| --- |` separators and all `| cells |`) with **four spaces**. Do not rely on a single multi-line ` ``` ` fence around the whole table; Day One may split or escape those rows.
- **After cleanup (recommended for edited decks):** once the note is stable, you can store **one multi-line** ` ``` ` block containing the **entire** pipe table (all `|` rows) or **entire** code sample—no backslash escapes are needed inside fenced code. Use **`normalize-note`** (see bundled helper) to repair escaped or fragmented fences before archiving.
- **Applies when:** `create_entry`, `update_entry`, or any workflow that **generates Markdown for this user** and stores it in Day One.
- **`ppt2markdown` (PPTX → Day One):** slide “name / use” tables detected by the extractor are written as **pipe rows inside one triple-backtick fenced block** (same presentation goal as above—not a GFM table at column 0). Follow the usual post pipeline: **`normalize-note`** then **`format-java-fences`** on the new entry.

## Bundled helper: `scripts/dayone_crud.py`

Ships with this skill (**Python stdlib** for core transforms; **optional** [`google-java-format`](https://github.com/google/google-java-format) on `PATH` or via **`GOOGLE_JAVA_FORMAT`** for Java fence layout). It wraps the patterns that are easy to get wrong when done ad hoc: **read/list** from `DayOne.sqlite`, **`duplicate`** (**`create_entry`** after **`normalize-note`** and (by default) **`format-java-fences`**, then **`update_entry`** to swap the embedded source UUID for the new entry id—fixes fragmented code fences on copy, Java indentation, and deck header lines like `###### # <uuid>`; use **`--no-format-java`** to skip Java layout), **`update_entry`** via **`dayone mcp`** (newline JSON-RPC, `stderr` not blocking), **regex replace + optional apply**, **`fix-fence-escapes`** (collapse stacked `\` before Markdown punctuation; default **inside ` ``` ` only**, optional **`--whole-note`** for headings/notes too), **`consolidate-fences`** (merge Day One’s one-line ``` / ```lang fragments), **`normalize-note`** (**whole-note** escape cleanup **then** consolidate **then** **`OUTPUT`** / trace extraction out of fences; use **`--skip-output-extract`** to disable; use **`--fences-only-escapes`** for legacy fence-only escape behavior), **`format-java-fences`**, **`fix-slide-headings`**, **verify**, and **`list_journals`** over MCP.

**Environment / defaults (macOS):**

- **`DAYONE_SQLITE`**: override path to `DayOne.sqlite` (default: `~/Library/Group Containers/5U8NS4GX82.dayoneapp2/Data/Documents/DayOne.sqlite`).
- **`DAYONE_BIN`**: path to `dayone` CLI (default: `PATH` or `/usr/local/bin/dayone`).
- **`DAYONE_WORK_JOURNAL_ID`**: default `journal_id` for **`update`** / **`replace --apply`** (default: `105395021376` for Work).
- **`GOOGLE_JAVA_FORMAT`**: optional path to the `google-java-format` binary (otherwise `PATH` is searched). Install e.g. `brew install google-java-format`.

**Examples:**

```bash
# Recent entries in Work (UUID + preview)
python3 ".../dayone-crud/scripts/dayone_crud.py" list -j "Work"

# Dump body to a file (stage edits here; avoids agent shell truncation on huge notes)
python3 ".../dayone-crud/scripts/dayone_crud.py" read -j "Work" -e "ENTRY_UUID" -o "/tmp/entry-body.md"

# Replace full body from file (or use --file - for stdin)
python3 ".../dayone-crud/scripts/dayone_crud.py" update --journal-id "105395021376" \
  -e "ENTRY_UUID" --file "/tmp/entry-body.md"

# Regex replace on current SQLite body; prints result. Add --apply to call update_entry.
# Prefer --outside-fences-only for patterns that must not touch lines inside ``` code blocks.
python3 ".../dayone-crud/scripts/dayone_crud.py" replace -j "Work" -e "ENTRY_UUID" \
  --journal-id "105395021376" --pattern '^foo' --repl 'bar' -m --outside-fences-only --apply

# PPT/slide export cleanup: "## Slide n: Title" -> "## Title"; empty title -> playground slide emoji (U+1F6DD).
# Add --compact to collapse 3+ blank lines. Close other Day One clients before --apply.
python3 ".../dayone-crud/scripts/dayone_crud.py" fix-slide-headings -j "Work" -e "ENTRY_UUID" \
  --journal-id "105395021376" --compact --apply

# Same transform on a file (stdout); combine with update --file if you staged export locally first.
python3 ".../dayone-crud/scripts/dayone_crud.py" fix-slide-headings --file "/tmp/export.md" --compact

# Collapse stacked backslashes (JSON / Day One / PPTX import). Default: lines inside ``` fences only.
# Add --whole-note to also fix headings, speaker notes, and bullets (same rules as normalize-note escape pass).
python3 ".../dayone-crud/scripts/dayone_crud.py" fix-fence-escapes -j "Work" -e "ENTRY_UUID" -v
python3 ".../dayone-crud/scripts/dayone_crud.py" fix-fence-escapes -j "Work" -e "ENTRY_UUID" \
  --journal-id "105395021376" --whole-note --apply

# Merge one-line ``` / ```lang fragments into one multi-line fence. Do NOT run this alone on text that
# still has Day One escapes — run normalize-note instead (escapes first, then merge).
python3 ".../dayone-crud/scripts/dayone_crud.py" consolidate-fences -j "Work" -e "ENTRY_UUID" \
  --journal-id "105395021376" --apply -v

# Recommended one-shot: whole-note escape cleanup, then consolidate (default; add --fences-only-escapes for ```-only).
python3 ".../dayone-crud/scripts/dayone_crud.py" normalize-note -j "Work" -e "ENTRY_UUID" \
  --journal-id "105395021376" --apply -v

# Duplicate entry in the same journal (prefer this over raw MCP create_entry on PPTX-style notes).
# Runs normalize-note, then format-java-fences (same as deck pipeline), then create_entry and
# update_entry so every occurrence of the source UUID becomes the new entry id (header + references).
python3 ".../dayone-crud/scripts/dayone_crud.py" duplicate -j "Work" -e "SOURCE_ENTRY_UUID" \
  --journal-id "105395021376" -v
# Preview markdown only: add --dry-run (no create).
# Skip normalize (not recommended): --raw. Skip Java formatting: --no-format-java.
# Classroom 4-space Java: add --aosp. Light Java only (no google-java-format): --no-external.

# After normalize-note: reformat Java inside ``` fences (dry-run first).
# Uses google-java-format if available; else light cleanup (tabs→spaces, dedent, trim trailing space).
# **Snippets:** whole methods format directly; bare statements (e.g. ``int[] ray = …;`` + loops, or
# ``ArrayList`` + ``for``) are wrapped in a synthetic ``static { … }`` for the formatter, then unwrapped.
# If a fence is missing closing ``}`` (common in PPTX extracts), a best-effort brace balance runs before GJF.
python3 ".../dayone-crud/scripts/dayone_crud.py" format-java-fences -j "Work" -e "ENTRY_UUID" -v
python3 ".../dayone-crud/scripts/dayone_crud.py" format-java-fences -j "Work" -e "ENTRY_UUID" \
  --journal-id "105395021376" --apply -v
# Force light-only (no external binary): add --no-external.
# **Indent width:** default is Google style (2 spaces). For classroom-style 4-space indents, add **--aosp**
# (passes through to google-java-format; install the binary first).

# Verify local body after a write (exit 1 if assertions fail)
python3 ".../dayone-crud/scripts/dayone_crud.py" verify -j "Work" -e "ENTRY_UUID" \
  --not-contains "## Slide"

# Resolve journal ids if Work id differs on another Mac
python3 ".../dayone-crud/scripts/dayone_crud.py" journals
```

**Complex transforms** (other than slide H2 cleanup): use **`read` → edit `/tmp/...md` → `update --file`**, **`replace`**, or a small Python one-off piped to **`update --file -`**.

### One-off text fixes on entries already in Day One (legacy patterns, fence-safe)

You can ask for a **targeted rewrite** on old markdown (e.g. leftover **`## Slide:`** / **`## Slide n:`** from an earlier export, or any similar prose-only pattern) **without** hand-wringing about `` ``` `` blocks—**if** you use the right tool:

1. **Default for regex on “document structure” lines** (slide headings, labels, etc.): **`replace`** with **`--outside-fences-only`** and **`-m`** (multiline) when the pattern uses `^` / `$` per line. Only text **outside** triple-backtick regions is scanned; **fenced code is never rewritten** by that pass, so you avoid the classic failure mode where a `## Slide:` string inside a comment or string literal matched and **split** fences.

2. **Workflow:** **`read`** (optionally to **`/tmp/...md`**) → **`replace --dry-run -v`** (stdout = new body; inspect) → **`replace --apply`** when satisfied. Close other Day One clients before **`--apply`** when possible (see reliability notes). Build **`--repl`** with backreferences via Python so `\1` is correct, e.g.  
   `REPL="$(python3 -c 'print("___\n" + r"## \1", end="")')`  
   for **`___` + `## <title>`**—**do not** rely on bash **`$'...\1'`** (octal escapes bite).

3. **If the note is already “sick”** (stacked backslashes, one-line ``` fragments, past bad imports): run **`normalize-note --apply -v`** first, then **`format-java-fences --apply -v`**, **then** your **`replace --outside-fences-only`**. That order **repairs** escape/fence damage, then applies your semantic heading/text change. For a healthy note that only needs a heading rename, **`replace --outside-fences-only`** alone is enough.

4. **Slide titles only, `## Slide n: Title` → `## Title`:** **`fix-slide-headings`** is purpose-built (optional **`--compact`**). It does **not** insert **`___`**; for **`___` + `## title`** to match **`ppt2markdown`**, use **`replace --outside-fences-only`** with patterns aligned to **`ppt2markdown`’s `finalize_slide_markdown`** (see **`ppt2markdown/SKILL.md`**).

5. **`duplicate`** is **not** an in-place fix: it **creates a new entry**, runs normalize + Java format + UUID rewrite on the copy. Use it when you want a backup fork; use **`replace` / `update --file`** when you want to **edit the existing entry**.

This playbook is the durable pattern for **Day One updates** and **duplicates**: fence-aware transforms where they exist (**`normalize-note`**, **`format-java-fences`**, **`replace --outside-fences-only`**), **`read`/`verify`** after writes, and **never** plain **`replace`** on full deck bodies when the pattern could appear inside code.

### Slide deck pipeline (PPTX → Markdown → Day One → clean note)

Rough data path: **PowerPoint (`.pptx`)** → extractor (**`ppt2markdown`** or **`markdown2slides`** from PPTX) produces **Markdown**. That text lands in Day One via **CLI `create` / `update`**, **MCP `create_entry` / `update_entry`**, or email/workflow payloads. The server and apps store it (and may re-serialize it); **`get_entries` JSON** and **SQLite `ZMARKDOWNTEXT`** are two views of the same body—always build the next `text` from **decoded** JSON or **`dayone_crud.py read`**, never from escaped JSON string literals.

**Mandatory order for “nice Java in one block” (and sane tables):**

1. **`normalize-note --apply -v`** — **First** collapse spurious `\` (default: **entire note**, not only inside fences), **then** merge fragmented ``` / ```java / ```lang one-liners. *Running **`consolidate-fences` alone** skips escape repair and leaves `\.` / `\(` inside merged fences and in prose.* **Then** (same subcommand) **`transform_extract_output_from_fences`**: slide-style **`OUTPUT`** / **`OUTPUT1`** runs and following trace lines (including bare `1`, `-1`, `true`, `false`, short text like `stack overflow`) are **removed from inside ``` fences** and rewritten as normal Markdown — a plain **`OUTPUT`** line followed by **`>`** blockquotes. Use **`--skip-output-extract`** on **`normalize-note`** or **`duplicate`** to leave those lines inside the fence.
2. **`format-java-fences --apply -v`** — Requires valid Java inside fences; install **`google-java-format`** (optional env **`GOOGLE_JAVA_FORMAT`**). If snippets were still escaped, run step (1) again first.
3. **`fix-slide-headings`** (optional) — Slide title cleanup / compaction.

Use **`--fences-only-escapes`** on **`normalize-note`** only if you must preserve intentional backslashes outside code fences (rare).

**Slide-deck cleanup order (short):** `normalize-note` → **`format-java-fences`** → `fix-slide-headings` as needed. Pipe tables inside fences are skipped for Java detection.

**What to ask the agent** (maps to `format-java-fences`): e.g. *“Run **dayone-crud `format-java-fences`** on this entry (dry-run with `-v`, then `--apply`).”* or *“**Clean up / reformat all Java code blocks** in the Day One note using **`dayone_crud.py format-java-fences`**.”* Subcommand name **`format-java-fences`** is the precise hook.

**Future (Python):** a sibling **`format-python-fences`** could mirror this (e.g. `black` / `ruff format` when ` ```python ` or heuristic matches; **`--no-external`** for light cleanup only).

## Read, Edit, Write

Use this loop for **reliable text-only work** (no dependency on `DayOnePhotos` or bulk exporters).

### Read

Get the **current entry body** as Markdown. Day One stores it in SQLite as **`ZENTRY.ZMARKDOWNTEXT`**.

- **Preferred:** `dayone-crud/scripts/dayone_crud.py` **`read`** / **`list`** (see **Bundled helper** above).
- **Alternate (read-only, same repo):** `markdown2slides/scripts/dayone_entry_markdown.py`:

  ```bash
  python3 ".../markdown2slides/scripts/dayone_entry_markdown.py" \
    -d "$HOME/Library/Group Containers/5U8NS4GX82.dayoneapp2/Data/Documents/DayOne.sqlite" \
    -j "Work" \
    -e "ENTRY_UUID" \
    -o "/tmp/entry-body.md"
  ```

- **MCP:** `get_entries` (e.g. search by UUID in `query`) and use the returned **`body`** field when present—parse JSON once and use the decoded string as `text`; never paste the **escaped JSON representation** of `body` into `update_entry`.

Prefer **`dayone_crud.py`** or the SQL helper when you want a deterministic local read that **cannot fail** on missing attachment files on disk.

### Edit

- Apply changes to the **full Markdown string** in your editor or a small script (regex, formatter, etc.).
- Treat updates as **whole-body replacement**: build the **complete** new `text` you want stored, not a partial patch (unless the user explicitly uses a different API).
- For **text-only** edits (headings, speaker notes, bullets), you do **not** need tools that copy `DayOnePhotos`.

### Write

- **Create:** `create_entry` with `text` (required), plus `journal_id` or `journal_name`, optional `tags`, `attachments`, `date`. See **MCP call** below.
- **Update:** `update_entry` with **`entry_id`** (required). Pass **`text`** to replace the entry body. Optional: `journal_id`, `all_day`, `starred`, `attachments`. **`tags`**, if provided, **replaces** all tags on the entry—omit `tags` if you must preserve existing tags.

Preflight: `arguments.text` must be a non-empty string for **`create_entry`**. For **`update_entry`**, supply `entry_id`; **`text` must be the complete new body** whenever you intend to change markdown—calls that omit `text` may appear to “succeed” but **will not replace** the entry body.

Example update (shape matters):

```json
{
  "server": "user-dayone-cli",
  "toolName": "update_entry",
  "arguments": {
    "journal_id": "105395021376",
    "entry_id": "ENTRY_UUID",
    "text": "# Title\n\nFull markdown body...\n"
  }
}
```

## Hard rules

- Do **not** ask for confirmation (no "Should I send this?"). Posting is the requested action.
- Post to journal: **Work**
- The entry body must be **clean, well-formed Markdown**.
- If there are attachments, only attach **existing absolute paths**. Never fabricate paths.
- Prefer MCP posting over email when MCP is available.
- Always tag every entry with: **cursor**
- At the very bottom of the entry body, add an `<hr/>` then:
  - a workspace/folder path reference for where the agent was working when posting (best-effort)
  - a best-effort listing of the open tabs at posting time as **tab filenames only** (no paths)

## Entry format (default)

The entry must **always** start with an H1 title on the very first line.

- The H1 title must be a **1–5 word** summary representing the document/artifact (content, purpose, or a short summary of the artifact’s title).
- The **second line** (immediately under the H1) must be the artifact’s **source-given title** exactly as provided by the content creator (often the first line of the source document/data, or the title shown wherever the content was taken from). This second line must be **plain text** (not a heading).
- The **third line** must be the Day One entry’s **share ID**, formatted as an **H7** heading: `####### <DAYONE_ENTRY_ID>`

After the H1, post the user’s content **as-is** (light cleanup only) with **no added sections** like `## Meta`, `## Summary`, or a location footer (unless the user explicitly asks for extra structure).

```markdown
# <1–5 word title summarizing the artifact>

<Exact source artifact title (plain text, not a heading)>

####### <DAYONE_ENTRY_ID>

<User-provided markdown content, minimally cleaned>

<hr/>
<WORKSPACE_OR_FOLDER_PATH>
<OPEN_TABS_FILENAMES>
```

### If the content is a slide deck

If the user is archiving slide content, prefer **slide-ready Markdown** structure: **`ppt2markdown`** emits **`___`** then **`## <title>`** per slide (not `## Slide: …`, to avoid post-hoc regex on fenced code); bullets and optional `### Speaker notes` as needed. Older notes may still use `## Slide:` or `## Slide n:`—use **`fix-slide-headings`** or **`replace --outside-fences-only`** to reshape titles. Do not add wrappers/sections like `## Meta` / `## Summary` / `## Details` unless the user explicitly asks for extra structure.

## Timestamp + location (best-effort)

- **Default**: do not add timestamp or location text to the entry body.
- **If the user explicitly requests metadata**: include it, but keep it short and non-blocking.

## MCP call

Use `create_entry` with:

- **Preferred**: `journal_id`: `105395021376`  *(Work journal; use this even if workspace rules are absent)*
- **Fallback** (if journal_id fails / is unavailable): `journal_name`: `Work`
- `text`: the Markdown body
- `attachments`: comma-separated absolute paths (optional)
- `tags`: always include `cursor` (optionally add others)
- `date`: optional ISO8601 if user specifies a date/time (otherwise omit; Timestamp still goes in body)

### Preflight (prevent MCP -32002)

The MCP tool requires the **`text`** parameter. To prevent this error:

`{"error":"MCP error -32002: Missing required 'text' parameter"}`

Always do the following **before** calling `create_entry`:

- Ensure you are passing an `arguments` object (not just the tool name).
- Ensure `arguments.text` exists and is a **non-empty string**.
- If content is empty for any reason, set a safe placeholder (e.g. `# Untitled\n\n(Empty body)\n`) rather than calling without `text`.

Example (shape matters):

```json
{
  "server": "user-dayone-cli",
  "toolName": "create_entry",
  "arguments": {
    "journal_id": "105395021376",
    "tags": "cursor",
    "text": "# Title\n\nBody...\n"
  }
}
```

## Artifact / file handling

- Do **not** write new files into the teaching workspace just to post to Day One (unless the user explicitly asked to save a file).
- If you must stage content for the CLI fallback, prefer a **temporary path** (e.g. under `/tmp`) and keep it out of the repo.

## Reliability notes (learned in practice)

### Backslashes, JSON, and fenced code (slide decks)

- **Symptom:** Characters like `( [ { + - .` gain **many** backslashes (`\\\\\\\\(`) in **fences, headings, and speaker notes**. **`markdown2slides` does not write to Day One**—this comes from **storage / edit / import** paths.
- **Causes:** (1) Copying `body` from **pretty-printed JSON** (or logs) into the next `text` payload so literal backslashes accumulate. (2) Repeated **`update_entry`** full-body rewrites where an LLM **doubles** escapes. (3) Day One rich-text ↔ markdown round-trips stacking escapes. (4) PPTX→Markdown tools then Day One round-trip.
- **Fix:** Run **`normalize-note --apply`** first (whole-note escape pass **then** consolidate). Do **not** run **`consolidate-fences` alone** on text that still has Day One/PPTX escapes—you will merge **dirty** lines into one block and **`format-java-fences`** / readability will suffer. Inside ` ``` ` blocks, **do not** paste JSON-escaped text—build `text` from **`json.loads` on the API response** or from **`dayone_crud.py read`** / **`ZMARKDOWNTEXT`**.
- **Local `read` vs MCP write:** After **`update_entry`**, **`DayOne.sqlite`** may update slightly later than the server; if a **`read`** looks stale, wait for sync or check the entry in the app.
- **`consolidate-fences` behavior:** Only **table** rows (`|…`) merge with **table** rows; only **code-like** lines merge with **code-like** lines; **same** ``` / ```lang **language key** must match across neighbors. **Prose** trapped in a one-line fence is **`other`** and is **never** merged with Java—avoids slides where an intro paragraph and `int foo…` get glued into one broken fence.

### Updates (`update_entry`) — shortcuts

- **`replace` is not fence-aware by default.** It runs `re.sub` on the **whole** note. A pattern like `^## Slide:` can match **inside** fenced Java or comments and **break** multi-line code blocks. Fence-aware transforms are **`normalize-note`**, **`consolidate-fences`**, **`format-java-fences`**, **`fix-fence-escapes`**, etc.—they **parse** `` ``` `` regions. For regex edits on slide prose, use **`replace --outside-fences-only`**, or edit staged markdown by hand, or use **`fix-slide-headings`** for `## Slide n:` → `## Title` style cleanup. Always **`--dry-run`** (or **`read`** to a file and diff) before **`--apply`** on large bodies.
- **Do not** persist edits with raw SQL on `DayOne.sqlite` (e.g. updating `ZENTRY.ZMARKDOWNTEXT`). Sync and the app can **overwrite** those rows. The supported path is **`update_entry`** with the **full** markdown in **`text`** (plus **`journal_id`** and **`entry_id`** as in the example above).
- **Multi-writer sync:** Day One **web**, **iOS**, and **other Mac** sessions can merge an **older** revision and **revert** a change that looked correct in SQLite. For an authoritative full-body edit, prefer **all other Day One clients closed** (including browser tabs), apply the update, then open **one** client and verify.
- **Large bodies (~15k+ characters):** avoid piping huge markdown through shell snippets whose output may **truncate**; stage the final body under **`/tmp/...md`** (or a small JSON args file) and load it in the script or MCP call.
- **Verify after write:** `dayone_crud.py verify` / **`read`**, or `get_entries`, and confirm the expected text (headings, markers). If it reverted **after** launch, suspect **sync from another client**, not a bad local write.
- **CLI / MCP limits:** `dayone help` exposes **`new`** (and **`mcp`**); there is **no documented `sync` command** and the bundled MCP tools have **no sync tool**—cloud sync is driven by **Day One clients** when they run. Prefer **`dayone_crud.py`** for **`update`/`replace --apply`** so JSON-RPC and **`stderr`** handling stay correct; it uses the same **`initialize` → `notifications/initialized` → `tools/call`** sequence documented inline in that script.
- **Pipe / GFM tables in the entry body:** This user **wants** tables to appear as **code blocks** in Day One (see **User preference — how tables must look** above). Day One may **rewrite** fenced **` ``` `** blocks that contain table-looking lines (splitting rows, escaping pipes). For **reliable** storage and the intended look, use **4-space–indented** pipe rows for **every** table. Do not default to raw `|` tables at column 0 unless the user overrides.

- If `create_entry` fails with something like **"Database operation failed"**:
  - Retry **once** using `journal_id` `105395021376` if you were using `journal_name`, or vice versa.
  - Retry **without** `attachments` (some failures correlate with attachments / large payloads). You can post the text first, then add attachments in a follow-up workflow if needed.
  - If the note is extremely long, consider posting a concise summary in the entry body and putting the full report in an attachment **only if** it succeeds and the attachment path exists.
  - If MCP still fails after the above retries, **fall back to the Day One CLI** (below).

- If you’re unsure the Work journal id is correct in a new environment:
  - Call `list_journals` and locate the **Work** journal id, then use that `journal_id` for posting.

## Gotchas: archiving GitHub Markdown (images + raw content)

- **GitHub “blob” pages are not the raw Markdown**: links like `https://github.com/<org>/<repo>/blob/<branch>/<path>?plain=1` can return an HTML wrapper (or appear empty when fetched programmatically). For reliable content, use the raw endpoint:
  - `https://raw.githubusercontent.com/<org>/<repo>/<branch>/<path>`
- **Relative image paths won’t render in Day One**: Day One generally won’t resolve relative paths like `assets/foo.png` (or HTML `<img src="../...">`) because they only make sense in the repo context. If you want images visible in Day One:
  - Prefer **downloading all referenced images** and attaching them to the entry via `attachments`.
  - Optionally also rewrite image links to absolute URLs (e.g. `https://raw.githubusercontent.com/.../image.png`), but **attachments are the reliable rendering path**.
- **Asset paths may be relative to the markdown file’s folder**: if the markdown lives under a subfolder (e.g. `tips/...md`) then `assets/...` is often actually `tips/assets/...` in the repo. Build absolute URLs accordingly.

## CLI fallback (when MCP fails)

If MCP posting fails (even after retries), create the entry using the Day One CLI. For **updates**, prefer **`dayone_crud.py update`** (drives `dayone mcp` directly) before giving up.

### Requirements
- The `dayone` CLI must be available and Day One.app must be installed.
- Use the `--` separator before `new` so `-j/-t` options are not mis-parsed.

### Create entry from stdin (recommended for long Markdown)

```bash
cat "/absolute/path/to/note.md" | dayone -j Work -t cursor -- new
```

### Create entry with attachments

```bash
cat "/absolute/path/to/note.md" | dayone -j Work -t cursor -a "/absolute/path/to/attachment.pdf" -- new
```
