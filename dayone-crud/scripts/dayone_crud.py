#!/usr/bin/env python3
"""
Day One: read/list local markdown, update via `dayone mcp` (JSON-RPC), regex replace + verify.

Self-contained (stdlib + optional ``google-java-format`` for ``format-java-fences``).
macOS default DB path; override with -d / $DAYONE_SQLITE.
See ../SKILL.md for pipeline order (normalize-note before format-java-fences; do not consolidate
alone on escaped text), OUTPUT/trace extraction from fences, and how consolidate-fences classifies
**table** / **code** / **other** lines.

Examples:
  python3 dayone_crud.py list -j Work
  python3 dayone_crud.py read -j Work -e ENTRY_UUID -o /tmp/body.md
  python3 dayone_crud.py update --journal-id 105395021376 -e ENTRY_UUID --file /tmp/body.md
  python3 dayone_crud.py replace -j Work -e UUID --journal-id 105395021376 \\
 --pattern '^foo' --repl 'bar' -m
  python3 dayone_crud.py fix-slide-headings -j Work -e UUID --journal-id 105395021376 --compact --apply
  python3 dayone_crud.py fix-fence-escapes -j Work -e ENTRY_UUID --apply --journal-id 105395021376
  python3 dayone_crud.py fix-fence-escapes --file /tmp/body.md
  python3 dayone_crud.py consolidate-fences -j Work -e ENTRY_UUID --apply
  python3 dayone_crud.py normalize-note -j Work -e ENTRY_UUID --apply
  python3 dayone_crud.py duplicate -j Work -e SOURCE_UUID --journal-id 105395021376 -v
  python3 dayone_crud.py format-java-fences -j Work -e ENTRY_UUID --apply -v
  python3 dayone_crud.py verify -j Work -e UUID --not-contains '## Slide'
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

# Default Work journal id (Day One); override with --journal-id or $DAYONE_WORK_JOURNAL_ID.
DEFAULT_WORK_JOURNAL_ID = "105395021376"

# Placeholder H2 when exported slide title is empty (e.g. "## Slide 4:" -> "## <emoji>").
DEFAULT_SLIDE_PLACEHOLDER_EMOJI = "\U0001f6dd"

DEFAULT_SQLITE = (
    Path.home()
    / "Library/Group Containers/5U8NS4GX82.dayoneapp2/Data/Documents/DayOne.sqlite"
)


def default_database() -> Path:
    env = os.environ.get("DAYONE_SQLITE")
    if env:
        return Path(env).expanduser()
    return DEFAULT_SQLITE


def default_dayone_bin() -> str:
    return os.environ.get("DAYONE_BIN") or shutil.which("dayone") or "/usr/local/bin/dayone"


def connect_ro(db: Path) -> sqlite3.Connection:
    uri = db.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def fetch_markdown(
    conn: sqlite3.Connection,
    entry_id: str,
    journal: str | None,
) -> str | None:
    entry_id = entry_id.strip()
    if journal:
        row = conn.execute(
            """
            SELECT e.ZMARKDOWNTEXT AS body
            FROM ZENTRY AS e
            JOIN ZJOURNAL AS j ON e.ZJOURNAL = j.Z_PK
            WHERE e.ZUUID = ? AND j.ZNAME = ?
            LIMIT 1
            """,
            (entry_id, journal.strip()),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT e.ZMARKDOWNTEXT AS body
            FROM ZENTRY AS e
            WHERE e.ZUUID = ?
            LIMIT 1
            """,
            (entry_id,),
        ).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])


def transform_slide_h2_headings(body: str, empty_title_emoji: str) -> tuple[str, int]:
    """
    Each line matching ``## Slide <n>: <title>`` becomes ``## <title>`` or, if title is
    blank/whitespace, ``## <empty_title_emoji>``. Uses MULTILINE ^ anchor only.
    """

    def repl(m: re.Match[str]) -> str:
        rest = (m.group(1) or "").strip()
        if not rest:
            return f"## {empty_title_emoji}"
        return f"## {rest}"

    # Only horizontal space after ":" — \s* would eat newlines and pull the next line into the title.
    return re.subn(
        r"^## Slide \d+:[ \t]*(.*)$",
        repl,
        body,
        flags=re.MULTILINE,
    )


def compact_blank_line_runs(body: str) -> str:
    """Collapse 3+ consecutive newlines to exactly two (one blank line)."""
    return re.sub(r"\n{3,}", "\n\n", body)


# CommonMark-style chars Day One / JSON round-trips often over-escape inside fenced code.
_FENCE_LAYERED_ESCAPES = re.compile(r"\\+([\\`*_{}[\]()#+\-.!|<>])")


def _collapse_redundant_fence_escapes(line: str) -> str:
    """Turn \\\\…\\( into ( inside a fence line; repeat until stable."""
    prev = None
    s = line
    while prev != s:
        prev = s
        s = _FENCE_LAYERED_ESCAPES.sub(r"\1", s)
    return s


def transform_fence_escapes(
    body: str, *, also_outside_fences: bool = False
) -> tuple[str, int]:
    """
    Collapse stacked backslashes before Markdown-escapable punctuation (see
    ``_FENCE_LAYERED_ESCAPES``). By default only **inside** `` ``` `` regions.
    Set ``also_outside_fences=True`` for **whole-note** cleanup (headings, speaker
    notes, bullets) after PPTX→Markdown or Day One / JSON round-trips — the same
    spurious ``\\.`` / ``\\(`` patterns appear outside fences too.

    Returns (new_body, number of lines rewritten).
    """
    if not body:
        return body, 0
    had_trailing_nl = body[-1] in "\n\r"
    lines = body.splitlines()
    out: list[str] = []
    in_fence = False
    changed = 0
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence or also_outside_fences:
            new_line = _collapse_redundant_fence_escapes(line)
            if new_line != line:
                changed += 1
            out.append(new_line)
        else:
            out.append(line)
    result = "\n".join(out)
    if had_trailing_nl:
        result += "\n"
    return result, changed


def _fence_line_kind(line: str) -> str:
    """
    Classify a one-line fenced-code body for merge rules.

    - table: GFM pipe row
    - code: likely source / formula (merge adjacent fragments of this kind)
    - other: prose, bullets, headings-in-fence — do not merge; one triplet stays as-is

    Keep in sync with markdown2slides._fence_fragment_line_kind (assignments, trace lines, XML).
    """
    prev = None
    s = line
    while prev != s:
        prev = s
        s = re.sub(r"\\([\\`*_{}[\]()#+\-.!|<>])", r"\1", s)
    s = s.strip()
    if not s:
        return "other"
    if re.match(r"^-\s*\|", s):
        return "table"
    if s.startswith("|"):
        return "table"
    if s.startswith(("- ", "* ", "+ ")) or s.startswith("#"):
        return "other"
    if re.match(r"^(else|return\b|\}|\{)$", s):
        return "code"
    if re.match(
        r"^(int|void|public|private|static|class|import|for|while|if)\b",
        s,
        re.I,
    ):
        return "code"
    if re.match(
        r"^\s*[A-Za-z_$][\w$]*(?:\.[A-Za-z_][\w$]*)?\s*=",
        s,
    ) or re.match(r"^\s*[\w\[\].]+\s*=", s):
        return "code"
    if re.match(r"^\s*return\b", s, re.I):
        return "code"
    if "(" in s or "{" in s or "}" in s or ";" in s:
        return "code"
    if re.match(r"^[A-Za-z_][\w]*\s*\(", s):
        return "code"
    if "(" not in s and re.match(
        r"^\s*[A-Za-z_][\w<>[\].,\s]*\)\s*$",
        s,
    ):
        return "code"
    if re.match(r"^\s*\d", s) and re.search(r"[=+\-*/]", s):
        return "code"
    if "<" in s and ">" in s:
        return "code"
    return "other"


def _minimal_lang_triplet_at(
    lines: list[str], idx: int, n: int
) -> tuple[int, str, str, str, str] | None:
    """
    If lines[idx:idx+3] is open / one content line / close (`` ``` `` or `` ```lang ``),
    return (index_after_triplet, raw_open_line, content_line, raw_close_line, lang_key).

    lang_key is the lowercased info after the opening backticks ("" for a bare fence).
    """
    if idx + 2 >= n:
        return None
    raw_open, mid, raw_close = lines[idx], lines[idx + 1], lines[idx + 2]
    so = raw_open.strip()
    if not so.startswith("```"):
        return None
    if raw_close.strip() != "```":
        return None
    if mid.strip().startswith("```"):
        return None
    info = so[3:].strip()
    lang_key = info.lower()
    return (idx + 3, raw_open, mid, raw_close, lang_key)


def transform_consolidate_fragment_fences(body: str) -> tuple[str, int]:
    """
    Merge Day One's repeated ``` / one line / ``` chunks into a single multi-line fence.

    Consecutive fragments merge only when they share a kind: **table** (``|`` rows) or
    **code** (Java-like / punctuation-heavy lines). **other** (prose in a fence) is never
    merged with neighbors. Works for bare `` ``` `` and language-tagged openers
    (e.g. `` ```java ``): neighbors merge only when **lang_key** matches (including both bare).

    Returns (new_body, number of merge groups where 2+ fragments were combined).
    """
    if not body:
        return body, 0
    had_trailing_nl = body[-1] in "\n\r"
    lines = body.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    groups_merged = 0

    def skip_blanks(idx: int) -> int:
        while idx < n and not lines[idx].strip():
            idx += 1
        return idx

    while i < n:
        triplet = _minimal_lang_triplet_at(lines, i, n)
        if triplet is None:
            out.append(lines[i])
            i += 1
            continue
        i_after, raw_open0, first, raw_close0, lang_key0 = triplet
        kind0 = _fence_line_kind(first)
        contents: list[str] = [first]
        i = i_after
        frags = 1
        if kind0 in ("table", "code"):
            while True:
                j = skip_blanks(i)
                t2 = _minimal_lang_triplet_at(lines, j, n)
                if t2 is None:
                    i = j
                    break
                _, _, nxt_mid, _, nxt_lang = t2
                if nxt_lang != lang_key0:
                    i = j
                    break
                if _fence_line_kind(nxt_mid) != kind0:
                    i = j
                    break
                contents.append(nxt_mid)
                frags += 1
                i = t2[0]
        else:
            i = skip_blanks(i)
        if frags > 1:
            groups_merged += 1
        out.append(raw_open0)
        out.extend(contents)
        out.append(raw_close0)
        continue

    result = "\n".join(out)
    if had_trailing_nl:
        result += "\n"
    return result, groups_merged


def apply_normalize_transforms(
    body: str,
    *,
    fences_only_escapes: bool = False,
    skip_escape: bool = False,
    skip_consolidate: bool = False,
) -> tuple[str, int, int]:
    """
    Same pipeline as ``normalize-note`` without read/MCP. Returns
    ``(body, n_escape_lines_changed, n_fence_groups_merged)``.
    """
    n_esc = n_con = 0
    if not skip_escape:
        body, n_esc = transform_fence_escapes(
            body, also_outside_fences=not fences_only_escapes
        )
    if not skip_consolidate:
        body, n_con = transform_consolidate_fragment_fences(body)
    return body, n_esc, n_con


# --- OUTPUT + blockquote lines: pull out of ``` fences (slide trace / I/O samples) ---------

_OUTPUT_HEAD = re.compile(r"^OUTPUT(\d*)\s*$", re.I)


def _line_looks_like_output_tail(st: str) -> bool:
    """Lines that belong after an OUTPUT label inside a fenced sample (not Java)."""
    if st.startswith(">"):
        return True
    if re.match(r"^-?\d+$", st):
        return True
    if re.match(r"^-?\d+\.\d+$", st):
        return True
    if re.match(r"^(true|false)$", st, re.I):
        return True
    if len(st) <= 72 and ";" not in st and "(" not in st and "{" not in st:
        if re.match(r"^[.\s·…‧]+$", st):
            return True
        if re.match(r"^[A-Za-z][A-Za-z0-9.,!?'\s-]{0,70}$", st):
            return True
    return False


def _output_line_to_blockquote(st: str) -> str:
    if st.startswith(">"):
        rest = st[1:].lstrip()
        return f"> {rest}" if rest else ">"
    return f"> {st}"


def _try_take_output_block(acc: list[str], start: int) -> tuple[int, list[str]] | None:
    """
    If ``acc[start]`` begins an OUTPUT run (``OUTPUT`` or ``OUTPUT1``…), return
    ``(end_index_exclusive, ['OUTPUT', '> …', …])`` for markdown **outside** the fence.
    """
    if start >= len(acc):
        return None
    m = _OUTPUT_HEAD.match(acc[start].strip())
    if not m:
        return None
    out_lines = ["OUTPUT"]
    idx = start + 1
    if m.group(1):
        out_lines.append(f"> {m.group(1)}")
    while idx < len(acc):
        st = acc[idx].strip()
        if not st:
            break
        if not _line_looks_like_output_tail(st):
            break
        out_lines.append(_output_line_to_blockquote(st))
        idx += 1
    if len(out_lines) < 2:
        return None
    return idx, out_lines


def _rewrite_fence_body_extract_output(acc: list[str]) -> tuple[list[str], int]:
    """
    Split one fence's inner lines into alternating code / OUTPUT+blockquote segments.
    Returns (flat lines to emit, number of OUTPUT blocks extracted).
    """
    i = 0
    n = len(acc)
    flat: list[str] = []
    extractions = 0
    cur_code: list[str] = []
    while i < n:
        took = _try_take_output_block(acc, i)
        if took is None:
            cur_code.append(acc[i])
            i += 1
            continue
        end_i, md_lines = took
        extractions += 1
        if cur_code:
            flat.append("```")
            flat.extend(cur_code)
            flat.append("```")
            flat.append("")
            cur_code = []
        flat.extend(md_lines)
        flat.append("")
        i = end_i
    if cur_code:
        flat.append("```")
        flat.extend(cur_code)
        flat.append("```")
    elif extractions and not flat:
        pass
    return flat, extractions


def transform_extract_output_from_fences(body: str) -> tuple[str, int]:
    """
    Move ``OUTPUT`` / trace lines (including ``>`` or bare ``1``, ``true``, …) out of
    triple-backtick blocks into normal Markdown: a plain ``OUTPUT`` line plus
    blockquotes, matching how slide I/O should read in Day One.
    """
    if not body:
        return body, 0
    had_trailing_nl = body[-1] in "\n\r"
    lines = body.splitlines(keepends=False)
    out: list[str] = []
    i = 0
    n = len(lines)
    total_x = 0
    while i < n:
        raw_open = lines[i]
        stripped_open = raw_open.strip()
        if not stripped_open.startswith("```"):
            out.append(raw_open)
            i += 1
            continue
        open_line = raw_open
        i += 1
        acc: list[str] = []
        while i < n and not lines[i].strip().startswith("```"):
            acc.append(lines[i])
            i += 1
        close_line = lines[i] if i < n else "```"
        if i < n:
            i += 1
        block = "\n".join(acc)
        if fence_body_looks_like_pipe_table(block):
            out.append(open_line)
            out.extend(acc)
            out.append(close_line)
            continue
        new_flat, nx = _rewrite_fence_body_extract_output(acc)
        total_x += nx
        if nx == 0:
            out.append(open_line)
            out.extend(acc)
            out.append(close_line)
        else:
            out.extend(new_flat)
    result = "\n".join(out)
    if had_trailing_nl:
        result += "\n"
    return result, total_x


def rewrite_entry_uuid_in_body(body: str, old_entry_id: str, new_entry_id: str) -> str:
    """
    Replace every case-insensitive occurrence of ``old_entry_id`` with ``new_entry_id``
    (e.g. header line ``###### # <uuid>`` and any prose references).
    """
    old_e = old_entry_id.strip()
    new_e = new_entry_id.strip()
    if not old_e or not new_e or old_e.lower() == new_e.lower():
        return body
    return re.sub(re.escape(old_e), new_e, body, flags=re.IGNORECASE)


# --- Java fence cleanup (PPTX→MD / Day One); optional google-java-format -----------------

_FMT_CLASS_WRAP = "__SlideFenceFmt__"


def fence_body_looks_like_pipe_table(body: str) -> bool:
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return bool(lines) and lines[0].startswith("|")


def is_probably_java_fence(code: str) -> bool:
    """Heuristic: Java vs e.g. Python, trace output, or plain text inside ```."""
    t = code.strip()
    if not t or fence_body_looks_like_pipe_table(code):
        return False
    if re.search(r"^\s*def\s+\w+\s*\(", t, re.M):
        return False
    if re.search(r"\b(import\s+java\.|package\s+[\w.]+;)", t):
        return True
    if re.search(r"^\s*(public\s+)?(class|interface|enum|record)\s+\w+", t, re.M):
        return True
    if ";" in t and "{" in t and re.search(
        r"\b(int|void|boolean|return|if|for|while|else|class|public)\b", t
    ):
        return True
    score = 0
    for pat in (
        r"\bpublic\s+static\b",
        r"\bvoid\b",
        r"\bnew\s+[A-Z]",
        r"\bfor\s*\(\s*int\b",
        r"\bif\s*\(",
        r"\bint\b",
        r"\bSystem\.out\.print",
        r"\.length\b",
        r"\+\+|--",
        r"Comparable\b",
        r"ArrayList\b",
        r"\.compareTo\s*\(",
    ):
        if re.search(pat, t):
            score += 1
    return score >= 3


def _google_java_format_exe() -> str | None:
    return os.environ.get("GOOGLE_JAVA_FORMAT") or shutil.which("google-java-format")


def _java_format_with_tool(src: str, *, aosp: bool) -> str | None:
    exe = _google_java_format_exe()
    if not exe:
        return None
    tmp = Path(tempfile.mkdtemp(prefix="d1-java-fmt-"))
    path = tmp / "Fmt.java"
    try:
        path.write_text(src, encoding="utf-8")
        cmd = [exe, str(path)]
        if aosp:
            cmd.append("--aosp")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return None
        # google-java-format sends the formatted source to stdout unless -i/--replace is used.
        out = r.stdout
        return out if out.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _close_unbalanced_braces(snippet: str) -> str:
    """
    If `{` outnumber `}`, append closing `}` so slide snippets missing a final brace
    can still be parsed by google-java-format. Naive (ignores strings); fine for decks.
    """
    s = snippet.rstrip()
    depth = 0
    for ch in s:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    if depth <= 0:
        return s
    return s + "\n" + ("}" * depth)


def _wrap_java_snippet_for_tool(code: str) -> tuple[str, bool]:
    t = code.strip()
    if re.match(r"^\s*(public\s+)?(class|interface|enum|record)\s+\w+", t):
        return code, False
    return f"class {_FMT_CLASS_WRAP} {{\n{t}\n}}\n", True


def _unwrap_fmt_class(formatted: str) -> str:
    lines = formatted.splitlines()
    if len(lines) < 3:
        return formatted
    if _FMT_CLASS_WRAP not in lines[0]:
        return formatted
    if lines[-1].strip() != "}":
        return formatted
    inner = "\n".join(lines[1:-1])
    return textwrap.dedent(inner).rstrip("\n")


def _unwrap_static_initializer(formatted: str) -> str:
    """
    Extract the body inside ``static { ... }`` from a formatted synthetic wrapper class.
    Used for slide snippets that are statements (not methods) at top level.
    """
    if _FMT_CLASS_WRAP not in formatted:
        return formatted
    m = re.search(r"\bstatic\s*\{", formatted)
    if not m:
        return formatted
    start_brace = formatted.find("{", m.start())
    if start_brace < 0:
        return formatted
    depth = 0
    i = start_brace
    while i < len(formatted):
        c = formatted[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                inner = formatted[start_brace + 1 : i]
                return textwrap.dedent(inner).strip("\n")
        i += 1
    return formatted


def format_java_fence_body(code: str, *, use_external: bool, aosp: bool) -> tuple[str, str]:
    """
    Return (new_code, method): method is 'google-java-format', 'google-java-format+wrap',
    'google-java-format+wrap-static', 'light', or 'unchanged'.

    Bare methods format directly. Class members that are not valid without a method
    (e.g. ``int[] ray = …; Arrays.sort(ray);``) are wrapped in a synthetic class, then
    if that fails, in ``static { … }`` so google-java-format can parse them.
    """
    original = code
    work = (
        _close_unbalanced_braces(code)
        if use_external and _google_java_format_exe()
        else code
    )
    if use_external and _google_java_format_exe():
        out = _java_format_with_tool(work, aosp=aosp)
        if out is not None and out.strip():
            return out.rstrip("\n"), "google-java-format"
        wrapped, did = _wrap_java_snippet_for_tool(work)
        if did:
            out2 = _java_format_with_tool(wrapped, aosp=aosp)
            if out2 is not None and out2.strip():
                return _unwrap_fmt_class(out2), "google-java-format+wrap"
            t = work.strip()
            if t:
                wrapped_static = (
                    f"class {_FMT_CLASS_WRAP} {{\n"
                    f"  static {{\n{t}\n"
                    f"  }}\n"
                    f"}}\n"
                )
                out3 = _java_format_with_tool(wrapped_static, aosp=aosp)
                if out3 is not None and out3.strip():
                    return (
                        _unwrap_static_initializer(out3),
                        "google-java-format+wrap-static",
                    )
    # Stdlib fallback: tabs → spaces, trim ends, dedent common leading space (PPTX junk indent)
    lines = [ln.replace("\t", "    ").rstrip() for ln in code.splitlines()]
    text = "\n".join(lines)
    ded = textwrap.dedent(text).strip("\n")
    if ded != original.strip("\n"):
        return ded, "light"
    return original, "unchanged"


def transform_format_java_fences(
    body: str,
    *,
    use_external: bool = True,
    aosp: bool = False,
) -> tuple[str, int, list[str]]:
    """
    For each ``` fence that looks like Java (lang tag or heuristic), reformat the body.
    Skips pipe-table blocks. Returns (new_body, fences_formatted, log lines).
    """
    if not body:
        return body, 0, []
    had_trailing_nl = body[-1] in "\n\r"
    lines = body.splitlines(keepends=False)
    out: list[str] = []
    log: list[str] = []
    i = 0
    n = len(lines)
    done = 0

    while i < n:
        raw_open = lines[i]
        stripped_open = raw_open.strip()
        if not stripped_open.startswith("```"):
            out.append(raw_open)
            i += 1
            continue
        info = stripped_open[3:].strip()
        lang = info.lower()
        open_line = raw_open
        i += 1
        acc: list[str] = []
        while i < n and not lines[i].strip().startswith("```"):
            acc.append(lines[i])
            i += 1
        close_line = lines[i] if i < n else "```"
        if i < n:
            i += 1
        block = "\n".join(acc)
        if fence_body_looks_like_pipe_table(block):
            out.append(open_line)
            out.extend(acc)
            out.append(close_line)
            continue
        is_java = lang == "java" or (
            lang in ("", "text") and is_probably_java_fence(block)
        )
        if not is_java:
            out.append(open_line)
            out.extend(acc)
            out.append(close_line)
            continue
        new_block, how = format_java_fence_body(block, use_external=use_external, aosp=aosp)
        tag_java = lang != "java" and lang in ("", "text")
        if how != "unchanged":
            done += 1
            log.append(f"java fence ({how}): {len(block)} -> {len(new_block)} chars")
        elif tag_java:
            done += 1
            log.append("java fence (tag -> ```java)")
        if tag_java:
            indent = len(raw_open) - len(raw_open.lstrip(" "))
            open_line = " " * indent + "```java"
        out.append(open_line)
        if new_block:
            out.extend(new_block.splitlines())
        out.append(close_line)

    result = "\n".join(out)
    if had_trailing_nl:
        result += "\n"
    return result, done, log


def cmd_format_java_fences(args: argparse.Namespace) -> int:
    body, ec = _load_body_for_transform(args)
    if ec != 0:
        return ec
    assert body is not None
    new_body, nfmt, log_lines = transform_format_java_fences(
        body,
        use_external=not args.no_external,
        aosp=args.aosp,
    )
    if args.verbose:
        print(f"java fences reformatted: {nfmt}", file=sys.stderr)
        for ln in log_lines:
            print(ln, file=sys.stderr)
        if not args.no_external and not _google_java_format_exe():
            print(
                "hint: install google-java-format (e.g. brew install google-java-format) "
                "or set GOOGLE_JAVA_FORMAT to the binary for IDE-quality layout; "
                "otherwise light dedent/trim is used.",
                file=sys.stderr,
            )

    if args.dry_run or not args.apply:
        sys.stdout.write(new_body)
        return 0

    if not args.entry_id:
        print("--apply requires --entry-id.", file=sys.stderr)
        return 2

    journal_id = args.journal_id or os.environ.get(
        "DAYONE_WORK_JOURNAL_ID", DEFAULT_WORK_JOURNAL_ID
    )
    try:
        mcp_tools_call(
            args.dayone,
            "update_entry",
            {
                "journal_id": journal_id,
                "entry_id": args.entry_id.strip(),
                "text": new_body,
            },
        )
    except (OSError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def list_entries(conn: sqlite3.Connection, journal: str, limit: int) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT e.ZUUID AS uuid,
               COALESCE(SUBSTR(e.ZMARKDOWNTEXT, 1, 120), '') AS preview
        FROM ZENTRY AS e
        JOIN ZJOURNAL AS j ON e.ZJOURNAL = j.Z_PK
        WHERE j.ZNAME = ?
        ORDER BY e.ZMODIFIEDDATE DESC
        LIMIT ?
        """,
        (journal.strip(), limit),
    ).fetchall()
    return [(str(u), str(p)) for u, p in rows]


def mcp_tools_call(dayone_bin: str, tool_name: str, arguments: dict) -> dict:
    """Run one MCP tools/call over newline-delimited JSON-RPC. Raises on transport or JSON-RPC error."""
    proc = subprocess.Popen(
        [dayone_bin, "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    if proc.stdin is None or proc.stdout is None:
        raise RuntimeError("failed to start dayone mcp")

    def send(obj: dict) -> None:
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "dayone_crud.py", "version": "1.0"},
                },
            }
        )
        proc.stdout.readline()
        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        )
        line = proc.stdout.readline()
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()

    if not line:
        raise RuntimeError("empty response from dayone mcp")
    resp = json.loads(line)
    if resp.get("error"):
        raise RuntimeError(json.dumps(resp["error"], indent=2))
    return resp


def tools_result_text(resp: dict) -> str:
    res = resp.get("result") or {}
    blocks = res.get("content") or []
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(str(b.get("text", "")))
    return "\n".join(parts).strip()


def mcp_tool_result_json(resp: dict) -> dict:
    """Parse JSON object from tools/call text content (e.g. create_entry metadata)."""
    raw = tools_result_text(resp)
    if not raw:
        raise RuntimeError("empty MCP tool result text")
    return json.loads(raw)


def cmd_list(args: argparse.Namespace) -> int:
    db: Path = args.database
    if not db.is_file():
        print(f"Not a file: {db}", file=sys.stderr)
        return 2
    conn = connect_ro(db)
    try:
        for uuid, preview in list_entries(conn, args.journal, max(1, args.limit)):
            line = preview.replace("\n", " ").strip()
            print(f"{uuid}\t{line}")
    finally:
        conn.close()
    return 0


def cmd_duplicate(args: argparse.Namespace) -> int:
    """
    Read source body from SQLite, run normalize-note transforms, format-java-fences by default,
    create_entry, then update_entry so the embedded source UUID becomes the new entry id.
    """
    db: Path = args.database
    if not db.is_file():
        print(f"Not a file: {db}", file=sys.stderr)
        return 2
    conn = connect_ro(db)
    try:
        body = fetch_markdown(conn, args.entry_id, args.journal)
    finally:
        conn.close()
    if body is None:
        print("No entry found (check --entry-id and --journal).", file=sys.stderr)
        return 1
    if not body.strip():
        print("Refusing to duplicate empty body.", file=sys.stderr)
        return 2

    skip_norm = args.raw
    body, n_esc, n_con = apply_normalize_transforms(
        body,
        fences_only_escapes=args.fences_only_escapes,
        skip_escape=skip_norm,
        skip_consolidate=skip_norm,
    )
    if args.verbose:
        if skip_norm:
            print("normalize-note: skipped (--raw)", file=sys.stderr)
        else:
            esc_scope = "fences only" if args.fences_only_escapes else "whole note + fences"
            print(
                f"normalize: escape lines fixed ({esc_scope}): {n_esc}; "
                f"multi-line fence groups: {n_con}",
                file=sys.stderr,
            )

    n_out = 0
    if not skip_norm and not args.skip_output_extract:
        body, n_out = transform_extract_output_from_fences(body)
        if args.verbose:
            print(f"OUTPUT blocks pulled out of ``` fences: {n_out}", file=sys.stderr)

    n_java = 0
    if not args.no_format_java:
        body, n_java, java_log = transform_format_java_fences(
            body,
            use_external=not args.no_external,
            aosp=args.aosp,
        )
        if args.verbose:
            print(f"format-java-fences: {n_java} fence(s) touched", file=sys.stderr)
            for ln in java_log:
                print(ln, file=sys.stderr)
        elif n_java and not _google_java_format_exe() and not args.no_external:
            print(
                "hint: install google-java-format for IDE-style Java layout "
                "(or pass --no-external for light dedent only).",
                file=sys.stderr,
            )
    elif args.verbose:
        print("format-java-fences: skipped (--no-format-java)", file=sys.stderr)

    if args.dry_run:
        sys.stdout.write(body)
        return 0

    journal_id = args.journal_id or os.environ.get(
        "DAYONE_WORK_JOURNAL_ID", DEFAULT_WORK_JOURNAL_ID
    )
    create_args: dict[str, str] = {"journal_id": journal_id, "text": body}
    if args.tags:
        create_args["tags"] = args.tags.strip()
    try:
        resp = mcp_tools_call(args.dayone, "create_entry", create_args)
        meta = mcp_tool_result_json(resp)
    except (OSError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1

    new_id = str(meta.get("entryId") or meta.get("entry_id") or "").strip()
    if not new_id:
        print(f"create_entry returned no entryId: {meta!r}", file=sys.stderr)
        return 1

    new_body = rewrite_entry_uuid_in_body(body, args.entry_id, new_id)
    if new_body != body:
        try:
            mcp_tools_call(
                args.dayone,
                "update_entry",
                {
                    "journal_id": journal_id,
                    "entry_id": new_id,
                    "text": new_body,
                },
            )
        except (OSError, RuntimeError, json.JSONDecodeError) as e:
            print(str(e), file=sys.stderr)
            return 1
        if args.verbose:
            print(
                f"update_entry: rewrote source UUID -> {new_id} ({len(body)} -> {len(new_body)} chars)",
                file=sys.stderr,
            )
    elif args.verbose:
        print(
            "update_entry: skipped (source UUID not present in body after normalize)",
            file=sys.stderr,
        )

    view_link = str(meta.get("viewLink") or "").strip()
    out = {
        "sourceEntryId": args.entry_id.strip(),
        "entryId": new_id,
        "journalName": meta.get("journalName"),
        "viewLink": view_link or None,
        "uuidRewriteApplied": new_body != body,
        "javaFencesFormatted": n_java if not args.no_format_java else 0,
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    db: Path = args.database
    if not db.is_file():
        print(f"Not a file: {db}", file=sys.stderr)
        return 2
    conn = connect_ro(db)
    try:
        body = fetch_markdown(conn, args.entry_id, args.journal)
    finally:
        conn.close()
    if body is None:
        print("No entry found (check --entry-id and --journal).", file=sys.stderr)
        return 1
    if args.output:
        args.output.write_text(body, encoding="utf-8")
    else:
        sys.stdout.write(body)
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    path = args.file
    if str(path) == "-":
        text = sys.stdin.read()
    else:
        if not path.is_file():
            print(f"Not a file: {path}", file=sys.stderr)
            return 2
        text = path.read_text(encoding="utf-8")
    if not text:
        print("Refusing empty body.", file=sys.stderr)
        return 2
    journal_id = args.journal_id or os.environ.get(
        "DAYONE_WORK_JOURNAL_ID", DEFAULT_WORK_JOURNAL_ID
    )
    arguments = {
        "journal_id": journal_id,
        "entry_id": args.entry_id.strip(),
        "text": text,
    }
    try:
        resp = mcp_tools_call(args.dayone, "update_entry", arguments)
    except (OSError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.verbose:
        print(tools_result_text(resp), file=sys.stderr)
    return 0


def _regex_flags(ns: argparse.Namespace) -> int:
    f = 0
    if ns.ignore_case:
        f |= re.IGNORECASE
    if ns.multiline:
        f |= re.MULTILINE
    if ns.dotall:
        f |= re.DOTALL
    return f


def cmd_fix_slide_headings(args: argparse.Namespace) -> int:
    if args.file:
        fp = args.file
        if not fp.is_file():
            print(f"Not a file: {fp}", file=sys.stderr)
            return 2
        body = fp.read_text(encoding="utf-8")
    else:
        if not args.journal:
            print("Need --journal when not using --file.", file=sys.stderr)
            return 2
        if not args.entry_id:
            print("Need --entry-id when reading from the database.", file=sys.stderr)
            return 2
        db: Path = args.database
        if not db.is_file():
            print(f"Not a file: {db}", file=sys.stderr)
            return 2
        conn = connect_ro(db)
        try:
            body = fetch_markdown(conn, args.entry_id, args.journal)
        finally:
            conn.close()
        if body is None:
            print("No entry found (check --entry-id and --journal).", file=sys.stderr)
            return 1

    emoji = args.emoji or DEFAULT_SLIDE_PLACEHOLDER_EMOJI
    new_body, n = transform_slide_h2_headings(body, emoji)
    if args.compact:
        new_body = compact_blank_line_runs(new_body)

    if args.verbose:
        print(f"slide-heading lines rewritten: {n}", file=sys.stderr)

    if args.dry_run or not args.apply:
        sys.stdout.write(new_body)
        return 0

    if not args.entry_id:
        print("--apply requires --entry-id.", file=sys.stderr)
        return 2

    journal_id = args.journal_id or os.environ.get(
        "DAYONE_WORK_JOURNAL_ID", DEFAULT_WORK_JOURNAL_ID
    )
    try:
        mcp_tools_call(
            args.dayone,
            "update_entry",
            {
                "journal_id": journal_id,
                "entry_id": args.entry_id.strip(),
                "text": new_body,
            },
        )
    except (OSError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def cmd_fix_fence_escapes(args: argparse.Namespace) -> int:
    if args.file:
        fp = args.file
        if not fp.is_file():
            print(f"Not a file: {fp}", file=sys.stderr)
            return 2
        body = fp.read_text(encoding="utf-8")
    else:
        if not args.journal:
            print("Need --journal when not using --file.", file=sys.stderr)
            return 2
        if not args.entry_id:
            print("Need --entry-id when reading from the database.", file=sys.stderr)
            return 2
        db: Path = args.database
        if not db.is_file():
            print(f"Not a file: {db}", file=sys.stderr)
            return 2
        conn = connect_ro(db)
        try:
            body = fetch_markdown(conn, args.entry_id, args.journal)
        finally:
            conn.close()
        if body is None:
            print("No entry found (check --entry-id and --journal).", file=sys.stderr)
            return 1

    new_body, n = transform_fence_escapes(
        body, also_outside_fences=args.whole_note
    )
    if args.verbose:
        scope = "whole note" if args.whole_note else "``` fences only"
        print(f"escape lines rewritten ({scope}): {n}", file=sys.stderr)

    if args.dry_run or not args.apply:
        sys.stdout.write(new_body)
        return 0

    if not args.entry_id:
        print("--apply requires --entry-id.", file=sys.stderr)
        return 2

    journal_id = args.journal_id or os.environ.get(
        "DAYONE_WORK_JOURNAL_ID", DEFAULT_WORK_JOURNAL_ID
    )
    try:
        mcp_tools_call(
            args.dayone,
            "update_entry",
            {
                "journal_id": journal_id,
                "entry_id": args.entry_id.strip(),
                "text": new_body,
            },
        )
    except (OSError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def _load_body_for_transform(args: argparse.Namespace) -> tuple[str | None, int]:
    """Return (body, exit_code). exit_code 0 on success; 2 usage/IO; 1 entry not found."""
    if args.file:
        fp = args.file
        if not fp.is_file():
            print(f"Not a file: {fp}", file=sys.stderr)
            return None, 2
        return fp.read_text(encoding="utf-8"), 0
    if not args.journal:
        print("Need --journal when not using --file.", file=sys.stderr)
        return None, 2
    if not args.entry_id:
        print("Need --entry-id when reading from the database.", file=sys.stderr)
        return None, 2
    db: Path = args.database
    if not db.is_file():
        print(f"Not a file: {db}", file=sys.stderr)
        return None, 2
    conn = connect_ro(db)
    try:
        body = fetch_markdown(conn, args.entry_id, args.journal)
    finally:
        conn.close()
    if body is None:
        print("No entry found (check --entry-id and --journal).", file=sys.stderr)
        return None, 1
    return body, 0


def cmd_consolidate_fences(args: argparse.Namespace) -> int:
    body, ec = _load_body_for_transform(args)
    if ec != 0:
        return ec
    assert body is not None
    new_body, n = transform_consolidate_fragment_fences(body)
    if args.verbose:
        print(f"multi-line fence groups built: {n}", file=sys.stderr)

    if args.dry_run or not args.apply:
        sys.stdout.write(new_body)
        return 0

    if not args.entry_id:
        print("--apply requires --entry-id.", file=sys.stderr)
        return 2

    journal_id = args.journal_id or os.environ.get(
        "DAYONE_WORK_JOURNAL_ID", DEFAULT_WORK_JOURNAL_ID
    )
    try:
        mcp_tools_call(
            args.dayone,
            "update_entry",
            {
                "journal_id": journal_id,
                "entry_id": args.entry_id.strip(),
                "text": new_body,
            },
        )
    except (OSError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def cmd_normalize_note(args: argparse.Namespace) -> int:
    body, ec = _load_body_for_transform(args)
    if ec != 0:
        return ec
    assert body is not None
    body, n_esc, n_con = apply_normalize_transforms(
        body,
        fences_only_escapes=args.fences_only_escapes,
        skip_escape=args.skip_escape,
        skip_consolidate=args.skip_consolidate,
    )
    if args.verbose:
        esc_scope = "fences only" if args.fences_only_escapes else "whole note + fences"
        print(
            f"escape lines fixed ({esc_scope}): {n_esc}; "
            f"multi-line fence groups built: {n_con}",
            file=sys.stderr,
        )

    n_out = 0
    if not args.skip_output_extract:
        body, n_out = transform_extract_output_from_fences(body)
        if args.verbose:
            print(f"OUTPUT blocks pulled out of ``` fences: {n_out}", file=sys.stderr)

    if args.dry_run or not args.apply:
        sys.stdout.write(body)
        return 0

    if not args.entry_id:
        print("--apply requires --entry-id.", file=sys.stderr)
        return 2

    journal_id = args.journal_id or os.environ.get(
        "DAYONE_WORK_JOURNAL_ID", DEFAULT_WORK_JOURNAL_ID
    )
    try:
        mcp_tools_call(
            args.dayone,
            "update_entry",
            {
                "journal_id": journal_id,
                "entry_id": args.entry_id.strip(),
                "text": body,
            },
        )
    except (OSError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def transform_replace_outside_fences(
    body: str,
    pattern: str,
    repl: str,
    *,
    count: int | None,
    flags: int,
) -> tuple[str, int]:
    """
    Apply ``re.subn`` only to **outside** triple-backtick regions so patterns like
    ``^## Slide:`` cannot rewrite lines that appear inside fenced code samples.
    """
    if not body:
        return body, 0
    had_trailing_nl = body[-1] in "\n\r"
    lines = body.splitlines(keepends=False)
    out_parts: list[str] = []
    outside_buf: list[str] = []
    inside_buf: list[str] = []
    in_fence = False
    remaining = None if count is None else max(0, count)
    total_subs = 0

    def flush_outside() -> None:
        nonlocal outside_buf, remaining, total_subs
        if not outside_buf:
            return
        chunk = "\n".join(outside_buf)
        outside_buf = []
        if remaining is not None and remaining == 0:
            out_parts.append(chunk)
            return
        try:
            if remaining is None:
                new_c, n = re.subn(pattern, repl, chunk, flags=flags)
            else:
                new_c, n = re.subn(pattern, repl, chunk, count=remaining, flags=flags)
        except re.error:
            raise
        total_subs += n
        if remaining is not None:
            remaining -= n
        out_parts.append(new_c)

    for line in lines:
        if line.strip().startswith("```"):
            if in_fence:
                out_parts.append("\n".join(inside_buf))
                inside_buf = []
                out_parts.append(line)
                in_fence = False
            else:
                flush_outside()
                out_parts.append(line)
                in_fence = True
            continue
        if in_fence:
            inside_buf.append(line)
        else:
            outside_buf.append(line)

    if in_fence:
        out_parts.append("\n".join(inside_buf))
    else:
        flush_outside()

    result = "\n".join(out_parts)
    if had_trailing_nl:
        result += "\n"
    return result, total_subs


def cmd_replace(args: argparse.Namespace) -> int:
    db: Path = args.database
    if not db.is_file():
        print(f"Not a file: {db}", file=sys.stderr)
        return 2
    conn = connect_ro(db)
    try:
        body = fetch_markdown(conn, args.entry_id, args.journal)
    finally:
        conn.close()
    if body is None:
        print("No entry found (check --entry-id and --journal).", file=sys.stderr)
        return 1

    flags = _regex_flags(args)
    count = 0 if args.count is None or args.count < 1 else args.count
    try:
        if args.outside_fences_only:
            eff = None if args.count is None or args.count < 1 else args.count
            new_body, n = transform_replace_outside_fences(
                body,
                args.pattern,
                args.repl,
                count=eff,
                flags=flags,
            )
        else:
            new_body, n = re.subn(
                args.pattern,
                args.repl,
                body,
                count=count,
                flags=flags,
            )
    except re.error as e:
        print(f"regex error: {e}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"replacements: {n}", file=sys.stderr)

    if args.dry_run or not args.apply:
        sys.stdout.write(new_body)
        return 0

    journal_id = args.journal_id or os.environ.get(
        "DAYONE_WORK_JOURNAL_ID", DEFAULT_WORK_JOURNAL_ID
    )
    try:
        mcp_tools_call(
            args.dayone,
            "update_entry",
            {
                "journal_id": journal_id,
                "entry_id": args.entry_id.strip(),
                "text": new_body,
            },
        )
    except (OSError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    db: Path = args.database
    if not db.is_file():
        print(f"Not a file: {db}", file=sys.stderr)
        return 2
    conn = connect_ro(db)
    try:
        body = fetch_markdown(conn, args.entry_id, args.journal)
    finally:
        conn.close()
    if body is None:
        print("No entry found (check --entry-id and --journal).", file=sys.stderr)
        return 1

    bad = False
    for s in args.contains:
        if s not in body:
            print(f"missing --contains: {s!r}", file=sys.stderr)
            bad = True
    for s in args.not_contains:
        if s in body:
            print(f"found --not-contains: {s!r}", file=sys.stderr)
            bad = True
    if args.regex:
        flags = _regex_flags(args)
        if not re.search(args.regex, body, flags):
            print(f"did not match --regex: {args.regex!r}", file=sys.stderr)
            bad = True
    return 1 if bad else 0


def cmd_journals(args: argparse.Namespace) -> int:
    try:
        resp = mcp_tools_call(args.dayone, "list_journals", {})
    except (OSError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(tools_result_text(resp))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "-d",
        "--database",
        type=Path,
        default=default_database(),
        help=f"Path to DayOne.sqlite (default: {DEFAULT_SQLITE}; override with $DAYONE_SQLITE)",
    )
    ap.add_argument(
        "--dayone",
        default=default_dayone_bin(),
        help="dayone CLI binary (default: $DAYONE_BIN, PATH, or /usr/local/bin/dayone)",
    )

    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="List recent entries (UUID + preview) for a journal")
    p.add_argument("-j", "--journal", required=True, help="Journal name (ZJOURNAL.ZNAME)")
    p.add_argument("-n", "--limit", type=int, default=30, help="Max rows (default: 30)")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("read", help="Print or save ZMARKDOWNTEXT for one entry")
    p.add_argument("-j", "--journal", help="Journal name (recommended)")
    p.add_argument("-e", "--entry-id", required=True, help="Entry UUID (ZUUID)")
    p.add_argument("-o", "--output", type=Path, help="Write markdown to this file")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser(
        "duplicate",
        help="create_entry copy: normalize-note + format-java-fences (default), then rewrite source UUID",
    )
    p.add_argument("-j", "--journal", required=True, help="Source journal name (ZJOURNAL.ZNAME)")
    p.add_argument(
        "-e",
        "--entry-id",
        required=True,
        help="Source entry UUID to copy",
    )
    p.add_argument(
        "--journal-id",
        help=f"MCP journal_id for create/update (default: $DAYONE_WORK_JOURNAL_ID or {DEFAULT_WORK_JOURNAL_ID})",
    )
    p.add_argument(
        "--fences-only-escapes",
        action="store_true",
        help="normalize: only collapse stacked backslashes inside ``` fences",
    )
    p.add_argument(
        "--raw",
        action="store_true",
        help="Skip normalize (escape + consolidate); fragile for fragmented PPTX-style fences on create",
    )
    p.add_argument(
        "--skip-output-extract",
        action="store_true",
        help="Do not move OUTPUT / trace lines out of ``` fences (after normalize, before Java format)",
    )
    p.add_argument(
        "--tags",
        help="Optional comma-separated tags for the new entry (passed to create_entry)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print normalized body only; do not call create_entry",
    )
    p.add_argument(
        "--no-format-java",
        action="store_true",
        help="Skip format-java-fences after normalize (default: run; keeps indentation like format-java-fences)",
    )
    p.add_argument(
        "--no-external",
        action="store_true",
        help="With Java formatting: do not run google-java-format; light dedent/trim only",
    )
    p.add_argument(
        "--aosp",
        action="store_true",
        help="With Java formatting: pass --aosp to google-java-format (4-space indents)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_duplicate)

    p = sub.add_parser(
        "update",
        help="Replace entry body via update_entry (full text from file or stdin)",
    )
    p.add_argument(
        "--journal-id",
        help=f"journal_id for MCP (default: $DAYONE_WORK_JOURNAL_ID or {DEFAULT_WORK_JOURNAL_ID})",
    )
    p.add_argument("-e", "--entry-id", required=True, help="Entry UUID")
    p.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Markdown file path, or - for stdin",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Print MCP result text to stderr")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser(
        "replace",
        help="Regex on full body (see --outside-fences-only); optionally apply via MCP",
    )
    p.add_argument("-j", "--journal", required=True)
    p.add_argument("-e", "--entry-id", required=True)
    p.add_argument(
        "--journal-id",
        help=f"For --apply (default: $DAYONE_WORK_JOURNAL_ID or {DEFAULT_WORK_JOURNAL_ID})",
    )
    p.add_argument("--pattern", required=True, help="Python regex pattern")
    p.add_argument("--repl", required=True, help="Replacement (backrefs allowed, e.g. \\1)")
    p.add_argument(
        "-c",
        "--count",
        type=int,
        default=None,
        help="Max substitutions (default: all)",
    )
    p.add_argument("-i", "--ignore-case", action="store_true")
    p.add_argument("-m", "--multiline", action="store_true")
    p.add_argument("-s", "--dotall", action="store_true")
    p.add_argument(
        "--outside-fences-only",
        action="store_true",
        help="Only run the regex on text outside ``` fences (avoids corrupting code blocks)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write result with update_entry (omit for dry-run to stdout)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print transformed body only; never call MCP",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_replace)

    p = sub.add_parser(
        "fix-slide-headings",
        help="Rewrite exported ## Slide n: titles (empty -> placeholder emoji); optional --compact",
    )
    p.add_argument(
        "--file",
        type=Path,
        help="Transform this markdown file instead of reading the entry from SQLite",
    )
    p.add_argument("-j", "--journal", help="Journal name (required when not using --file)")
    p.add_argument(
        "-e",
        "--entry-id",
        help="Entry UUID; required when reading from DB; required with --apply when using --file",
    )
    p.add_argument(
        "--journal-id",
        help=f"For --apply (default: $DAYONE_WORK_JOURNAL_ID or {DEFAULT_WORK_JOURNAL_ID})",
    )
    p.add_argument(
        "--emoji",
        default="",
        help=f"Placeholder for empty slide title (default: U+1F6DD playground slide)",
    )
    p.add_argument(
        "--compact",
        action="store_true",
        help="Collapse runs of 3+ blank lines to a single blank line",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write result with update_entry (omit for stdout only)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print transformed body only; never call MCP",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_fix_slide_headings)

    p = sub.add_parser(
        "fix-fence-escapes",
        help="Collapse stacked backslashes before Markdown punctuation (default: ``` fences only)",
    )
    p.add_argument(
        "--file",
        type=Path,
        help="Transform this markdown file instead of reading the entry from SQLite",
    )
    p.add_argument("-j", "--journal", help="Journal name (required when not using --file)")
    p.add_argument(
        "-e",
        "--entry-id",
        help="Entry UUID; required when reading from DB; required with --apply when using --file",
    )
    p.add_argument(
        "--journal-id",
        help=f"For --apply (default: $DAYONE_WORK_JOURNAL_ID or {DEFAULT_WORK_JOURNAL_ID})",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write result with update_entry (omit for stdout only)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print transformed body only; never call MCP",
    )
    p.add_argument(
        "--whole-note",
        action="store_true",
        help="Also collapse escapes outside ``` fences (headings, notes, bullets)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_fix_fence_escapes)

    p = sub.add_parser(
        "consolidate-fences",
        help="Merge one-line ``` fragments (bare or ```lang). Run after escape cleanup — prefer normalize-note",
    )
    p.add_argument(
        "--file",
        type=Path,
        help="Transform this markdown file instead of reading the entry from SQLite",
    )
    p.add_argument("-j", "--journal", help="Journal name (required when not using --file)")
    p.add_argument(
        "-e",
        "--entry-id",
        help="Entry UUID; required when reading from DB; required with --apply when using --file",
    )
    p.add_argument(
        "--journal-id",
        help=f"For --apply (default: $DAYONE_WORK_JOURNAL_ID or {DEFAULT_WORK_JOURNAL_ID})",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write result with update_entry (omit for stdout only)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print transformed body only; never call MCP",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_consolidate_fences)

    p = sub.add_parser(
        "normalize-note",
        help="Escape cleanup (whole note by default) then consolidate-fences; then use format-java-fences",
    )
    p.add_argument(
        "--file",
        type=Path,
        help="Transform this markdown file instead of reading the entry from SQLite",
    )
    p.add_argument("-j", "--journal", help="Journal name (required when not using --file)")
    p.add_argument(
        "-e",
        "--entry-id",
        help="Entry UUID; required when reading from DB; required with --apply when using --file",
    )
    p.add_argument(
        "--journal-id",
        help=f"For --apply (default: $DAYONE_WORK_JOURNAL_ID or {DEFAULT_WORK_JOURNAL_ID})",
    )
    p.add_argument(
        "--fences-only-escapes",
        action="store_true",
        help="Only collapse backslashes inside ``` fences (legacy; default cleans whole note)",
    )
    p.add_argument(
        "--skip-escape",
        action="store_true",
        help="Do not run stacked-backslash cleanup",
    )
    p.add_argument(
        "--skip-consolidate",
        action="store_true",
        help="Do not merge one-line fence fragments",
    )
    p.add_argument(
        "--skip-output-extract",
        action="store_true",
        help="Do not move OUTPUT / trace lines out of ``` fences into blockquotes",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write result with update_entry (omit for stdout only)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print transformed body only; never call MCP",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_normalize_note)

    p = sub.add_parser(
        "format-java-fences",
        help="Reformat Java inside ``` fences (optional google-java-format; else light dedent)",
    )
    p.add_argument(
        "--file",
        type=Path,
        help="Transform this markdown file instead of reading the entry from SQLite",
    )
    p.add_argument("-j", "--journal", help="Journal name (required when not using --file)")
    p.add_argument(
        "-e",
        "--entry-id",
        help="Entry UUID; required when reading from DB; required with --apply when using --file",
    )
    p.add_argument(
        "--journal-id",
        help=f"For --apply (default: $DAYONE_WORK_JOURNAL_ID or {DEFAULT_WORK_JOURNAL_ID})",
    )
    p.add_argument(
        "--no-external",
        action="store_true",
        help="Do not run google-java-format; only light tab/dedent/trim cleanup",
    )
    p.add_argument(
        "--aosp",
        action="store_true",
        help="Pass --aosp to google-java-format (4-space indents)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write result with update_entry (omit for stdout only)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print transformed body only; never call MCP",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_format_java_fences)

    p = sub.add_parser("verify", help="Assert substrings / regex against local DB body")
    p.add_argument("-j", "--journal", required=True)
    p.add_argument("-e", "--entry-id", required=True)
    p.add_argument(
        "--contains",
        action="append",
        default=[],
        metavar="STR",
        help="Must appear (repeatable)",
    )
    p.add_argument(
        "--not-contains",
        action="append",
        default=[],
        metavar="STR",
        help="Must not appear (repeatable)",
    )
    p.add_argument("--regex", help="Must match somewhere in body")
    p.add_argument("-i", "--ignore-case", action="store_true")
    p.add_argument("-m", "--multiline", action="store_true")
    p.add_argument("-s", "--dotall", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("journals", help="List journals via MCP (names + ids)")
    p.set_defaults(func=cmd_journals)

    return ap


def main() -> None:
    ap = build_parser()
    args = ap.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
