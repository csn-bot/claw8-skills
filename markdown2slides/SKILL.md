---
name: markdown2slides
description: >-
  Turn slide-ready Markdown into Moodle-forum-paste HTML (scoped CSS, 600px
  scroll viewport, Google-style slide cards). Use when building or updating
  classroom slide decks for Moodle or when asked to regenerate h7-slides-out
  / moodle HTML from AML-style markdown. For Day One–exported markdown, run
  dayone-crud pipeline first: normalize-note (escapes + consolidate), then format-java-fences when the deck has Java.
  When creating new deck markdown for Day One, include the source `.pptx`
  basename and the entry UUID at the top (see “Day One deck notes: source file + entry id”).
user-invocable: true
---

## Purpose

Convert a slide source into a **single HTML fragment** safe to paste into a Moodle forum post.

Supported sources:

- **Markdown**: slide-ready Markdown (front-matter keys + `---` slide breaks + `##` slide titles)
- **PPTX**: `.pptx` slide deck; slide text is extracted and rendered into the same HTML deck structure

- No `<!DOCTYPE>`, `<html>`, `<head>`, or `<body>` — avoids fighting the Adaptable theme.
- All layout/CSS scoped under `#aml-openclaw`; viewport wrapper `.aml-viewport` is **600px max-height** with scroll.
- Optional: title slide meta grid, lesson blocks, link-card grids, week table, glossary grid, speaker notes strip, Q&A slide styling.

## When to use

- User asks you to **generate slides** and provides the source (you will be told what the source is each time).
- Output is currently **always HTML** (Moodle-forum-paste-ready).
- User asks to **regenerate** output (e.g. overwrite `h7-slides-out.html`).
- User wants **typography/CSS tweaks** — change the embedded `<style>` in `scripts/markdown2slides.py`, then rerun the script.

## Script location

Repo path (this skills project):

`markdown2slides/scripts/markdown2slides.py`

### Day One → Markdown without attachment I/O

For **one entry** (or “text first, media later”), read the body from SQLite: Day One stores the entry Markdown in **`ZENTRY.ZMARKDOWNTEXT`**. That text already includes attachment placeholders (for example `dayone-moment://…`); nothing under `DayOnePhotos` has to exist for this step, so the pipeline does not fail on missing blobs.

- **Helper (stdlib only):** `markdown2slides/scripts/dayone_entry_markdown.py`

```bash
python3 ".../markdown2slides/scripts/dayone_entry_markdown.py" \
  -d "$HOME/Library/Group Containers/5U8NS4GX82.dayoneapp2/Data/Documents/DayOne.sqlite" \
  -j "Work" \
  -e "ENTRY_UUID" \
  -o "/path/to/slide-deck.md"
```

Then pass that `.md` file to `markdown2slides.py` as usual. Use `--list` with `--journal` to print recent UUIDs and a one-line preview.

### Day One deck notes: source file + entry id

When you **create new** slide-deck Markdown for Day One (for example after **`ppt2markdown`** and **`create_entry`** / `dayone … new`), the note **must** remain traceable to both the **source deck file** and the **Day One entry**. Put this block at the **very top**, then the first slide section after a `---` separator:

1. **`# Title`** — human-readable deck name (becomes the HTML title slide’s main heading).
2. **Source file** — the **basename** of the source `.pptx` on its own line (as it exists on disk), e.g. `sorting_and_searching.pptx`.
3. **Entry id** — the Day One entry UUID on its own line as a **level-6 heading** (`######`), e.g. `###### 871BFD9129DB47B2BB01AEDCAF994603`.
4. **`---`** or **`___`** on its own line — then slide content (`## …` sections) as usual (both split slides in **`markdown2slides`**).

Reference example (same shape as the *Sorting and Searching* / `871BFD9129DB47B2BB01AEDCAF994603` note):

```markdown
# Sorting and Searching
sorting_and_searching.pptx

###### 871BFD9129DB47B2BB01AEDCAF994603

---
```

Keep the **`.pptx` file** in the project or a known path alongside this workflow so regeneration and `markdown2slides` runs always point at the same source. After Day One returns the new entry id, **update the note** (or create with a body that includes the id) so the **`###### <uuid>`** line matches that entry.

Day One storage may add CommonMark-style backslashes (e.g. `sorting\_and\_searching\.pptx`, or odd spacing around `#` in headings); **`dayone-crud`** **`normalize-note`** still applies before HTML when needed.

**Pipeline (PPTX → Markdown → Day One → HTML):** PowerPoint is converted to Markdown (this script or **`ppt2markdown`**); the note is stored in Day One (CLI/MCP), often picking up **stacked backslashes** and **split ``` / ```java fences** on round-trip. Before generating HTML, run **`dayone-crud`** **`normalize-note --apply`** (whole-note escape cleanup **then** consolidate), then **`format-java-fences --apply`** for Java slides. Never run **`consolidate-fences` alone** on still-escaped text. If the markdown came from **`get_entries`**, decode **`body`** with **`json.loads`**—do not paste JSON-escaped strings into `update_entry`.

If the deck still looks wrong (tables as monospace, odd `\\` in pipe rows), fix the Day One body with that pipeline **before** passing the `.md` here—`markdown2slides` does not repair fragmented fences or stacked escapes except via **`preprocess_consolidate_fragment_fences`** (merge only; it does not undo Day One escapes in prose).

#### When to use [dayone2md](https://github.com/kwo/dayone2md) instead

Use **dayone2md** when you want a **bulk export of a whole journal**: many `.md` files plus a **`photos/`** tree of copied attachments and links rewritten to local paths. That is a different goal than SQL text extraction (for example an offline folder of entries **with** media on disk).

#### Before running `dayone2md` (prep and pitfalls)

Current **brew** builds require **`-j` (journal name)**, **`-i` (path to `DayOne.sqlite`)**, and **`-o` (output directory)**; omitting `-j` exits with an error.

The tool **copies every attachment** it associates with exported entries from `DayOnePhotos` using `ZMD5` + `ZTYPE`. **The first missing file aborts the entire run** (there is no “continue without this asset” mode). Practical prep:

- Open **Day One** on the Mac and let **iCloud sync** finish so blobs exist under  
  `~/Library/Group Containers/5U8NS4GX82.dayoneapp2/Data/Documents/DayOnePhotos/`, **or**
- Expect to fix **orphan rows** in the DB (metadata without a file on disk). Journal name in `-j` must match **`ZJOURNAL.ZNAME`** exactly (for example `Work`).

Rare schema/data quirks we have seen: attachments with **empty `ZMD5`** can make the tool look for a source path like **`DayOnePhotos/.jpeg`**; empty or odd `ZTYPE` values can produce odd filenames. Resolving sync/metadata issues in Day One is preferable to hacking the library folder.

## Run (absolute paths recommended)

```bash
python3 "/Users/smh/Documents/GitHub/claw8/skills/markdown2slides/scripts/markdown2slides.py" \
  "/path/to/slide-deck.md" \
  -o "/path/to/output.moodle.html"
```

PPTX example:

```bash
python3 "/Users/smh/Documents/GitHub/claw8/skills/markdown2slides/scripts/markdown2slides.py" \
  "/path/to/slide-deck.pptx" \
  -o "/path/to/output.moodle.html"
```

Default output if `-o` is omitted: `<source-basename>.moodle.html` next to the input file.

## Auto-regenerate `h7-slides-out.html` (this repo)

This project includes a **Cursor hook** so that when you edit anything under `markdown2slides/`, the Teach preview file is regenerated immediately:

- Hook script: `.cursor/hooks/regen-h7-slides-after-skill-edit.py`
- Config: `.cursor/hooks.json` (`afterFileEdit` and `afterTabFileEdit`)

The hook reads **source markdown** and **output HTML** paths from constants at the top of the hook script (defaults: `AML_test_slidedeck.md` → `h7-slides-out.html` in your OneDrive `88/Teach` folder). Change those constants if your filenames move.

If hooks do not run after adding files, open Cursor **Hooks** settings or restart Cursor once.

## Markdown conventions the generator expects

- **GFM pipe tables (storage vs HTML)**: **Day One / authoring** often keeps tables as **code-shaped** markdown (4-space–indented `| … |` rows and/or tiny ` ``` ` fences per row—see **`dayone-crud`**). **`generate_html` always** runs **`preprocess_consolidate_fragment_fences`** first (mandatory, not optional): every ``` / one line / ``` fragment run is merged into **one multi-line** fence when lines classify as the same **table** or **code** kind (assignments, `stuff[i] =`, trace lines, SVG, etc.—see **`_fence_fragment_line_kind`**). Then **`preprocess_merge_adjacent_table_fences`** handles any remaining pipe-only fragment patterns. Agents do not need to remember a separate “consolidate” step for HTML output. **Fenced code** whose body is a valid GFM pipe table (header + `| --- |` separator + body rows) is **not** left as `<pre><code>`: it is rendered as the same **`week-table`** HTML as unfenced tables (section-title row, `week-table-col-head` column labels, etc.). **Raw** `|` tables at column 0 in a `.md` file still hit the mixed renderer directly and become `week-table` HTML. Non-table fenced blocks stay `<pre><code>`.
- **Day One markdown escapes:** API/export text often uses CommonMark-style backslashes before punctuation (`\.`, `\(`, `\-\-\-` in tables, etc.). **`_unescape_dayone_commonmark_escapes`** (loop until stable) is applied when building HTML: **inline** text (`md_inline_to_html`), **Jua headings**, **`<pre><code>`** bodies, **link-card** names/notes, **glossary** terms, and **lesson** titles. Pipe-table row parsing uses the same helper. Readers should not see stray `\` from Day One storage in the Moodle output; cleaning the source with **`dayone-crud`** **`normalize-note`** is still useful for the raw note.
- **Ampersands**: Slide titles (`h1` / slide `h2`) use **Jua** — the script replaces **`&` with `+`** in those headings only, then HTML-escapes once (never emits literal `&amp;` text). Body copy (Roboto / Google Sans) keeps normal **`&`** via `md_inline_to_html`.
- **Title**: first `# Heading` → title slide (cleaned; parenthetical suffix like `(slide-ready notes)` dropped).
- **Front matter**: a block of `key: value` lines (underscores may be escaped as `\_` in Markdown) before the first `##` slide; used for subtitle + meta grid when keys match `session_focus`, `wednesday_class`, `friday_class`, `instructor_prep_due`, `related_events`.
- **Slides**: a horizontal rule on its own line separates sections — **`---`** (dash) or **`___`** (underscore), including longer underscore rules. Each section should start with `## Slide title` or `## title` (optional `Slide:` prefix stripped). Matches **`ppt2markdown`** slide breaks (`___` + `## …`).
- **Speaker notes**: `### Speaker notes` then bullets or lines; rendered as yellow footnote strip.
- **This week table**: slide whose title contains “this week”; bullets like `- **Wednesday (in class):** …` or `- **When:** …` → `<table class="week-table">`.
- **Pipe tables (GFM) in slide bodies** (`render_mixed_markdown_lines`): markdown tables become `week-table` HTML. **PPT-style section title** (one label cell + empty siblings on the first row, e.g. `| Section title | |`, then `| --- | --- |`, then column names): **`<thead>`** has only the **blue full-width** `<th colspan="N" class="week-table-section-title">` (centered). The **column name row** is the **first row of `<tbody>`**, each cell **`<td class="week-table-col-head">`**: **centered, bold, white background** (no blue). Ordinary tables (every header cell has text) keep one `<thead>` row with default left-aligned `th`.
- **Monospace in tables (optional):** (1) **Per cell** — use inline code in a cell, e.g. ``| `0xFF` |``, rendered as `<code class="md-inline-code">` (monospace chip). (2) **Whole table** — `<!-- m2s:tt -->` on the line **above** an unfenced pipe table or **above** the opening `` ``` ``, *or* as the **first non-empty line inside** a fenced pipe table (before the `|` rows). The table gets `class="week-table week-table--mono"`. The comment is not shown in the slide HTML. If you use both (outside and inside the fence), one `<!-- m2s:tt -->` is enough. **Day One** may store the directive **escaped** (e.g. `\<\\!-- m2s:tt \\-\\->`) and/or in its **own** tiny `` ``` `` block before one-row-per-fence tables; **`generate_html`** normalizes that (``preprocess_promote_m2s_tt_fence``) after fragment consolidation.
- **Progressive reveal (fenced pipe tables only):** after the `| --- |` row, any body line may be written as **`- | col | col |`** (dash, space, then a normal pipe row). Those rows render in the same `week-table` but start **invisible** (`opacity: 0`); the first **mouseenter** or **focus** adds **`is-revealed`** via a small footer script and the row **stays** visible. Rows **without** the `- ` prefix behave like normal visible rows. Header and separator lines must not use the dash prefix.
- **SNIPPET / OUTPUT (caps labels):** if **SNIPPET** then **OUTPUT** (plain paragraphs, all caps) appear on a slide, the **first** run of **Markdown blockquote** lines (each line starts with ``>``) immediately after **OUTPUT** becomes **`div.md-output-reveal-block`** with one **`div.md-output-reveal-line`** per line: **monospace**, **no** list markers or arrows, starts **invisible**, first hover/focus reveals that line permanently. Other ``>`` blocks on the slide (without that trigger) render as **`blockquote.md-slide-gt-block`**. Normal ``- `` lists are always standard bullets.
- **Lessons**: lines `**Lesson N — …**` start lesson cards; following bullets go in that card.
- **Glossary**: `- **Term:** definition` → 2-column card grid.
- **Link shortlist**: slide with “shortlist” / IDE recommendation pattern → primary + secondary link grids from URL bullets.
  - Format: `- **Name** — https://...` or `- **Name** (short subtitle) — https://...` (subtitle becomes a gray note under the name; the optional parenthetical must sit **between** the bold name and the em dash).
  - Long URLs show a **short visible label** (usually hostname); the full URL is still `href` and `title`.
- **Footer**: optional italic `*Source: …*` at end of file → `.deck-footer`.

## Agent workflow

1. If the user names an output path, pass it as `-o` and **overwrite** that file after CSS/script changes.
2. After editing the Python file, **run it** and confirm the output contains expected structure (e.g. `week-table` for the expectations slide).
3. For **Day One–sourced** `.md`, if fences are still one-line-per-row or tables render as `<pre>`, normalize the markdown with **`dayone-crud`** first, then rerun **`markdown2slides`**.
4. When **posting new** deck Markdown to Day One, follow **Day One deck notes: source file + entry id** (prepend `#` title, `.pptx` basename, `###### <uuid>`, then `---`), keep the source `.pptx` at a known path, and persist the entry UUID in the note after creation.
5. Do not require extra pip packages; script uses the Python standard library only.

## Pasting in Moodle

Paste the **entire** generated file contents into the forum editor in **HTML** mode. The outer `.aml-viewport` div provides the fixed-height scroll region inside the post.
