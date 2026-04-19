#!/usr/bin/env python3
"""
Convert a PPTX slide deck into slide-ready Markdown.

Goals:
- No third-party deps (stdlib only)
- Drop common footer/copyright lines (e.g. apluscompsci.com)
- Detect code-looking blocks and render them as fenced code blocks
- After building Markdown, rewrite legacy ``## Slide:`` / ``## Slide n:`` lines to ``___`` + ``## <title>``
  **outside `` ``` `` fences only** (same idea as ``dayone_crud`` ``replace --outside-fences-only``)
- Optional: :func:`embed_markdown_images_as_data_uris` (or ``--embed-images``) turns ``![alt](url)``
  / ``<img src=…>`` into ``<img src="data:image/…;base64,…"/>``; use a custom ``fetcher`` when
  images come from Day One MCP or other non-HTTP sources.
"""

from __future__ import annotations

import argparse
import base64
import html
import os
import re
import sys
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

# Work journal default; matches dayone-crud (override with DAYONE_WORK_JOURNAL_ID).
_DEFAULT_WORK_JOURNAL_ID = "105395021376"

_NS_PML = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

_PPTX_FOOTER_DROP_RE = re.compile(r"(apluscompsci\.com|a\+\s*computer\s*science|©)", re.IGNORECASE)
_MONO_FONTS = {
    "courier",
    "courier new",
    "consolas",
    "menlo",
    "monaco",
    "liberation mono",
    "source code pro",
    "lucida console",
}


@dataclass
class Para:
    text: str
    max_font_sz: int
    any_monospace: bool


@dataclass
class SlideMD:
    title: str
    blocks: List["Block"]


@dataclass
class Block:
    kind: str  # bullets | text | code | table2
    lines: List[str]


def _pptx_slide_paths(z: zipfile.ZipFile) -> List[str]:
    names = [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]

    def _num(path: str) -> int:
        m = re.search(r"slide(\d+)\.xml$", path)
        return int(m.group(1)) if m else 10**9

    return sorted(names, key=_num)


def _pptx_is_footer_line(text: str) -> bool:
    t = " ".join(text.split()).strip()
    if not t:
        return False
    return bool(_PPTX_FOOTER_DROP_RE.search(t))


def _pptx_para_font_props(p_el: ET.Element) -> Tuple[int, bool]:
    max_sz = 0
    any_mono = False
    for rpr in p_el.findall(".//a:rPr", _NS_PML):
        sz = rpr.get("sz")
        if sz and sz.isdigit():
            max_sz = max(max_sz, int(sz))
        latin = rpr.find("a:latin", _NS_PML)
        if latin is not None:
            tf = (latin.get("typeface") or "").strip().lower()
            if tf in _MONO_FONTS:
                any_mono = True
    return max_sz, any_mono


def _pptx_extract_paragraphs(slide_xml: str) -> List[Para]:
    try:
        root = ET.fromstring(slide_xml)
    except ET.ParseError:
        return []

    out: List[Para] = []
    for p_el in root.findall(".//a:p", _NS_PML):
        max_sz, any_mono = _pptx_para_font_props(p_el)
        parts: List[str] = []
        for child in list(p_el):
            if child.tag.endswith("}r"):
                t_el = child.find(".//a:t", _NS_PML)
                if t_el is not None and t_el.text:
                    parts.append(t_el.text)
            elif child.tag.endswith("}br"):
                parts.append("\n")
        if not parts:
            parts = [t_el.text or "" for t_el in p_el.findall(".//a:t", _NS_PML)]
        text = "".join(parts).strip()
        if text:
            out.append(Para(text=text, max_font_sz=max_sz, any_monospace=any_mono))
    return out


def _looks_like_code(text: str) -> bool:
    return bool(re.search(r"[{}();]|^\s*(public|private|class|def|for|while|if)\b", text))


def _try_parse_name_use_table(text: str) -> Optional[List[Tuple[str, str]]]:
    """
    Heuristic for PPTX "tables" that flatten into a single multi-line paragraph.

    Typical pattern (from the sample deck):
      indexOf(x)
      returns ...
      returns ...
      contains(x)
      returns ...
      returns ...

    We convert this into pipe rows inside a fenced code block (Day One: not a GFM table).
    """
    if "\n" not in text:
        return None
    if any(ch in text for ch in "{};"):
        return None

    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(raw_lines) < 4:
        return None

    def is_name_line(ln: str) -> bool:
        return (
            "(" in ln
            and ")" in ln
            and " " not in ln
            and not ln.lower().startswith("return")
            and len(ln) <= 80
        )

    def is_use_line(ln: str) -> bool:
        return ln.lower().startswith(("return", "returns", "puts", "checks", "fills", "shifts", "reverses"))

    name_count = sum(1 for ln in raw_lines if is_name_line(ln))
    useish_count = sum(1 for ln in raw_lines if is_use_line(ln))
    if name_count < 2 or useish_count < 2:
        return None

    rows: List[Tuple[str, str]] = []
    cur_name: Optional[str] = None
    cur_use: List[str] = []

    def flush() -> None:
        nonlocal cur_name, cur_use
        if cur_name and cur_use:
            rows.append((cur_name, "<br>".join(cur_use)))
        cur_name = None
        cur_use = []

    for ln in raw_lines:
        if is_name_line(ln):
            flush()
            cur_name = ln
            continue
        if cur_name:
            cur_use.append(ln)

    flush()

    return rows if len(rows) >= 2 else None


def _is_name_use_table_name_line(text: str) -> bool:
    t = text.strip()
    return (
        "(" in t
        and ")" in t
        and " " not in t
        and not t.lower().startswith(("return", "returns"))
        and len(t) <= 80
    )


def _is_name_use_table_use_line(text: str) -> bool:
    t = text.strip().lower()
    return t.startswith(("return", "returns", "puts", "checks", "fills", "shifts", "reverses"))


def slides_from_pptx(pptx_path: Path) -> Tuple[Optional[str], List[SlideMD]]:
    deck_title = pptx_path.stem.replace("_", " ").strip() or None
    slides: List[SlideMD] = []

    with zipfile.ZipFile(pptx_path, "r") as z:
        for slide_path in _pptx_slide_paths(z):
            try:
                xml_bytes = z.read(slide_path)
            except KeyError:
                continue

            paras = _pptx_extract_paragraphs(xml_bytes.decode("utf-8", errors="replace"))
            paras = [p for p in paras if not _pptx_is_footer_line(p.text)]
            if not paras:
                continue

            # Choose title: largest font size wins, otherwise first.
            title_idx = max(range(len(paras)), key=lambda i: paras[i].max_font_sz) if paras else 0
            title = paras[title_idx].text.strip()
            body_paras = [p for i, p in enumerate(paras) if i != title_idx]

            blocks: List[Block] = []
            cur_code: List[str] = []
            cur_text: List[str] = []

            def flush_text() -> None:
                nonlocal cur_text
                if not cur_text:
                    return
                if len(cur_text) == 1:
                    blocks.append(Block(kind="text", lines=cur_text))
                else:
                    blocks.append(Block(kind="bullets", lines=cur_text))
                cur_text = []

            def flush_code() -> None:
                nonlocal cur_code
                if not cur_code:
                    return
                blocks.append(Block(kind="code", lines=cur_code))
                cur_code = []

            i = 0
            while i < len(body_paras):
                p = body_paras[i]
                text = p.text.strip()
                if not text:
                    i += 1
                    continue

                # Table detection (across multiple paragraphs).
                if _is_name_use_table_name_line(text) and i + 1 < len(body_paras):
                    nxt = body_paras[i + 1].text.strip()
                    if nxt and _is_name_use_table_use_line(nxt):
                        rows: List[Tuple[str, str]] = []
                        cur_name = text
                        cur_use: List[str] = []
                        j = i + 1
                        while j < len(body_paras):
                            t = body_paras[j].text.strip()
                            if not t:
                                j += 1
                                continue
                            if _is_name_use_table_name_line(t):
                                if cur_name and cur_use:
                                    rows.append((cur_name, "<br>".join(cur_use)))
                                cur_name = t
                                cur_use = []
                                j += 1
                                continue
                            if _is_name_use_table_use_line(t):
                                # Normalize embedded newlines inside a cell into <br>
                                cur_use.append("<br>".join(ln.strip() for ln in t.splitlines() if ln.strip()))
                                j += 1
                                continue
                            break

                        if cur_name and cur_use:
                            rows.append((cur_name, "<br>".join(cur_use)))

                        if len(rows) >= 2:
                            flush_code()
                            flush_text()
                            blocks.append(Block(kind="table2", lines=[f"{n}\t{u}" for (n, u) in rows]))
                            i = j
                            continue

                # Table detection (single paragraph with embedded line breaks).
                if "\n" in text:
                    table_rows = _try_parse_name_use_table(text)
                    if table_rows:
                        flush_code()
                        flush_text()
                        blocks.append(Block(kind="table2", lines=[f"{name}\t{use}" for (name, use) in table_rows]))
                        i += 1
                        continue

                is_code = p.any_monospace or ("\n" in text) or _looks_like_code(text)
                if is_code:
                    flush_text()
                    cur_code.extend(text.splitlines())
                else:
                    flush_code()
                    cur_text.append(text)
                i += 1

            flush_code()
            flush_text()

            slides.append(SlideMD(title=title, blocks=blocks))

    return deck_title, slides


def _dayone_crud_script() -> Path:
    """Sibling skill: skills/dayone-crud/scripts/dayone_crud.py"""
    skills_root = Path(__file__).resolve().parent.parent.parent
    return skills_root / "dayone-crud" / "scripts" / "dayone_crud.py"


def _transform_regex_outside_fences(
    body: str,
    pattern: str,
    repl: str,
    *,
    count: Optional[int],
    flags: int,
) -> tuple[str, int]:
    """
    Apply ``re.subn`` only outside triple-backtick regions (aligned with
    ``dayone_crud.transform_replace_outside_fences``).
    """
    if not body:
        return body, 0
    had_trailing_nl = body[-1] in "\n\r"
    lines = body.splitlines(keepends=False)
    out_parts: List[str] = []
    outside_buf: List[str] = []
    inside_buf: List[str] = []
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
        if remaining is None:
            new_c, n = re.subn(pattern, repl, chunk, flags=flags)
        else:
            new_c, n = re.subn(pattern, repl, chunk, count=remaining, flags=flags)
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


def finalize_slide_markdown(md: str) -> str:
    """
    Durable slide-heading pipeline: ``___`` + ``## <title>`` for any legacy
    ``## Slide n:`` / ``## Slide:`` lines **only outside fenced code** (never
    touches `` ``` `` bodies).
    Idempotent on Markdown that already uses ``___`` + ``## …``.
    """
    # Numbered export form first (e.g. ``## Slide 3: List``).
    md, _ = _transform_regex_outside_fences(
        md,
        r"^## Slide \d+:\s*(.*)$",
        r"___\n## \1",
        count=None,
        flags=re.MULTILINE,
    )
    # Plain ``## Slide: Title`` (no slide number).
    md, _ = _transform_regex_outside_fences(
        md,
        r"^## Slide:\s*(.*)$",
        r"___\n## \1",
        count=None,
        flags=re.MULTILINE,
    )
    return md


def to_slide_ready_markdown(
    deck_title: Optional[str],
    slides: List[SlideMD],
    *,
    source_basename: str,
    entry_id: Optional[str] = None,
) -> str:
    """
    Day One header (see dayone-crud / ppt2markdown skill):
    1. H1 title
    2. Plain line: source .pptx filename only
    3. H7 line with entry UUID (####### <id>) when entry_id is set; omitted for stdout-only preview

    Per slide: ``___`` then ``## <slide title>`` (not ``## Slide:`` — avoids regex migration that can break fences).
    """
    title = deck_title or "Slide Deck"
    lines: List[str] = [f"# {title}", source_basename.strip()]
    if entry_id:
        lines.append(f"####### {entry_id.strip()}")
    lines.append("")

    for s in slides:
        # Horizontal rule + H2 title (not "## Slide: …") so Day One / duplicate never need
        # regex rewrites that can touch fenced code. Matches user-facing slide delimiter preference.
        lines.append("___")
        lines.append(f"## {s.title}")
        for b in s.blocks:
            if b.kind == "code":
                lines.append("")
                lines.append("```")
                lines.extend(b.lines)
                lines.append("```")
                lines.append("")
            elif b.kind == "table2":
                # Pipe rows inside a fenced code block (Day One: tabular data as monospace, not GFM tables).
                inner: List[str] = ["| Name | Use |", "| --- | --- |"]
                for row in b.lines:
                    name, use = (row.split("\t", 1) + [""])[:2]
                    use = use.replace("<br>", " ")
                    use = use.replace("\n", " ")
                    use = " ".join(use.split())
                    inner.append(f"| {name.strip()} | {use.strip()} |")
                lines.append("")
                lines.append("```")
                lines.extend(inner)
                lines.append("```")
                lines.append("")
            elif b.kind == "text":
                for t in b.lines:
                    lines.append(f"- {t}")
            else:
                for t in b.lines:
                    lines.append(f"- {t}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


_UUID_FROM_NEW_RE = re.compile(
    r"Created new entry with uuid:\s*([0-9A-Fa-f]{32})\s*",
    re.IGNORECASE,
)

# Markdown / HTML image references for ``embed_markdown_images_as_data_uris``.
_RE_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_RE_HTML_IMG_SRC = re.compile(
    r"(<img\b[^>]*\bsrc=)([\"'])([^\"']+)(\2)([^>]*>)",
    re.IGNORECASE,
)


def _mime_from_image_magic(data: bytes) -> str:
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def fetch_image_bytes_default(
    url: str,
    *,
    base_dir: Optional[Path] = None,
    max_bytes: int = 5_000_000,
    timeout_s: float = 60.0,
) -> Optional[bytes]:
    """
    Stdlib-only fetch: ``http``/``https`` via ``urllib``, local paths via ``Path.read_bytes``.

    Returns ``None`` if the URL scheme is unsupported or the read fails.
    """
    raw = url.strip()
    if not raw:
        return None
    low = raw.lower()
    if low.startswith(("http://", "https://")):
        try:
            req = urllib.request.Request(
                raw,
                headers={"User-Agent": "ppt2markdown/1 (image embed)"},
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = resp.read(max_bytes + 1)
        except (urllib.error.URLError, OSError, ValueError):
            return None
        if len(data) > max_bytes:
            return None
        return data
    # file:// or plain path
    path_s = raw[7:] if low.startswith("file://") else raw
    p = Path(path_s).expanduser()
    if not p.is_absolute() and base_dir is not None:
        p = (base_dir / p).resolve()
    try:
        if not p.is_file():
            return None
        data = p.read_bytes()
    except OSError:
        return None
    if len(data) > max_bytes:
        return None
    return data


def _md_image_url_from_target(inner: str) -> str:
    """First path/URL from ``![alt](target)`` target (supports ``<url>`` and ``url "title"``)."""
    s = inner.strip()
    if s.startswith("<") and ">" in s:
        return s[1 : s.index(">")].strip()
    head = s.split('"', maxsplit=1)[0].strip()
    return head.split()[0] if head.split() else head


def embed_markdown_images_as_data_uris(
    markdown: str,
    *,
    fetcher: Optional[Callable[[str], Optional[bytes]]] = None,
    base_dir: Optional[Path] = None,
    max_image_bytes: int = 5_000_000,
) -> str:
    """
    Replace image references with ``<img src="data:image/…;base64,…"/>`` tags.

    Handles:

    - CommonMark images: ``![alt](url)`` (optional title in parentheses not required).
    - Existing HTML: ``<img … src="url" …>`` — replaces ``src`` when fetch succeeds.

    **Fetching:** default uses :func:`fetch_image_bytes_default` (HTTP(S) and local files).
    Pass ``fetcher(url) -> bytes | None`` to inject bytes from another source (for example
    attachment blobs resolved via Day One MCP / CLI in an agent workflow). If ``fetcher``
    returns ``None``, the original markup is left unchanged.

    Unsupported schemes (e.g. ``dayone-moment://``) are left as-is unless ``fetcher`` handles them.
    """
    fetch = fetcher or (
        lambda u: fetch_image_bytes_default(
            u, base_dir=base_dir, max_bytes=max_image_bytes
        )
    )

    def _data_uri_img(alt: str, data: bytes) -> str:
        mime = _mime_from_image_magic(data)
        if mime == "application/octet-stream":
            mime = "image/png"
        b64 = base64.standard_b64encode(data).decode("ascii")
        a = html.escape(alt, quote=True)
        return f'<img alt="{a}" src="data:{mime};base64,{b64}" />'

    def _sub_md(m: re.Match[str]) -> str:
        alt = m.group(1)
        url = _md_image_url_from_target(m.group(2))
        if not url or url.startswith(("<", "data:")):
            return m.group(0)
        data = fetch(url)
        if data is None:
            return m.group(0)
        return _data_uri_img(alt, data)

    out = _RE_MD_IMAGE.sub(_sub_md, markdown)

    def _sub_html(m: re.Match[str]) -> str:
        pre, q1, url, q2, rest = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        if url.strip().lower().startswith("data:"):
            return m.group(0)
        data = fetch(url.strip())
        if data is None:
            return m.group(0)
        mime = _mime_from_image_magic(data)
        if mime == "application/octet-stream":
            mime = "image/png"
        b64 = base64.standard_b64encode(data).decode("ascii")
        new_src = f"data:{mime};base64,{b64}"
        return f"{pre}{q1}{new_src}{q2}{rest}"

    out = _RE_HTML_IMG_SRC.sub(_sub_html, out)
    return out


def _parse_new_entry_uuid(combined_output: str) -> str:
    m = _UUID_FROM_NEW_RE.search(combined_output)
    if not m:
        raise SystemExit(
            "Could not parse new entry UUID from dayone output; expected "
            "'Created new entry with uuid: <32 hex chars>'"
        )
    return m.group(1).upper()


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Convert PPTX to slide-ready Markdown and optionally post to Day One.")
    ap.add_argument(
        "pptx_path",
        type=Path,
        nargs="?",
        default=None,
        help="Path to .pptx slide deck (omit when using --embed-images)",
    )
    ap.add_argument(
        "--post",
        action="store_true",
        help="Post the generated Markdown to Day One (Work journal, tag: cursor) using the dayone CLI.",
    )
    ap.add_argument(
        "--journal",
        default="Work",
        help="Day One journal name to post to (default: Work). Ignored unless --post is set.",
    )
    ap.add_argument(
        "--tags",
        default="cursor",
        help="Comma-separated Day One tags (default: cursor). Ignored unless --post is set.",
    )
    ap.add_argument(
        "--embed-images",
        type=Path,
        metavar="MARKDOWN",
        default=None,
        help="Read MARKDOWN, replace ![alt](url) and <img src=…> with data-URI <img/> (http/https/file paths). "
        "Writes UTF-8 to stdout. For dayone-moment:// or other schemes, use embed_markdown_images_as_data_uris(..., fetcher=...) from Python.",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.embed_images is not None:
        md_path = args.embed_images.expanduser()
        if not md_path.is_file():
            raise SystemExit(f"Not a file: {md_path}")
        md_in = md_path.read_text(encoding="utf-8")
        md_out = embed_markdown_images_as_data_uris(md_in, base_dir=md_path.parent)
        sys.stdout.write(md_out)
        return 0

    if args.pptx_path is None:
        raise SystemExit("pptx_path is required unless --embed-images MARKDOWN is used")

    pptx_path = args.pptx_path.expanduser()
    deck_title, slides = slides_from_pptx(pptx_path)
    source_name = pptx_path.name

    if args.post:
        if not shutil.which("dayone"):
            raise SystemExit("dayone CLI not found on PATH")
        crud = _dayone_crud_script()
        if not crud.is_file():
            raise SystemExit(f"dayone_crud.py not found at {crud} (needed to set entry id header)")

        # UUID is unknown until after `dayone new`; create with lines 1–2 + body, then update with H7 id line.
        md_partial = finalize_slide_markdown(
            to_slide_ready_markdown(deck_title, slides, source_basename=source_name, entry_id=None)
        )
        proc = subprocess.run(
            ["dayone", "-j", args.journal, "-t", args.tags, "--", "new"],
            input=md_partial,
            text=True,
            capture_output=True,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            sys.stdout.write(proc.stdout or "")
            sys.stderr.write(proc.stderr or "")
            raise SystemExit(proc.returncode or 1)
        entry_id = _parse_new_entry_uuid(out)
        md_full = finalize_slide_markdown(
            to_slide_ready_markdown(deck_title, slides, source_basename=source_name, entry_id=entry_id)
        )
        journal_id = os.environ.get("DAYONE_WORK_JOURNAL_ID", _DEFAULT_WORK_JOURNAL_ID)
        dayone_bin = os.environ.get("DAYONE_BIN") or shutil.which("dayone") or "dayone"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".md",
            delete=False,
        ) as tmp:
            tmp.write(md_full)
            tmp_path = tmp.name
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(crud),
                    "--dayone",
                    dayone_bin,
                    "update",
                    "--journal-id",
                    journal_id,
                    "-e",
                    entry_id,
                    "--file",
                    tmp_path,
                ],
                check=True,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        print(f"Created new entry with uuid: {entry_id}", flush=True)
        return 0

    md = finalize_slide_markdown(
        to_slide_ready_markdown(deck_title, slides, source_basename=source_name, entry_id=None)
    )
    print(md, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

