#!/usr/bin/env python3
"""
Generate a Moodle-forum-paste-ready slide deck HTML fragment from a constrained
source:

- slide-ready Markdown (like `AML_test_slidedeck.md`)
- PPTX (`.pptx`) where slide text is extracted and rendered into the same HTML deck
  structure as the markdown workflow.

Output is intentionally a single HTML fragment (no doctype/html/head/body) with:
- scoped CSS under #aml-openclaw
- a 600px scrollable viewport wrapper for Moodle posts

This is a best-effort "reverse engineered" generator based on the existing
`aml_openclaw_slides.html` structure and styling.

Day One sourced markdown: merge fragmented table fences, unescape `\\-` style pipe rows for table HTML, and promote fenced pipe tables to week-table output; see ../SKILL.md.
A fenced block whose body is ``<svg>…</svg>`` is emitted as inline SVG (``md-slide-svg``), not ``<pre><code>``.
``![](dayone-moment://…)`` is resolved via local ``DayOne.sqlite`` + ``DayOnePhotos`` (see ``_try_dayone_moment_data_uri``) and embedded as ``data:image/…;base64,…`` on the ``<img/>`` tag.
For stacked escapes / one-line code fences in the *source*, normalize with dayone-crud
(`normalize-note`) before running this script.

Java `` ```java `` / heuristic Java fences are passed through optional ``google-java-format``
(same binary as dayone-crud: ``GOOGLE_JAVA_FORMAT`` or PATH). Set ``MARKDOWN2SLIDES_JAVA_AOSP=1``
for ``--aosp`` (4-space indents). If the tool is missing, a light dedent + brace-indent fallback runs.
"""

from __future__ import annotations

import argparse
import base64
import html
import os
import re
import sqlite3
import shutil
import subprocess
import tempfile
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse


CSS_AND_WRAPPER_PREFIX = """<style>
  @import url('https://fonts.googleapis.com/css2?family=Jua&display=swap');
  @import url('https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Google+Sans+Display:wght@400;700&family=Roboto:wght@300;400;500&display=swap');

  #aml-openclaw {
    --blue: #1a73e8;
    --blue-dark: #1557b0;
    --blue-light: #e8f0fe;
    --teal: #137333;
    --teal-light: #e6f4ea;
    --yellow: #f9ab00;
    --yellow-light: #fef7e0;
    --red: #d93025;
    --red-light: #fce8e6;
    --gray-50: #f8f9fa;
    --gray-100: #f1f3f4;
    --gray-200: #e8eaed;
    --gray-400: #9aa0a6;
    --gray-600: #5f6368;
    --gray-700: #4b4f54;
    --gray-800: #3c4043;
    --gray-900: #202124;
    --white: #ffffff;
    --slide-width: 900px;
    --slide-radius: 8px;
    --shadow: 0 1px 3px rgba(60,64,67,0.3), 0 4px 8px rgba(60,64,67,0.15);
    --shadow-hover: 0 2px 6px rgba(60,64,67,0.35), 0 8px 20px rgba(60,64,67,0.2);

    background: #e8eaed;
    font-family: 'Roboto', sans-serif;
    color: var(--gray-900);
    padding: 40px 20px 80px;
    border-radius: 8px;
  }

  #aml-openclaw,
  #aml-openclaw * { box-sizing: border-box; margin: 0; padding: 0; }

  /* UI component styles (top/bottom bar). Component is currently disabled in HTML. */
  #aml-openclaw .topbar {
    background: var(--white);
    border-bottom: 1px solid var(--gray-200);
    padding: 10px 24px;
    display: flex;
    align-items: center;
    gap: 12px;
    position: static;
    box-shadow: 0 1px 3px rgba(60,64,67,0.15);
    margin: 0 0 24px;
    border-radius: 8px;
  }

  #aml-openclaw .topbar-icon {
    width: 28px;
    height: 28px;
    background: linear-gradient(135deg, #fbbc04 25%, #f28b00 100%);
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    color: white;
    font-weight: 700;
    flex-shrink: 0;
  }

  #aml-openclaw .topbar-title {
    font-family: 'Roboto', sans-serif;
    font-size: 18px;
    color: var(--gray-800);
    font-weight: 400;
  }

  #aml-openclaw .topbar-meta {
    font-size: 12px;
    color: var(--gray-400);
    margin-left: auto;
  }

  /* Slide container */
  #aml-openclaw .deck {
    max-width: var(--slide-width);
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 32px;
  }

  #aml-openclaw .slide {
    background: var(--white);
    border-radius: var(--slide-radius);
    box-shadow: var(--shadow);
    overflow: visible;
    transition: box-shadow 0.2s ease;
    position: relative;
  }

  #aml-openclaw .slide:hover {
    box-shadow: var(--shadow-hover);
  }

  /* Slide number badge */
  #aml-openclaw .slide-num {
    position: absolute;
    top: 14px;
    right: 18px;
    font-size: 11px;
    color: var(--gray-400);
    font-family: 'Roboto', sans-serif;
    font-weight: 500;
    letter-spacing: 0.5px;
  }

  /* ── TITLE SLIDE ── */
  #aml-openclaw .slide-title {
    background: linear-gradient(135deg, #1a73e8 0%, #0d52bf 60%, #073a9e 100%);
    padding: 70px 64px 60px;
    color: white;
    min-height: 320px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: relative;
    overflow: hidden;
  }

  #aml-openclaw .slide-title::before {
    content: '';
    position: absolute;
    top: -60px; right: -60px;
    width: 300px; height: 300px;
    border-radius: 50%;
    background: rgba(255,255,255,0.07);
  }

  #aml-openclaw .slide-title::after {
    content: '';
    position: absolute;
    bottom: -80px; left: -40px;
    width: 220px; height: 220px;
    border-radius: 50%;
    background: rgba(255,255,255,0.05);
  }

  #aml-openclaw .slide-title h1 {
    font-family: 'Jua', 'Google Sans Display', 'Roboto', sans-serif;
    font-size: 42px;
    font-weight: 700;
    line-height: 1.2;
    margin-bottom: 20px;
    position: relative;
    z-index: 1;
  }

  #aml-openclaw .slide-title .subtitle {
    font-size: 16px;
    opacity: 0.85;
    font-weight: 400;
    line-height: 1.6;
    position: relative;
    z-index: 1;
  }

  #aml-openclaw .meta-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px 32px;
    margin-top: 28px;
    position: relative;
    z-index: 1;
  }

  #aml-openclaw .meta-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  #aml-openclaw .meta-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.65;
    font-weight: 500;
  }

  #aml-openclaw .meta-value {
    font-size: 13px;
    opacity: 0.92;
    font-weight: 500;
  }

  /* ── SECTION HEADER SLIDE ── */
  #aml-openclaw .slide-section-header {
    background: var(--blue-light);
    border-left: 6px solid var(--blue);
    padding: 48px 56px;
    min-height: 180px;
    display: flex;
    align-items: center;
  }

  #aml-openclaw .slide-section-header h2 {
    font-family: 'Jua', 'Google Sans Display', 'Roboto', sans-serif;
    font-size: 34px;
    font-weight: 700;
    color: var(--blue-dark);
  }

  /* ── CONTENT SLIDE ── */
  #aml-openclaw .slide-content {
    padding: 44px 56px 48px;
    min-height: 260px;
  }

  #aml-openclaw .slide-content h2 {
    font-family: 'Jua', 'Google Sans Display', 'Roboto', sans-serif;
    font-size: 30px;
    font-weight: 700;
    color: var(--blue-dark);
    margin-bottom: 28px;
    padding-bottom: 12px;
    border-bottom: 2px solid var(--blue-light);
  }

  #aml-openclaw .slide-content h3 {
    font-family: 'Google Sans', 'Roboto', sans-serif;
    font-size: 16px;
    font-weight: 700;
    color: var(--gray-800);
    margin: 24px 0 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  /* Markdown ### lines on content slides (e.g. import …) — no uppercase */
  #aml-openclaw .slide-content h3.md-slide-h3 {
    font-family: 'Roboto', 'Google Sans', sans-serif;
    font-size: 17px;
    font-weight: 600;
    color: var(--blue-dark);
    margin: 8px 0 12px;
    text-transform: none;
    letter-spacing: 0;
  }

  #aml-openclaw .slide-content .week-table {
    width: 100%;
    margin-top: 4px;
    margin-bottom: 20px;
  }

  /* Day One / Markdown: ![](url) — custom schemes (e.g. dayone-moment://) may not load in a browser */
  #aml-openclaw .slide-content img.md-inline-image {
    display: block;
    max-width: 100%;
    height: auto;
    margin: 12px auto;
    border-radius: 6px;
    border: 1px solid var(--gray-200);
  }

  /* Fenced code block whose body is <svg>…</svg> — rendered inline (not <pre><code>) */
  #aml-openclaw .slide-content .md-slide-svg {
    margin: 12px 0 20px;
    max-width: 100%;
  }
  #aml-openclaw .slide-content .md-slide-svg svg {
    display: block;
    width: 100%;
    height: auto;
    max-width: 100%;
  }

  #aml-openclaw ul {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  /* Block + absolute bullet: avoids flex making each <strong> / text run a separate flex item     (which caused independent word-wrapping in narrow frames). */
  #aml-openclaw ul li {
    display: block;
    position: relative;
    padding-left: 20px;
    font-size: 15px;
    line-height: 1.55;
    color: var(--gray-800);
  }

  #aml-openclaw ul li::before {
    content: '';
    position: absolute;
    left: 0;
    top: 7px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--blue);
  }

  #aml-openclaw ul li strong {
    color: var(--gray-900);
    font-weight: 600;
  }

  /* ── CODE BLOCKS (PPTX) ── */
  #aml-openclaw pre {
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    padding: 14px 16px;
    margin-top: 16px;
    overflow-x: auto;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 13px;
    line-height: 1.55;
    color: var(--gray-900);
    white-space: pre;
  }

  #aml-openclaw pre code { font-family: inherit; }

  /*
   * Per-line <span>s for scan-reveal must be block + white-space: pre — inline spans inside
   * <code> can collapse leading spaces / indent in the HTML slide view even when <pre> has pre.
   */
  #aml-openclaw .md-java-reveal-pre code {
    display: block;
    white-space: pre;
    tab-size: 4;
  }

  /* ── Java: optional corner “reveal” mode (hover Y reveals lines; source stays in DOM) ── */
  #aml-openclaw .md-java-reveal {
    position: relative;
    margin-top: 16px;
  }

  #aml-openclaw .md-java-reveal .md-java-reveal-pre {
    margin-top: 0;
    position: relative;
    padding-bottom: 32px;
    padding-right: 36px;
  }

  #aml-openclaw .md-java-reveal-arm {
    position: absolute;
    right: 12px;
    bottom: 12px;
    z-index: 4;
    width: 24px;
    height: 24px;
    padding: 0;
    border: 1px solid var(--gray-300);
    border-radius: 4px;
    background: var(--white);
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
    color: var(--gray-600);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
  }

  #aml-openclaw .md-java-reveal-arm:hover {
    background: var(--gray-50);
    color: var(--gray-900);
  }

  #aml-openclaw .md-java-reveal-line {
    display: block;
    white-space: pre;
    transition: opacity 0.12s ease, color 0.1s ease;
  }

  #aml-openclaw .md-java-reveal.is-scan-active .md-java-reveal-line:not(.is-line-revealed) {
    opacity: 0;
  }

  /* Line under pointer while scanning: burnt orange; reverts when pointer leaves that line */
  #aml-openclaw .md-java-reveal.is-scan-active .md-java-reveal-line.is-line-hot {
    color: #b8430e;
    opacity: 1;
  }

  /* ── SPEAKER NOTES (emoji bottom-left; full-width yellow bar under emoji on hover) ── */
  #aml-openclaw .speaker-notes {
    position: relative;
    width: 100%;
    box-sizing: border-box;
    background: transparent;
    border: none;
    padding: 0 0 20px;
    display: block;
  }

  #aml-openclaw .notes-anchor-row {
    display: flex;
    justify-content: flex-start;
    align-items: flex-end;
    padding: 12px 56px 6px;
    box-sizing: border-box;
  }

  #aml-openclaw .notes-hover-wrap {
    display: inline-block;
  }

  #aml-openclaw .notes-trigger {
    font-size: 1.75rem;
    line-height: 1;
    cursor: help;
    user-select: none;
    opacity: 0.82;
    transition: opacity 0.15s ease, transform 0.15s ease;
  }

  #aml-openclaw .speaker-notes:hover .notes-trigger,
  #aml-openclaw .speaker-notes:focus-within .notes-trigger {
    opacity: 1;
    transform: scale(1.07);
  }

  #aml-openclaw .notes-popover {
    position: absolute;
    left: 0;
    right: 0;
    width: 100%;
    box-sizing: border-box;
    top: 100%;
    margin-top: 0;
    background: var(--yellow-light);
    border: 1px solid #fdd663;
    border-radius: 8px;
    padding: 14px 56px 16px;
    box-shadow: 0 6px 20px rgba(60, 64, 67, 0.18);
    z-index: 100;
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
    transition: opacity 0.14s ease, visibility 0.14s;
  }

  #aml-openclaw .speaker-notes:hover .notes-popover,
  #aml-openclaw .speaker-notes:focus-within .notes-popover {
    opacity: 1;
    visibility: visible;
    pointer-events: auto;
  }

  #aml-openclaw .notes-content {
    font-size: 13px;
    color: #5a4a00;
    line-height: 1.55;
  }

  #aml-openclaw .notes-content ul {
    gap: 6px;
  }

  #aml-openclaw .notes-content ul li {
    display: block;
    position: relative;
    padding-left: 14px;
    font-size: 13px;
    color: #5a4a00;
  }

  #aml-openclaw .notes-content ul li::before {
    position: absolute;
    left: 0;
    top: 6px;
    background: #8a6914;
    width: 5px;
    height: 5px;
  }

  /* ── LESSON BLOCKS ── */
  #aml-openclaw .lesson-block {
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    padding: 20px 24px;
    margin-bottom: 16px;
  }

  #aml-openclaw .lesson-block:last-of-type { margin-bottom: 0; }

  #aml-openclaw .lesson-title {
    font-family: 'Google Sans', 'Roboto', sans-serif;
    font-size: 14px;
    font-weight: 700;
    color: var(--blue-dark);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  #aml-openclaw .lesson-badge {
    background: var(--blue);
    color: white;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  /* ── LINK GRID ── */
  #aml-openclaw .link-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 20px;
  }

  #aml-openclaw .link-card {
    background: var(--blue-light);
    border: 1px solid #c5d9f8;
    border-radius: 6px;
    padding: 14px 16px;
  }

  #aml-openclaw .link-card-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--blue-dark);
    margin-bottom: 4px;
  }

  #aml-openclaw .link-card-note {
    font-size: 11px;
    color: var(--gray-600);
    margin: -2px 0 6px;
    line-height: 1.4;
  }

  #aml-openclaw .link-card-url {
    font-size: 11px;
    color: var(--blue);
    word-break: break-all;
    text-decoration: none;
  }

  #aml-openclaw .link-card-url:hover { text-decoration: underline; }

  #aml-openclaw .link-card.secondary {
    background: var(--gray-50);
    border-color: var(--gray-200);
  }

  #aml-openclaw .link-card.secondary .link-card-name { color: var(--gray-800); }
  #aml-openclaw .link-card.secondary .link-card-url { color: var(--blue); }

  /* ── HIGHLIGHT BOXES ── */
  #aml-openclaw .callout {
    border-radius: 6px;
    padding: 16px 20px;
    margin: 16px 0;
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }

  #aml-openclaw .callout-blue { background: var(--blue-light); border-left: 4px solid var(--blue); }
  #aml-openclaw .callout-green { background: var(--teal-light); border-left: 4px solid var(--teal); }
  #aml-openclaw .callout-red { background: var(--red-light); border-left: 4px solid var(--red); }

  #aml-openclaw .callout-text { font-size: 14px; line-height: 1.55; color: var(--gray-800); }
  #aml-openclaw .callout-text strong { color: var(--gray-900); }

  /* ── WEEK TABLE ── */
  #aml-openclaw .week-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
  }

  #aml-openclaw .week-table th {
    background: var(--blue);
    color: white;
    font-size: 13px;
    font-weight: 600;
    text-align: left;
    padding: 10px 16px;
    font-family: 'Google Sans', 'Roboto', sans-serif;
  }

  /* One full-width title row (PPT-style pipe tables), then column labels */
  #aml-openclaw .week-table th.week-table-section-title {
    text-align: center;
    font-size: 14px;
    font-weight: 600;
  }

  /* Column labels under section title (tbody row): no blue bar — centered, bold */
  #aml-openclaw .week-table td.week-table-col-head {
    text-align: center;
    font-weight: 700;
    background: var(--white);
    color: var(--gray-900);
    border-bottom: 2px solid var(--gray-200);
  }

  /* Round top corners: single header row */
  #aml-openclaw .week-table thead tr:only-child th:first-child { border-radius: 6px 0 0 0; }
  #aml-openclaw .week-table thead tr:only-child th:last-child { border-radius: 0 6px 0 0; }
  #aml-openclaw .week-table thead tr:only-child th:only-child { border-radius: 6px 6px 0 0; }

  /* PPT-style: only thead row is section title; round bottom of blue bar where tbody begins */
  #aml-openclaw .week-table thead tr:only-child th.week-table-section-title {
    border-radius: 6px 6px 0 0;
  }

  #aml-openclaw .week-table td {
    padding: 10px 16px;
    font-size: 14px;
    border-bottom: 1px solid var(--gray-200);
    line-height: 1.5;
    color: var(--gray-800);
  }

  #aml-openclaw .week-table td strong { color: var(--gray-900); }

  /* Inline `code` in table cells (default: monospace chip; table may also be .week-table--mono) */
  #aml-openclaw .week-table code.md-inline-code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 0.92em;
    background: var(--gray-100);
    padding: 0.12em 0.4em;
    border-radius: 4px;
    color: var(--gray-900);
  }

  /* thead: th sets Google Sans — force monospace for inline code on blue bar */
  #aml-openclaw .week-table th code.md-inline-code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    background: rgba(255, 255, 255, 0.22);
    color: #fff;
  }

  /* Whole-table fixed width: put <!-- m2s:tt --> on the line above the pipe table */
  #aml-openclaw .week-table.week-table--mono,
  #aml-openclaw .week-table.week-table--mono th,
  #aml-openclaw .week-table.week-table--mono td {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 13px;
  }

  #aml-openclaw .week-table tr:last-child td { border-bottom: none; }
  #aml-openclaw .week-table tr:nth-child(even) td { background: var(--gray-50); }

  /* Progressive reveal: fenced pipe rows authored as "- | … | … |" (hover once to show; stays visible) */
  #aml-openclaw tr.week-table-row-reveal:not(.is-revealed) {
    opacity: 0;
    transition: opacity 0.2s ease;
  }
  #aml-openclaw tr.week-table-row-reveal.is-revealed {
    opacity: 1;
  }

  /* SNIPPET + OUTPUT: blockquote lines (>) after OUTPUT — monospace, no bullets; hover-once reveal */
  #aml-openclaw .md-output-reveal-block {
    margin: 0.35em 0 0.75em;
  }
  #aml-openclaw .md-output-reveal-line {
    font-family: ui-monospace, "Cascadia Code", "Source Code Pro", Menlo, Consolas, "Roboto Mono", monospace;
    font-size: 13px;
    line-height: 1.55;
    color: var(--gray-900);
    opacity: 0;
    transition: opacity 0.2s ease;
    margin: 0.15em 0;
    padding: 0;
  }
  #aml-openclaw .md-output-reveal-line.is-revealed {
    opacity: 1;
  }

  #aml-openclaw .md-slide-gt-block {
    margin: 0.5em 0;
    padding: 0 0 0 14px;
    border-left: 3px solid var(--gray-300);
    color: var(--gray-800);
  }
  #aml-openclaw .md-slide-gt-block p {
    margin: 0.35em 0;
    font-size: 14px;
    line-height: 1.5;
  }

  /* ── GLOSSARY ── */
  #aml-openclaw .glossary-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-top: 8px;
  }

  #aml-openclaw .glossary-item {
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    padding: 14px 16px;
  }

  #aml-openclaw .glossary-term {
    font-size: 13px;
    font-weight: 700;
    color: var(--blue-dark);
    margin-bottom: 4px;
  }

  #aml-openclaw .glossary-def {
    font-size: 13px;
    color: var(--gray-600);
    line-height: 1.5;
  }

  /* ── Q&A SLIDE ── */
  #aml-openclaw .slide-qa {
    background: linear-gradient(135deg, #f8f9fa 0%, #e8f0fe 100%);
    padding: 60px 56px;
    min-height: 220px;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }

  #aml-openclaw .slide-qa h2 {
    font-family: 'Jua', 'Google Sans Display', 'Roboto', sans-serif;
    font-size: 44px;
    font-weight: 700;
    color: var(--blue-dark);
    margin-bottom: 20px;
  }

  #aml-openclaw .slide-qa ul { gap: 8px; }

  #aml-openclaw .slide-qa ul li { font-size: 16px; color: var(--gray-700); }

  /* ── FOOTER ── */
  #aml-openclaw .deck-footer {
    text-align: center;
    font-size: 12px;
    color: var(--gray-400);
    margin-top: 8px;
    font-style: italic;
  }

  /* Divider between major sections */
  #aml-openclaw .section-divider {
    text-align: center;
    font-size: 11px;
    color: var(--gray-400);
    text-transform: uppercase;
    letter-spacing: 2px;
    font-weight: 500;
    padding: 4px 0;
  }

  /* Moodle embed: keep the activity/post from growing infinitely tall */
  .aml-viewport {
    max-height: 600px;
    overflow: auto;
    -webkit-overflow-scrolling: touch;
    border: 1px solid rgba(154,160,166,0.35);
    border-radius: 10px;
    background: transparent;
  }

  .aml-viewport #aml-openclaw {
    padding: 16px 16px 24px;
  }

</style>

<div class="aml-viewport">
<div id="aml-openclaw">
  <div class="deck">
"""


CSS_AND_WRAPPER_SUFFIX = """  </div>
</div>
 </div>
<script>
(function () {
  var root = document.getElementById("aml-openclaw");
  if (!root) return;
  function reveal(el) {
    el.classList.add("is-revealed");
  }
  root.querySelectorAll("tr.week-table-row-reveal").forEach(function (tr) {
    tr.addEventListener("mouseenter", function () { reveal(tr); }, { once: true });
    tr.addEventListener("focusin", function () { reveal(tr); }, { once: true });
  });
  root.querySelectorAll(".md-output-reveal-line").forEach(function (el) {
    el.addEventListener("mouseenter", function () { reveal(el); }, { once: true });
    el.addEventListener("focusin", function () { reveal(el); }, { once: true });
  });

  /* Java fences: corner toggles scan mode; pointer must visit top of block before line reveal runs
     (avoids one mousemove from bottom revealing everything after click). */
  root.querySelectorAll(".md-java-reveal").forEach(function (block) {
    var pre = block.querySelector(".md-java-reveal-pre");
    var btn = block.querySelector(".md-java-reveal-arm");
    if (!pre || !btn) return;
    var lines = pre.querySelectorAll(".md-java-reveal-line");
    var maxReveal = 0;
    var armed = false;

    function clearHot() {
      lines.forEach(function (ln) {
        ln.classList.remove("is-line-hot");
      });
    }

    function topGateY() {
      if (lines.length) return lines[0].getBoundingClientRect().top + 8;
      return pre.getBoundingClientRect().top + 8;
    }

    function applyReveal(y) {
      if (!block.classList.contains("is-scan-active")) {
        clearHot();
        return;
      }
      if (!armed) {
        if (y <= topGateY()) {
          armed = true;
          maxReveal = 0;
          lines.forEach(function (ln) {
            ln.classList.remove("is-line-revealed", "is-line-hot");
          });
        }
        clearHot();
        return;
      }
      var n = 0;
      lines.forEach(function (span, i) {
        var r = span.getBoundingClientRect();
        if (y >= r.top + 1) n = i + 1;
      });
      maxReveal = Math.max(maxReveal, n);
      lines.forEach(function (span, i) {
        span.classList.toggle("is-line-revealed", i < maxReveal);
      });
      var hot = -1;
      for (var hi = 0; hi < maxReveal; hi++) {
        var hr = lines[hi].getBoundingClientRect();
        if (y >= hr.top && y <= hr.bottom) {
          hot = hi;
          break;
        }
      }
      lines.forEach(function (span, i) {
        span.classList.toggle("is-line-hot", i === hot);
      });
    }

    function setScanActive(on) {
      if (on) {
        block.classList.add("is-scan-active");
        maxReveal = 0;
        armed = false;
        lines.forEach(function (ln) {
          ln.classList.remove("is-line-revealed", "is-line-hot");
        });
        btn.setAttribute("aria-pressed", "true");
      } else {
        block.classList.remove("is-scan-active");
        maxReveal = 0;
        armed = false;
        lines.forEach(function (ln) {
          ln.classList.remove("is-line-revealed", "is-line-hot");
        });
        btn.setAttribute("aria-pressed", "false");
      }
    }

    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (block.classList.contains("is-scan-active")) setScanActive(false);
      else setScanActive(true);
    });

    pre.addEventListener("mousemove", function (e) {
      if (!block.classList.contains("is-scan-active")) return;
      applyReveal(e.clientY);
    });

    pre.addEventListener(
      "touchmove",
      function (e) {
        if (!block.classList.contains("is-scan-active") || !e.touches || !e.touches[0]) return;
        applyReveal(e.touches[0].clientY);
      },
      { passive: true }
    );

    pre.addEventListener("mouseleave", function () {
      clearHot();
    });
  });
})();
</script>
"""


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


# Day One / CommonMark single-character escapes in prose and code (often stacked).
_MD_SINGLE_CHAR_ESC = re.compile(r"\\([\\`*_{}[\]()#+\-.!|<>])")


def _unescape_dayone_commonmark_escapes(text: str) -> str:
    """Strip Day One backslash escapes; repeat until stable (handles \\\\… layers)."""
    prev = None
    s = text
    while prev != s:
        prev = s
        s = _MD_SINGLE_CHAR_ESC.sub(r"\1", s)
    return s


def jua_heading_html(plain: str) -> str:
    """
    Slide titles use Jua; ampersands are unreliable there — show '+' instead.
    Escape exactly once for HTML (never pre-encode as &amp; in plain text).
    """
    plain = _unescape_dayone_commonmark_escapes(plain)
    return _esc(plain.replace("&", "+"))


def title_slide_h1_html(cleaned_plain: str) -> str:
    """Title slide h1: Jua, '+' for '&', optional line break at first ' + '."""
    jua = _unescape_dayone_commonmark_escapes(cleaned_plain).replace("&", "+")
    if " + " in jua:
        left, right = jua.split(" + ", 1)
        return _esc(left) + "<br>+ " + _esc(right)
    return _esc(jua)


_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RE_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

# Optional cap for ``dayone-moment://`` → data-URI embed (default ~12 MiB).
_MAX_DAYONE_EMBED_BYTES = int(os.environ.get("MARKDOWN2SLIDES_MAX_EMBED_BYTES", "12000000"))


def _dayone_sqlite_path() -> Optional[Path]:
    """``DAYONE_SQLITE`` or default macOS Day One 2 database path."""
    env = os.environ.get("DAYONE_SQLITE")
    if env:
        p = Path(env).expanduser()
        return p if p.is_file() else None
    default = Path.home() / (
        "Library/Group Containers/5U8NS4GX82.dayoneapp2/Data/Documents/DayOne.sqlite"
    )
    return default if default.is_file() else None


def _mime_for_photo_ext(ext: str) -> str:
    e = ext.lower().strip().lstrip(".")
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "heic": "image/heic",
        "heif": "image/heif",
    }.get(e, "image/png")


def _try_dayone_moment_data_uri(moment_url: str) -> Optional[str]:
    """
    Resolve ``dayone-moment://<ZATTACHMENT.ZIDENTIFIER>`` to a ``data:image/…;base64,…`` URI
    by reading ``DayOnePhotos/<ZMD5>.<ZTYPE>`` next to ``DayOne.sqlite``. Returns ``None``
    if the DB or file is missing (HTML keeps the original ``src``).
    """
    u = moment_url.strip()
    if not u.lower().startswith("dayone-moment:"):
        return None
    ident = u.split("://", 1)[-1].strip().strip("/")
    if not ident:
        return None
    db_path = _dayone_sqlite_path()
    if not db_path:
        return None
    photos_dir = db_path.parent / "DayOnePhotos"
    uri = db_path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute(
                "SELECT ZMD5, ZTYPE FROM ZATTACHMENT WHERE ZIDENTIFIER = ? COLLATE NOCASE",
                (ident,),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    md5, ztype = str(row[0]), (row[1] or "png")
    ext = str(ztype).lower().strip().lstrip(".") or "png"
    candidates = [ext, "png", "jpg", "jpeg", "gif", "webp", "heic"]
    seen: set[str] = set()
    ordered = [x for x in candidates if x not in seen and not seen.add(x)]
    path: Optional[Path] = None
    used_ext = ext
    for e in ordered:
        p = photos_dir / f"{md5}.{e}"
        if p.is_file():
            path = p
            used_ext = e
            break
    if path is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > _MAX_DAYONE_EMBED_BYTES:
        return None
    mime = _mime_for_photo_ext(used_ext)
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"
_RE_INLINE_CODE_SPAN = re.compile(r"`([^`]+)`")
_RE_M2S_TT_COMMENT = re.compile(r"^<!--\s*m2s:tt\s*-->\s*$", re.IGNORECASE)


def _line_is_m2s_tt_comment(line: str) -> bool:
    """Whole-table monospace directive for the next pipe table (fenced or unfenced)."""
    s = _unescape_dayone_commonmark_escapes(line.strip())
    return bool(_RE_M2S_TT_COMMENT.match(s))


def _m2s_tt_before_table(lines: List[str], table_line_idx: int) -> bool:
    """True if the nearest non-blank line above ``table_line_idx`` is ``<!-- m2s:tt -->``."""
    j = table_line_idx - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    if j < 0:
        return False
    return _line_is_m2s_tt_comment(lines[j])


def _md_inline_links_bold_italic_fragment(text: str) -> str:
    """**bold**, *italic*, [label](url), ``![alt](url)`` images — fragment must not contain `` ` `` code spans."""
    if not text:
        return ""
    # Images first: ``![](url)`` must not be parsed as ``[](url)`` (empty link). Use placeholders
    # so ``<img>`` is not passed through ``_esc`` (which would escape markup).
    img_html: List[str] = []

    def img_sub(m: re.Match[str]) -> str:
        alt = _esc(m.group(1))
        raw_url = m.group(2).strip()
        # Day One: resolve ``dayone-moment://…`` via local SQLite + ``DayOnePhotos``, embed as data URI.
        data_uri = _try_dayone_moment_data_uri(raw_url)
        if data_uri is not None:
            src = data_uri
        else:
            src = _esc(raw_url)
        img_html.append(
            f'<img class="md-inline-image" alt="{alt}" src="{src}" loading="lazy" />'
        )
        return f"@@IMG{len(img_html) - 1}@@"

    text = _RE_MD_IMAGE.sub(img_sub, text)
    # Tokenize links, escape the rest, then splice <a> tags (single HTML escape pass).
    s = _esc(_RE_MD_LINK.sub(lambda m: f"@@LINK{m.start()}@@", text))
    links: List[Tuple[str, str, str]] = []
    for m in _RE_MD_LINK.finditer(text):
        token = f"@@LINK{m.start()}@@"
        links.append((token, _esc(m.group(1)), _esc(m.group(2))))
    for token, label, url in links:
        s = s.replace(token, f'<a href="{url}" target="_blank">{label}</a>')

    # Bold then italics (non-nested best-effort)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    for i, fragment in enumerate(img_html):
        s = s.replace(f"@@IMG{i}@@", fragment)
    return s


def md_inline_to_html(text: str) -> str:
    """Small inline markdown subset: **bold**, *italic*, [label](url), `` `inline code` ``, ``![alt](url)`` images."""
    text = _unescape_dayone_commonmark_escapes(text)
    out: List[str] = []
    pos = 0
    for m in _RE_INLINE_CODE_SPAN.finditer(text):
        if m.start() > pos:
            out.append(_md_inline_links_bold_italic_fragment(text[pos : m.start()]))
        out.append(f'<code class="md-inline-code">{_esc(m.group(1))}</code>')
        pos = m.end()
    if pos < len(text):
        out.append(_md_inline_links_bold_italic_fragment(text[pos:]))
    return "".join(out)


def _is_slide_section_break_line(line: str) -> bool:
    """Horizontal rules that separate slides: `---` or `___` (and longer underscore HR)."""
    s = line.strip()
    if s == "---":
        return True
    if len(s) >= 3 and s.replace("_", "") == "":
        return True
    return False


def split_sections(lines: List[str]) -> List[List[str]]:
    sections: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if _is_slide_section_break_line(line):
            if current:
                sections.append(current)
                current = []
            continue
        current.append(line.rstrip("\n"))
    if current:
        sections.append(current)
    return sections


def parse_front_matter(sections: List[List[str]]) -> Tuple[Optional[dict], List[List[str]]]:
    """
    If the markdown uses a '---' separated front matter block (not YAML proper),
    it will appear as the second section (first is the H1 chunk).
    """
    if not sections:
        return None, sections

    # Front matter in this format is the first section that contains `key: value` lines
    # and no `##` headings.
    first_kv_section_idx = None
    for i, sec in enumerate(sections):
        if any(l.startswith("## ") for l in sec):
            break
        if any(re.match(r"^[a-zA-Z0-9_]+:\s*.*$", l.strip()) for l in sec):
            first_kv_section_idx = i
            break
    if first_kv_section_idx is None:
        return None, sections

    fm: dict = {}
    for raw in sections[first_kv_section_idx]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Markdown often escapes underscores in plain text blocks.
        # Accept keys like `session\_focus` and normalize to `session_focus`.
        line = line.replace("\\_", "_")
        m = re.match(r"^([a-zA-Z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        fm[k] = v
    remaining = [sec for j, sec in enumerate(sections) if j != first_kv_section_idx]
    return fm, remaining


def extract_h1(lines: List[str]) -> Tuple[Optional[str], List[str]]:
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            rest = lines[:i] + lines[i + 1 :]
            return title, rest
    return None, lines


@dataclass
class BodyBlock:
    kind: str  # bullets | text | code
    lines: List[str]
    fence_lang: str = ""


@dataclass
class Slide:
    title: str
    body_lines: List[str]
    speaker_notes_lines: List[str]
    body_blocks: Optional[List[BodyBlock]] = None


def parse_slides(sections: List[List[str]]) -> List[Slide]:
    slides: List[Slide] = []
    for sec in sections:
        heading = None
        body: List[str] = []
        notes: List[str] = []
        in_notes = False
        for line in sec:
            if line.startswith("## "):
                heading = line[3:].strip()
                continue
            if line.startswith("### Speaker notes"):
                in_notes = True
                continue
            if in_notes:
                if line.strip():
                    notes.append(line)
            else:
                if line.strip():
                    body.append(line)
        if heading:
            slides.append(Slide(title=heading, body_lines=body, speaker_notes_lines=notes))
    return slides


def normalize_title(t: str) -> str:
    """Plain-text slide title only — do not insert HTML entities here."""
    s = t.strip()
    if s.lower().startswith("slide:"):
        s = s.split(":", 1)[1].strip()
    s = s.replace("’", "'")
    # One-off polish patterns matching the existing deck style.
    s = re.sub(r"\(tone\)\s*$", "— Tone & Mindset", s, flags=re.IGNORECASE)
    return s


def render_ul_from_bullets(lines: List[str]) -> str:
    items = []
    for line in lines:
        m = re.match(r"^\s*-\s+(.*)$", line)
        if m:
            items.append(f"        <li>{md_inline_to_html(m.group(1).strip())}</li>")
    if not items:
        return ""
    return "<ul>\n" + "\n".join(items) + "\n      </ul>"


def render_output_reveal_blockquotes(content_lines: List[str]) -> str:
    """
    After **OUTPUT** (with prior **SNIPPET** on the slide): lines from ``> text`` markdown.
    Monospace, no list markers; each line reveals on first hover/focus and stays visible.
    """
    items: List[str] = []
    for raw in content_lines:
        items.append(
            '        <div class="md-output-reveal-line" tabindex="0">'
            f"{md_inline_to_html(raw.strip())}</div>"
        )
    if not items:
        return ""
    return (
        '      <div class="md-output-reveal-block">\n'
        + "\n".join(items)
        + "\n      </div>"
    )


def render_plain_slide_blockquotes(content_lines: List[str]) -> str:
    """Non-reveal ``>`` lines on a slide: simple blockquote styling."""
    paras = [ln.strip() for ln in content_lines]
    if not paras:
        return ""
    inner = "\n".join(f"        <p>{md_inline_to_html(p)}</p>" for p in paras)
    return f'      <blockquote class="md-slide-gt-block">\n{inner}\n      </blockquote>'


def render_ul_from_text_lines(lines: List[str]) -> str:
    items = [f"        <li>{md_inline_to_html(l.strip())}</li>" for l in lines if l.strip()]
    if not items:
        return ""
    return "<ul>\n" + "\n".join(items) + "\n      </ul>"


def _unescape_dayone_table_line(line: str) -> str:
    """Pipe-table parsing (same unescape as prose)."""
    return _unescape_dayone_commonmark_escapes(line)


def _is_table_separator_line(line: str) -> bool:
    """GFM pipe-table separator row: | --- | --- |"""
    s = _unescape_dayone_table_line(line).strip()
    if not s.startswith("|"):
        return False
    inner = s.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    cells = _split_inner_pipe_row_cells(inner)
    if not cells or any(not c for c in cells):
        return False
    for c in cells:
        if not re.match(r"^:?-{2,}:?$", c):
            return False
    return True


def _split_inner_pipe_row_cells(inner: str) -> List[str]:
    """
    Split on ``|`` only **outside** single-backtick `` `...` `` spans.

    Naive ``inner.split('|')`` breaks when a cell uses inline code and the closing
    `` ` `` was stripped by storage (or never written): the column ``|`` can be
    parsed as ending the code span. Keeping ``|`` inside an odd backtick run
    preserves the cell text for ``md_inline_to_html``.
    """
    cells: List[str] = []
    cur: List[str] = []
    in_code = False
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if ch == "`":
            in_code = not in_code
            cur.append(ch)
            i += 1
        elif ch == "|" and not in_code:
            cells.append("".join(cur).strip())
            cur = []
            i += 1
        else:
            cur.append(ch)
            i += 1
    cells.append("".join(cur).strip())
    return cells


def _split_pipe_row(line: str) -> List[str]:
    s = _unescape_dayone_table_line(line).strip()
    if not s.startswith("|"):
        return []
    s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return _split_inner_pipe_row_cells(s)


def _strip_reveal_row_prefix(line: str) -> Tuple[str, bool]:
    """
    Rows authored as ``- | col | col |`` (progressive reveal in HTML) return
    (``| col | col |``, True). Otherwise (line, False).
    """
    s = _unescape_dayone_table_line(line).strip()
    m = re.match(r"^-\s*(\|.*)$", s)
    if m:
        return m.group(1).strip(), True
    return s, False


def _line_looks_like_gfm_pipe_row(line: str) -> bool:
    """Header/body pipe row, optionally with reveal prefix ``- ``."""
    s = _unescape_dayone_table_line(line).strip()
    if s.startswith("|"):
        return True
    return bool(re.match(r"^-\s*\|", s))


def preprocess_promote_m2s_tt_fence(md_text: str) -> str:
    """
    Day One often stores ``<!-- m2s:tt -->`` as **its own** tiny `` ``` / line / ``` `` block
    (with backslash-escaped ``<`` / ``-``), *before* fragmented one-row-per-fence pipe
    tables. Replace that 3-line fence with a single canonical ``<!-- m2s:tt -->`` line so
    ``preprocess_merge_adjacent_table_fences`` and ``_m2s_tt_before_table`` can attach
    monospace to the merged table.
    """
    if not md_text:
        return md_text
    had_trailing_nl = md_text[-1] in "\n\r"
    lines = md_text.splitlines(keepends=False)
    out: List[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if (
            i + 2 < n
            and lines[i].strip().startswith("```")
            and lines[i + 2].strip() == "```"
        ):
            body = lines[i + 1]
            if _line_is_m2s_tt_comment(body):
                out.append("<!-- m2s:tt -->")
                i += 3
                continue
        out.append(lines[i])
        i += 1
    result = "\n".join(out)
    if had_trailing_nl:
        result += "\n"
    return result


def preprocess_merge_adjacent_table_fences(md_text: str) -> str:
    """
    Day One sometimes exports one pipe row per tiny fenced block:

 ```
 | header |
      ```
      ```
      | --- |
      ```

    Merge consecutive ``` / single |...| line / ``` groups into one fence so the
    renderer can treat the body as a single GFM table. Blank lines between groups are
    skipped. Does not alter normal fences or raw (unfenced) pipe tables.
    """
    lines = md_text.splitlines(keepends=False)
    out: List[str] = []
    i = 0
    n = len(lines)

    def _skip_blanks(j: int) -> int:
        while j < n and not lines[j].strip():
            j += 1
        return j

    while i < n:
        if (
            i + 2 < n
            and lines[i].strip() == "```"
            and _line_looks_like_gfm_pipe_row(lines[i + 1])
            and lines[i + 2].strip() == "```"
        ):
            merged: List[str] = ["```", lines[i + 1]]
            i = i + 3
            while True:
                j = _skip_blanks(i)
                if (
                    j + 2 < n
                    and lines[j].strip() == "```"
                    and _line_looks_like_gfm_pipe_row(lines[j + 1])
                    and lines[j + 2].strip() == "```"
                ):
                    merged.append(lines[j + 1])
                    i = j + 3
                else:
                    i = j
                    break
            merged.append("```")
            out.extend(merged)
            continue
        out.append(lines[i])
        i += 1
    result = "\n".join(out)
    if md_text.endswith("\n"):
        result += "\n"
    return result


def _fence_fragment_line_kind(line: str) -> str:
    """
    Classify a one-line ``` body when merging Day One's ```/line/``` fragments.

    table: GFM pipe row | code: source / formula / markup one-liner
    other: prose or list-in-fence — never merged with neighbors
    """
    s = _unescape_dayone_commonmark_escapes(line).strip()
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
    # Assignments: bot = …, stuff[3] = 10, ray.length = 1
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
    # Split method signature continuation (no `(` on this line): "Comparable item)"
    if "(" not in s and re.match(
        r"^\s*[A-Za-z_][\w<>[\].,\s]*\)\s*$",
        s,
    ):
        return "code"
    # Trace / math lines: 0 + 7 = 7 / 2 = 3
    if re.match(r"^\s*\d", s) and re.search(r"[=+\-*/]", s):
        return "code"
    # SVG / inline XML
    if "<" in s and ">" in s:
        return "code"
    return "other"


def _minimal_lang_triplet_at(
    lines: List[str], idx: int, n: int
) -> Optional[Tuple[int, str, str, str, str]]:
    """
    If lines[idx:idx+3] is open / one line / close (`` ``` `` or `` ```lang ``), return
    (index_after_triplet, raw_open_line, content_line, raw_close_line, lang_key).
    lang_key is lowercased fence info ("" for bare). Keep in sync with dayone_crud.py.
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


def preprocess_consolidate_fragment_fences(md_text: str) -> str:
    """
    **Always** run in generate_html: merge Day One's repeated ``` / one line / ``` chunks
    into one multi-line fence so agents cannot "forget" this step. Same kind only:
    **table** (|…) or **code** (see _fence_fragment_line_kind). Bare `` ``` `` or
    language-tagged openers (e.g. `` ```java ``); neighbors merge only when lang_key matches.
    """
    if not md_text:
        return md_text
    had_trailing_nl = md_text[-1] in "\n\r"
    lines = md_text.splitlines(keepends=False)
    out: List[str] = []
    i = 0
    n = len(lines)

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
        kind0 = _fence_fragment_line_kind(first)
        i = i_after
        if kind0 in ("table", "code"):
            trips: List[Tuple[str, str]] = [(raw_open0, first)]
            while True:
                j = skip_blanks(i)
                t2 = _minimal_lang_triplet_at(lines, j, n)
                if t2 is None:
                    i = j
                    break
                _i2, raw_open_k, nxt_mid, _rc, nxt_lang = t2
                if nxt_lang != lang_key0:
                    i = j
                    break
                if _fence_fragment_line_kind(nxt_mid) != kind0:
                    i = j
                    break
                trips.append((raw_open_k, nxt_mid))
                i = t2[0]
            if kind0 == "code" and len(trips) > 1:
                # Each fragment encodes nesting via spaces before `` ``` ``; merged body
                # lines were column-0 — apply per-fragment column so render does not
                # lose structure. Strip opener indent so _html_for_code_block_lines does
                # not add fence_open_leading twice (body lines already carry full indent).
                contents = [
                    _apply_fence_open_indent([m], _fence_open_leading_columns(ro))[0]
                    for ro, m in trips
                ]
                raw_open_emit = raw_open0.lstrip()
            else:
                contents = [m for _, m in trips]
                raw_open_emit = raw_open0
        else:
            i = skip_blanks(i)
            contents = [first]
            raw_open_emit = raw_open0
        out.append(raw_open_emit)
        out.extend(contents)
        out.append(raw_close0)
        continue

    result = "\n".join(out)
    if had_trailing_nl:
        result += "\n"
    return result


def _try_parse_gfm_table_from_code_lines(
    code_lines: List[str],
) -> Optional[Tuple[Optional[List[str]], List[List[str]], List[bool], bool]]:
    """
    If fenced (or pasted) code body is a GFM pipe table, return
    (header_cells_or_None, body_rows, reveal_row_flags, monospace_directive).

    **Monospace:** if the first non-empty line in the fence is ``<!-- m2s:tt -->``, it is
    stripped and ``monospace_directive`` is True (same effect as the comment above the
    opening `` ``` ``).

    **Standard GFM:** header row, then ``| --- |`` separator, then body rows.

    **Headerless:** when there is no column heading row — first row is only the separator
    line (e.g. one-column ``| --- |``), then data rows. Example::

        | --- |
        | @ @ @ - @ |
        | - - @ - - |

    ``header_cells`` is ``None`` in that case; HTML is rendered with ``<tbody>`` only.

    Rows may be authored as ``- | cell | cell |`` to hide the row until the learner
    hovers once (see ``.week-table-row-reveal``). Blank lines inside the block are ignored.
    """
    norm: List[str] = []
    mono_inside = False
    for ln in code_lines:
        s = _unescape_dayone_table_line(ln).strip()
        if not s:
            continue
        if not norm and _line_is_m2s_tt_comment(s):
            mono_inside = True
            continue
        norm.append(s)
    if len(norm) < 2:
        return None

    # Headerless: first row is separator-only (column spec), not headings; body follows.
    if (
        _is_table_separator_line(norm[0])
        and norm[1].startswith("|")
        and not _is_table_separator_line(norm[1])
    ):
        body_rows: List[List[str]] = []
        reveal_flags: List[bool] = []
        for row_line in norm[1:]:
            stripped, is_reveal = _strip_reveal_row_prefix(row_line)
            if not stripped.startswith("|"):
                return None
            body_rows.append(_split_pipe_row(stripped))
            reveal_flags.append(is_reveal)
        return None, body_rows, reveal_flags, mono_inside

    if (
        not norm[0].startswith("|")
        or _is_table_separator_line(norm[0])
        or not _is_table_separator_line(norm[1])
    ):
        return None
    header = _split_pipe_row(norm[0])
    if not header:
        return None
    body_rows2: List[List[str]] = []
    reveal_flags2: List[bool] = []
    for row_line in norm[2:]:
        stripped, is_reveal = _strip_reveal_row_prefix(row_line)
        if not stripped.startswith("|"):
            return None
        body_rows2.append(_split_pipe_row(stripped))
        reveal_flags2.append(is_reveal)
    return header, body_rows2, reveal_flags2, mono_inside


def _is_probably_java_code(code: str) -> bool:
    """Heuristic for bare ``` fences: Java vs Python / traces / pipe-ish text."""
    t = code.strip()
    if not t:
        return False
    first = ""
    for ln in code.splitlines():
        s = ln.strip()
        if not s:
            continue
        if _line_is_m2s_tt_comment(s):
            continue
        first = s
        break
    if first.startswith("|"):
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


def _should_wrap_java_line_reveal(code: str, fence_lang: str) -> bool:
    """Pipe-table fences are excluded earlier; this targets Java-like ``` bodies only."""
    fl = fence_lang.strip().lower()
    if fl == "java":
        return True
    if fl not in ("", "text"):
        return False
    return _is_probably_java_code(code)


def _google_java_format_exe() -> Optional[str]:
    return os.environ.get("GOOGLE_JAVA_FORMAT") or shutil.which("google-java-format")


# Synthetic class name matches ``dayone-crud`` ``format-java-fences`` (unwrap logic).
_FMT_M2S_WRAP = "__SlideFenceFmt__"


def _close_unbalanced_braces_m2s(snippet: str) -> str:
    """
    If ``{`` outnumber ``}``, append closing ``}`` so slide snippets missing a final brace
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


def _m2s_java_aosp_from_env() -> bool:
    return os.environ.get("MARKDOWN2SLIDES_JAVA_AOSP", "").lower() in (
        "1",
        "true",
        "yes",
    )


def _m2s_java_format_with_tool(src: str, *, aosp: bool) -> Optional[str]:
    exe = _google_java_format_exe()
    if not exe:
        return None
    tmp = Path(tempfile.mkdtemp(prefix="m2s-gjf-"))
    path = tmp / "Fmt.java"
    try:
        path.write_text(src, encoding="utf-8")
        cmd = [exe, str(path)]
        if aosp:
            cmd.append("--aosp")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return None
        out = r.stdout
        return out if out.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _m2s_wrap_java_snippet_for_tool(code: str) -> Tuple[str, bool]:
    t = code.strip()
    if re.match(r"^\s*(public\s+)?(class|interface|enum|record)\s+\w+", t):
        return code, False
    return f"class {_FMT_M2S_WRAP} {{\n{t}\n}}\n", True


def _m2s_unwrap_fmt_class(formatted: str) -> str:
    lines = formatted.splitlines()
    if len(lines) < 3:
        return formatted
    if _FMT_M2S_WRAP not in lines[0]:
        return formatted
    if lines[-1].strip() != "}":
        return formatted
    inner = "\n".join(lines[1:-1])
    return textwrap.dedent(inner).rstrip("\n")


def _m2s_unwrap_static_initializer(formatted: str) -> str:
    if _FMT_M2S_WRAP not in formatted:
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


def _try_google_java_format(code: str) -> Optional[str]:
    """
    Same strategy as ``dayone-crud`` ``format_java_fence_body``: format raw, then synthetic
    class, then ``static { … }`` wrapper. Optional ``MARKDOWN2SLIDES_JAVA_AOSP=1`` for 4-space.
    """
    if not _google_java_format_exe():
        return None
    aosp = _m2s_java_aosp_from_env()
    work = _close_unbalanced_braces_m2s(code)
    out = _m2s_java_format_with_tool(work, aosp=aosp)
    if out is not None and out.strip():
        return out.rstrip("\n")
    wrapped, did = _m2s_wrap_java_snippet_for_tool(work)
    if did:
        out2 = _m2s_java_format_with_tool(wrapped, aosp=aosp)
        if out2 is not None and out2.strip():
            return _m2s_unwrap_fmt_class(out2).rstrip("\n")
    t = work.strip()
    if t:
        wrapped_static = (
            f"class {_FMT_M2S_WRAP} {{\n"
            f"  static {{\n{t}\n"
            f"  }}\n"
            f"}}\n"
        )
        out3 = _m2s_java_format_with_tool(wrapped_static, aosp=aosp)
        if out3 is not None and out3.strip():
            return _m2s_unwrap_static_initializer(out3).rstrip("\n")
    return None


def _indent_java_by_braces(src: str) -> str:
    """Stdlib fallback when ``google-java-format`` is unavailable (classroom slides)."""
    lines = [ln.replace("\t", "    ").rstrip() for ln in src.splitlines()]
    s = textwrap.dedent("\n".join(lines)).strip()
    lines = s.splitlines()
    out: List[str] = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if stripped.startswith("}"):
            depth = max(0, depth - 1)
        out.append("  " * depth + stripped)
        open_braces = stripped.count("{") - stripped.count("}")
        if open_braces > 0:
            depth += open_braces
        elif open_braces < 0:
            depth = max(0, depth + open_braces)
    return "\n".join(out)


def _format_java_block_for_slide(code: str, fence_lang: str) -> str:
    """
    Normalize Java layout for HTML so Day One / PPTX flat columns still read as indented
    code. Prefer ``google-java-format`` when installed; else brace-aware indent.
    """
    fl = (fence_lang or "").strip().lower()
    if fl != "java" and not (
        fl in ("", "text") and _is_probably_java_code(code)
    ):
        return code
    gjf = _try_google_java_format(code)
    if gjf is not None:
        return gjf
    return _indent_java_by_braces(code)


def _fence_open_leading_columns(open_line: str) -> int:
    """
    Column offset of a fenced block: spaces/tabs before `` ``` `` on the **opening** line.
    PPTX / Day One fragmented fences often encode nesting this way while the inner line starts
    at column 0; without applying this offset, HTML loses Java indentation.
    """
    return len(open_line) - len(open_line.lstrip())


def _apply_fence_open_indent(code_lines: List[str], cols: int) -> List[str]:
    """Prepend ``cols`` spaces to each non-empty body line (table path skips this)."""
    if cols <= 0:
        return code_lines
    pad = " " * cols
    out: List[str] = []
    for ln in code_lines:
        if ln.strip() == "":
            out.append(ln)
        else:
            out.append(pad + ln)
    return out


def _html_java_reveal_block(code: str) -> str:
    """Corner control + per-line spans; full source remains in DOM for copy/paste."""
    lines = code.split("\n")
    parts: List[str] = []
    for i, ln in enumerate(lines):
        suf = "\n" if i < len(lines) - 1 else ""
        parts.append(f'<span class="md-java-reveal-line">{_esc(ln)}{suf}</span>')
    inner = "".join(parts)
    return f"""      <div class="md-java-reveal">
        <pre class="md-java-reveal-pre"><code>{inner}</code></pre>
        <button type="button" class="md-java-reveal-arm" aria-pressed="false" aria-label="Reveal mode: move the pointer to the top of the code, then down to show each line. Click again to exit." title="Reveal mode — move to top of code first, then hover down (click again to exit)">⋮</button>
      </div>"""


_RE_SVG_BLOCK = re.compile(r"<\s*svg\b[\s\S]*?</\s*svg\s*>", re.IGNORECASE)
_RE_SVG_SELF_CLOSE = re.compile(r"<\s*svg\b[^>]*/\s*>", re.IGNORECASE)


def _try_extract_svg_embed_html(code: str) -> Optional[str]:
    """
    If a fenced block contains an SVG document (``<svg`` … ``</svg>`` or self-closing),
    return a wrapper div with raw SVG markup (not escaped). Otherwise ``None``.
    """
    if not re.search(r"<\s*svg\b", code, re.IGNORECASE):
        return None
    m = _RE_SVG_BLOCK.search(code)
    if m:
        return _html_svg_embed(m.group(0).strip())
    m2 = _RE_SVG_SELF_CLOSE.search(code)
    if m2:
        return _html_svg_embed(m2.group(0).strip())
    return None


def _html_svg_embed(svg_markup: str) -> str:
    return f"""      <div class="md-slide-svg">
{svg_markup}
      </div>"""


def _html_for_code_block_lines(
    code_lines: List[str],
    fence_lang: str = "",
    *,
    snippet_reveal: bool = False,
    fence_open_leading: int = 0,
    table_monospace: bool = False,
) -> str:
    """`<pre><code>` for real code; `week-table` HTML when the body is a pipe table."""
    parsed = _try_parse_gfm_table_from_code_lines(code_lines)
    if parsed is not None:
        h, rows, reveal, mono_inside = parsed
        return _render_gfm_table(
            h,
            rows,
            reveal_rows=reveal,
            monospace=(table_monospace or mono_inside),
        )
    body_lines = _apply_fence_open_indent(code_lines, fence_open_leading)
    raw = "\n".join(body_lines).rstrip("\n")
    code = _unescape_dayone_commonmark_escapes(raw)
    if not code.strip():
        return ""
    svg_html = _try_extract_svg_embed_html(code)
    if svg_html is not None:
        return svg_html
    code = _format_java_block_for_slide(code, fence_lang)
    if snippet_reveal or _should_wrap_java_line_reveal(code, fence_lang):
        return _html_java_reveal_block(code)
    return f"      <pre><code>{_esc(code)}</code></pre>"


def _section_title_from_table_header(header: List[str]) -> Optional[str]:
    """
    PPT-export pattern: first row is one label over the grid, e.g.
    | frequently used methods |  |
    Only one cell has text (any column); remaining cells are empty.
    """
    if len(header) < 2:
        return None
    non_empty = [i for i, c in enumerate(header) if c.strip()]
    if len(non_empty) != 1:
        return None
    return header[non_empty[0]].strip()


def _tr_week_table(
    cells: List[str],
    *,
    ncols: int,
    reveal: bool,
    td_class: str = "",
) -> str:
    cells = list(cells[:ncols])
    while len(cells) < ncols:
        cells.append("")
    cls = "week-table-row-reveal" if reveal else ""
    tds = []
    for c in cells:
        extra = f' class="{td_class}"' if td_class else ""
        tds.append(f"<td{extra}>{md_inline_to_html(c)}</td>")
    if cls:
        row_attr = f' class="{cls}" tabindex="0"'
    else:
        row_attr = ""
    return f"<tr{row_attr}>{''.join(tds)}</tr>"


def _render_gfm_table(
    header: Optional[List[str]],
    rows: List[List[str]],
    *,
    reveal_rows: Optional[List[bool]] = None,
    monospace: bool = False,
) -> str:
    rev = reveal_rows or [False] * len(rows)
    tbl_cls = "week-table week-table--mono" if monospace else "week-table"

    if header is None:
        if not rows:
            return ""
        ncols = max(len(r) for r in rows)
        body_lines: List[str] = []
        for i, r in enumerate(rows):
            reveal = rev[i] if i < len(rev) else False
            body_lines.append(_tr_week_table(list(r), ncols=ncols, reveal=reveal))
        tbody = "\n        ".join(body_lines)
        return f"""      <table class="{tbl_cls}">
        <tbody>
        {tbody}
        </tbody>
      </table>"""

    ncols = len(header)
    section_title = _section_title_from_table_header(header)

    if section_title and rows:
        sub = list(rows[0][:ncols])
        while len(sub) < ncols:
            sub.append("")
        data_rows = rows[1:]
        rev_sub = rev[0] if rev else False
        rev_data = rev[1:] if len(rev) > 1 else [False] * len(data_rows)
        while len(rev_data) < len(data_rows):
            rev_data.append(False)
        title_th = (
            f'<th colspan="{ncols}" class="week-table-section-title">'
            f"{md_inline_to_html(section_title)}</th>"
        )
        thead = f"""        <thead>
          <tr>{title_th}</tr>
        </thead>"""
        body_lines: List[str] = [
            _tr_week_table(sub, ncols=ncols, reveal=rev_sub, td_class="week-table-col-head")
        ]
        for i, r in enumerate(data_rows):
            body_lines.append(
                _tr_week_table(list(r), ncols=ncols, reveal=rev_data[i])
            )
        tbody_inner = "\n        ".join(body_lines)
        return f"""      <table class="{tbl_cls}">
{thead}
        <tbody>
        {tbody_inner}
        </tbody>
      </table>"""

    ths = "".join(f"<th>{md_inline_to_html(h)}</th>" for h in header)
    body_rows: List[str] = []
    for i, r in enumerate(rows):
        reveal = rev[i] if i < len(rev) else False
        body_rows.append(_tr_week_table(list(r), ncols=ncols, reveal=reveal))
    tbody = "\n        ".join(body_rows)
    return f"""      <table class="{tbl_cls}">
        <thead>
          <tr>{ths}</tr>
        </thead>
        <tbody>
        {tbody}
        </tbody>
      </table>"""


def render_mixed_markdown_lines(lines: List[str]) -> str:
    """
    Slide body from Day One / PPT-export style markdown: ### headings, fenced ``` code
    (pipe tables inside fences render as week-table HTML), raw GFM pipe tables, '- '
    bullets, and plain paragraphs (e.g. SNIPPET / OUTPUT).

    When a slide contains **SNIPPET** (caps) before **OUTPUT** (caps), the first run of
    **blockquote** lines (each line starts with ``>``) after **OUTPUT** uses progressive
    reveal and monospace (see ``render_output_reveal_blockquotes``).

    Fenced code **after SNIPPET and before OUTPUT** uses the same corner + hover scan reveal
    as Java fences elsewhere (see ``_html_for_code_block_lines`` / ``md-java-reveal``).
    """
    parts: List[str] = []
    i = 0
    n = len(lines)
    seen_snippet_label = False
    seen_output_label = False
    next_output_reveal = False
    while i < n:
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue

        if _line_is_m2s_tt_comment(line):
            i += 1
            continue

        if line.startswith("### ") and not line.startswith("####"):
            title = line[4:].strip()
            parts.append(
                f'      <h3 class="md-slide-h3">{md_inline_to_html(title)}</h3>'
            )
            i += 1
            continue

        if line.strip().startswith("```"):
            table_mono = _m2s_tt_before_table(lines, i)
            opener = line.strip()
            fence_lang = opener[3:].strip().lower() if len(opener) > 3 else ""
            fence_open_leading = _fence_open_leading_columns(line)
            i += 1
            code_lines: List[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            snippet_reveal = seen_snippet_label and not seen_output_label
            parts.append(
                _html_for_code_block_lines(
                    code_lines,
                    fence_lang=fence_lang,
                    snippet_reveal=snippet_reveal,
                    fence_open_leading=fence_open_leading,
                    table_monospace=table_mono,
                )
            )
            continue

        # Headerless pipe table: ``| --- |`` (or ``| :---: |``) defines columns only; no <thead>.
        if (
            line.strip().startswith("|")
            and _is_table_separator_line(line)
            and i + 1 < n
            and _unescape_dayone_table_line(lines[i + 1]).strip().startswith("|")
            and not _is_table_separator_line(lines[i + 1])
        ):
            mono_tbl = _m2s_tt_before_table(lines, i)
            i += 1
            body_rows_h: List[List[str]] = []
            while i < n:
                rl = lines[i].strip()
                if not rl.startswith("|"):
                    break
                body_rows_h.append(_split_pipe_row(lines[i]))
                i += 1
            parts.append(_render_gfm_table(None, body_rows_h, monospace=mono_tbl))
            continue

        if (
            line.strip().startswith("|")
            and i + 1 < n
            and _is_table_separator_line(lines[i + 1])
        ):
            mono_tbl = _m2s_tt_before_table(lines, i)
            header = _split_pipe_row(line)
            i += 2
            body_rows: List[List[str]] = []
            while i < n:
                rl = lines[i].strip()
                if not rl.startswith("|"):
                    break
                body_rows.append(_split_pipe_row(lines[i]))
                i += 1
            if header:
                parts.append(_render_gfm_table(header, body_rows, monospace=mono_tbl))
            continue

        if re.match(r"^\s*>", line):
            gt_contents: List[str] = []
            while i < n and re.match(r"^\s*>", lines[i]):
                mgt = re.match(r"^\s*>\s?(.*)$", lines[i])
                gt_contents.append(mgt.group(1) if mgt else "")
                i += 1
            use_reveal = next_output_reveal
            next_output_reveal = False
            bq = (
                render_output_reveal_blockquotes(gt_contents)
                if use_reveal
                else render_plain_slide_blockquotes(gt_contents)
            )
            if bq:
                parts.append(bq)
            continue

        if re.match(r"^\s*-\s+", line):
            bullets: List[str] = []
            while i < n and re.match(r"^\s*-\s+", lines[i]):
                bullets.append(lines[i])
                i += 1
            ul = render_ul_from_bullets(bullets)
            if ul:
                parts.append(f"      {ul}")
            continue

        text_lines: List[str] = []
        while i < n:
            l2 = lines[i]
            if not l2.strip():
                break
            if l2.startswith("### ") and not l2.startswith("####"):
                break
            if l2.strip().startswith("```"):
                break
            if (
                l2.strip().startswith("|")
                and i + 1 < n
                and _is_table_separator_line(lines[i + 1])
            ):
                break
            if (
                l2.strip().startswith("|")
                and _is_table_separator_line(lines[i])
                and i + 1 < n
                and _unescape_dayone_table_line(lines[i + 1]).strip().startswith("|")
                and not _is_table_separator_line(lines[i + 1])
            ):
                break
            if re.match(r"^\s*-\s+", l2):
                break
            if re.match(r"^\s*>", l2):
                break
            text_lines.append(l2.strip())
            i += 1
        if text_lines:
            merged = " ".join(text_lines)
            extra = ""
            if merged in ("SNIPPET", "OUTPUT"):
                extra = ' style="font-size:12px;font-weight:600;color:var(--gray-600);text-transform:uppercase;letter-spacing:0.06em;margin:14px 0 6px;"'
            if merged == "SNIPPET":
                seen_snippet_label = True
                seen_output_label = False
            elif merged == "OUTPUT":
                if seen_snippet_label:
                    next_output_reveal = True
                seen_output_label = True
            parts.append(f"      <p{extra}>{md_inline_to_html(merged)}</p>")
        else:
            i += 1
        continue

    return "\n".join(parts)


def _render_body_blocks(blocks: List[BodyBlock]) -> str:
    parts: List[str] = []
    for b in blocks:
        if b.kind == "code":
            parts.append(
                _html_for_code_block_lines(b.lines, fence_lang=b.fence_lang)
            )
        elif b.kind == "text":
            text = " ".join(l.strip() for l in b.lines if l.strip()).strip()
            if text:
                parts.append(
                    "      <p style=\"font-size:15px;line-height:1.6;color:var(--gray-800);\">"
                    + md_inline_to_html(text)
                    + "</p>"
                )
        else:
            ul = render_ul_from_text_lines(b.lines)
            if ul:
                parts.append(f"      {ul}")
    return "\n".join(p for p in parts if p)


def render_speaker_notes(notes_lines: List[str], label: str = "📝 Notes") -> str:
    if not notes_lines:
        return ""

    # Bullets in source become line breaks in the popover (hover / focus-visible).
    cleaned: List[str] = []
    for l in notes_lines:
        m = re.match(r"^\s*-\s+(.*)$", l)
        cleaned.append(m.group(1).strip() if m else l.strip())
    cleaned = [c for c in cleaned if c]

    text = "<br>\n        ".join(md_inline_to_html(c) for c in cleaned)
    # Visible hint: memo emoji only; full label in tooltip + a11y. Popover hides when pointer leaves.
    t_attr = _esc(label)
    return f"""    <div class="speaker-notes">
      <div class="notes-anchor-row">
        <div class="notes-hover-wrap">
          <span class="notes-trigger" role="img" tabindex="0" title="{t_attr}" aria-label="{t_attr}">\N{MEMO}</span>
        </div>
      </div>
      <div class="notes-popover" role="tooltip">
        <div class="notes-content">{text}</div>
      </div>
    </div>"""


# **Name** optional (subtitle) — tail with URL(s). Dash may be – — or -.
_LINK_CARD_HEAD = re.compile(
    r"^\*\*([^*]+)\*\*(?:\s*\(([^)]*)\))?\s*[\u2013\u2014\-]\s*(.+)$"
)


def _link_card_visible_url(url: str, max_len: int = 52) -> str:
    """Shorter anchor text; full URL stays in href + title. Avoids long paths in narrow cards."""
    try:
        p = urlparse(url)
    except Exception:
        raw = url.replace("https://", "").replace("http://", "")
        return raw if len(raw) <= max_len else raw[: max_len - 1] + "\u2026"
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (p.path or "").rstrip("/")
    query = f"?{p.query}" if p.query else ""
    frag = f"#{p.fragment}" if p.fragment else ""
    rest = f"{path}{query}{frag}" if path or query or frag else ""
    if not host:
        raw = url.replace("https://", "").replace("http://", "")
        return raw if len(raw) <= max_len else raw[: max_len - 1] + "\u2026"
    compact = f"{host}{rest}" if rest else host
    if len(compact) <= max_len:
        return compact
    return host


def _extract_links_from_bullets(lines: List[str]) -> List[Tuple[str, str, str]]:
    """
    Parse link bullets into (display_name, url, optional_note).

    Supports:
      - **Cursor** — https://cursor.com
      - **Google Antigravity** (getting started / official codelab) — https://...
      - **OpenAI Codex (IDE)** — overview: https://... · ...
    Uses the first URL in the tail. Optional (note) after **name** must not contain ')'
    mid-string (rare); use — immediately after **name** when there is no subtitle.
    """
    out: List[Tuple[str, str, str]] = []
    for line in lines:
        m = re.match(r"^\s*-\s+(.*)$", line)
        if not m:
            continue
        text = m.group(1).strip()
        name = ""
        note = ""
        tail = text

        hm = _LINK_CARD_HEAD.match(text)
        if hm:
            name = hm.group(1).strip()
            note = (hm.group(2) or "").strip()
            tail = hm.group(3).strip()
        else:
            # Legacy: **Label** — rest (no parenthetical between label and dash)
            bold_m = re.match(r"^\*\*([^*]+)\*\*\s*[\u2013\u2014\-]\s*(.*)$", text)
            if bold_m:
                name = bold_m.group(1).strip()
                tail = bold_m.group(2).strip()

        url_m = re.search(r"(https?://\S+)", tail)
        if not url_m:
            continue
        url = url_m.group(1).rstrip(").,;]")
        if not name:
            pre = tail[: url_m.start()].strip()
            pre = re.sub(r"^\*\*|\*\*$", "", pre).strip()
            pre = re.sub(r"\s*[\u2013\u2014\-]\s*$", "", pre).strip()
            name = pre if pre else _link_card_visible_url(url)
        out.append((name, url, note))
    return out


def render_link_grid(cards: List[Tuple[str, str, str]], secondary: bool) -> str:
    if not cards:
        return ""
    cls = "link-card secondary" if secondary else "link-card"
    parts = ['      <div class="link-grid">']
    for name, url, note in cards:
        name_u = _unescape_dayone_commonmark_escapes(name)
        note_u = _unescape_dayone_commonmark_escapes(note) if note else ""
        note_el = (
            f'\n          <div class="link-card-note">{_esc(note_u)}</div>'
            if note
            else ""
        )
        vis = _link_card_visible_url(url)
        parts.append(f"""        <div class="{cls}">
          <div class="link-card-name">{_esc(name_u)}</div>{note_el}
          <a class="link-card-url" href="{_esc(url)}" target="_blank" title="{_esc(url)}">{_esc(vis)}</a>
        </div>""")
    parts.append("      </div>")
    return "\n".join(parts)


def render_week_table_from_bullets(lines: List[str]) -> str:
    rows: List[Tuple[str, str]] = []
    for line in lines:
        # Accept both:
        # - **Wednesday (In Class)**: text
        # - **Wednesday (In Class):** text   (colon inside the bold)
        m = re.match(r"^\s*-\s+\*\*([^*]+?)\*\*\s*:\s*(.*)$", line)
        if not m:
            m = re.match(r"^\s*-\s+\*\*([^*]+?):\*\*\s*(.*)$", line)
        if not m:
            continue
        when_label = m.group(1).strip().rstrip(":").strip()
        when = md_inline_to_html(f"**{when_label}**")
        what = md_inline_to_html(m.group(2).strip())
        rows.append((when, what))

    if not rows:
        return ""

    trs = "\n".join(
        f"""          <tr>
            <td>{when}</td>
            <td>{what}</td>
          </tr>"""
        for when, what in rows
    )
    return f"""      <table class="week-table">
        <thead>
          <tr>
            <th>When</th>
            <th>What</th>
          </tr>
        </thead>
        <tbody>
{trs}
        </tbody>
      </table>"""


def render_glossary_from_bullets(lines: List[str]) -> str:
    items: List[Tuple[str, str]] = []
    for line in lines:
        m = re.match(r"^\s*-\s+\*\*([^*]+)\*\*:\s*(.*)$", line)
        if not m:
            continue
        term = m.group(1).strip()
        definition = m.group(2).strip()
        items.append((term, definition))

    if not items:
        return ""

    parts = ['      <div class="glossary-grid">']
    for term, definition in items:
        parts.append(f"""        <div class="glossary-item">
          <div class="glossary-term">{_esc(_unescape_dayone_commonmark_escapes(term))}</div>
          <div class="glossary-def">{md_inline_to_html(definition)}</div>
        </div>""")
    parts.append("      </div>")
    return "\n".join(parts)


def render_lessons(body_lines: List[str]) -> Optional[str]:
    lesson_headers = []
    for i, line in enumerate(body_lines):
        m = re.match(r"^\*\*Lesson\s+(\d+)\s+[—-]\s+(.+)\*\*\s*$", line.strip())
        if m:
            lesson_headers.append((i, int(m.group(1)), m.group(2).strip()))
    if not lesson_headers:
        return None

    # Partition per lesson
    lesson_blocks = []
    for idx, (start_i, num, title) in enumerate(lesson_headers):
        end_i = lesson_headers[idx + 1][0] if idx + 1 < len(lesson_headers) else len(body_lines)
        lesson_body = [l for l in body_lines[start_i + 1 : end_i] if l.strip()]
        ul = render_ul_from_bullets(lesson_body)
        lesson_blocks.append(
            f"""      <div class="lesson-block">
        <div class="lesson-title"><span class="lesson-badge">Lesson {num}</span> {_esc(_unescape_dayone_commonmark_escapes(title))}</div>
        {ul}
      </div>"""
        )
    return "\n\n".join(lesson_blocks)


def render_slide_body(slide: Slide) -> Tuple[str, str]:
    """
    Returns (body_html, wrapper_class) where wrapper_class is 'slide-content' or 'slide-qa'.
    """
    title_norm = normalize_title(slide.title)
    title_h2 = jua_heading_html(title_norm)
    title_plain = title_norm.lower()

    if slide.body_blocks:
        blocks_html = _render_body_blocks(slide.body_blocks)
        body = f"""      <h2>{title_h2}</h2>
{blocks_html}"""
        return body, "slide-content"

    # Q&A special slide
    if "q&a" in title_plain or title_plain.strip() == "q & a" or title_plain.strip() == "q and a":
        ul = render_ul_from_bullets(slide.body_lines)
        body = f"""      <h2>{jua_heading_html("Q & A")}</h2>
      {ul}"""
        return body, "slide-qa"

    # Glossary
    if "glossary" in title_plain:
        grid = render_glossary_from_bullets(slide.body_lines)
        body = f"""      <h2>{title_h2}</h2>
{grid}"""
        return body, "slide-content"

    # "This week" table
    if "this week" in title_plain:
        table = render_week_table_from_bullets(slide.body_lines)
        if table:
            body = f"""      <h2>{title_h2}</h2>
{table}"""
            return body, "slide-content"

    # Lessons blocks
    lessons = render_lessons(slide.body_lines)
    if lessons is not None:
        intro = ""
        if "lessons from" in title_plain:
            intro = '<p style="font-size:13px;color:var(--gray-600);margin-bottom:20px;font-style:italic;">Experience-based observations — not product verdicts</p>\n\n'
        body = f"""      <h2>{title_h2}</h2>
      {intro}{lessons}"""
        return body, "slide-content"

    # Link grids (two groups)
    if "shortlist" in title_plain or "ide" in title_plain:
        # Attempt to find the two bullet groups split by a marker line.
        # We'll treat lines between a "Class-shortlist" marker and "Other common options" as primary.
        primary_lines: List[str] = []
        secondary_lines: List[str] = []
        cur = "main"
        for l in slide.body_lines:
            if "Class-shortlist" in l or "Class Shortlist" in l:
                cur = "primary"
                continue
            if "Other common options" in l or "Other Common Options" in l:
                cur = "secondary"
                continue
            if cur == "primary":
                primary_lines.append(l)
            elif cur == "secondary":
                secondary_lines.append(l)

        primary_cards = _extract_links_from_bullets(primary_lines)
        secondary_cards = _extract_links_from_bullets(secondary_lines)

        if primary_cards or secondary_cards:
            # Also keep any leading bullets before the marker as a normal ul.
            lead_bullets = []
            for l in slide.body_lines:
                if "Class-shortlist" in l or "Class Shortlist" in l:
                    break
                lead_bullets.append(l)
            ul = render_ul_from_bullets(lead_bullets)

            body_parts = [f"      <h2>{title_h2}</h2>", f"      {ul}" if ul else ""]
            body_parts.append('      <h3 style="margin-top:24px;">Class Shortlist — Pick One</h3>')
            body_parts.append('      <p style="font-size:12px;color:var(--gray-600);margin-bottom:12px;">Verify school policy and pricing yourself.</p>')
            body_parts.append(render_link_grid(primary_cards, secondary=False))
            if secondary_cards:
                body_parts.append('      <h3 style="margin-top:20px;">Other Common Options</h3>')
                body_parts.append(render_link_grid(secondary_cards, secondary=True))
            return "\n".join(p for p in body_parts if p), "slide-content"

    # Default: mixed markdown (tables, ###, code fences, bullets) — bullet-only was dropping pipe tables
    mixed = render_mixed_markdown_lines(slide.body_lines)
    body = f"""      <h2>{title_h2}</h2>
{mixed}"""
    return body, "slide-content"


def render_title_slide(h1: str, fm: Optional[dict], slide_num: int, total: int) -> str:
    # Light "deck-title" cleanup:
    # - remove parenthetical suffixes like "(slide-ready notes)"
    # - normalize curly quotes
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", h1.strip())
    cleaned = cleaned.replace("’", "'").replace("“", '"').replace("”", '"')
    # Use a mild title-casing for readability while preserving acronyms like AML.
    def _tc(word: str) -> str:
        if word.isupper() and len(word) <= 5:
            return word
        if word.lower() in {"and", "or", "the", "a", "an", "of", "to", "with", "vs"}:
            return word.lower()
        return word[:1].upper() + word[1:]

    words = re.split(r"(\s+)", cleaned)
    cleaned = "".join(_tc(w) if not w.isspace() else w for w in words)
    cleaned = cleaned.replace("What's", "What's").replace("What'S", "What's")

    title_html = title_slide_h1_html(cleaned)

    session_focus = fm.get("session_focus") if fm else None
    subtitle = ""
    if session_focus:
        subtitle = f'<p class="subtitle">Session Focus: {md_inline_to_html(session_focus)}</p>'

    # Canonical labels for this particular deck pattern.
    meta_rows: List[Tuple[str, str]] = []
    if fm:
        mapping = [
            ("Wednesday (In Class)", fm.get("wednesday_class", "")),
            ("Friday (Due)", fm.get("friday_class", "")),
            ("Instructor Prep Due", fm.get("instructor_prep_due", "")),
            ("Related Event", fm.get("related_events", "")),
        ]
        for label, value in mapping:
            if value:
                meta_rows.append((label, value))

    meta_html = ""
    if meta_rows:
        meta_items = "\n".join(
            f"""        <div class="meta-item">
          <span class="meta-label">{_esc(label)}</span>
          <span class="meta-value">{md_inline_to_html(value)}</span>
        </div>"""
            for label, value in meta_rows
        )
        meta_html = f"""      <div class="meta-grid">
{meta_items}
      </div>"""

    return f"""  <!-- SLIDE {slide_num}: TITLE -->
  <div class="slide">
    <div class="slide-title">
      <div class="slide-num">{slide_num} / {total}</div>
      <h1>{title_html}</h1>
      {subtitle}
{meta_html}
    </div>
  </div>"""


def render_slide(slide: Slide, slide_num: int, total: int) -> str:
    body_html, cls = render_slide_body(slide)
    notes_label = "📝 Notes"
    if any("instructor-only" in l.lower() for l in slide.speaker_notes_lines):
        notes_label = "📝 Notes (Instructor-Only)"
    notes_html = render_speaker_notes(slide.speaker_notes_lines, label=notes_label)

    inner = f"""    <div class="{cls}">
      <div class="slide-num">{slide_num} / {total}</div>
{body_html}
    </div>"""

    return f"""  <div class="slide">
{inner}
{notes_html if notes_html else ""}
  </div>"""

def _render_deck(
    *,
    deck_title_h1: Optional[str],
    fm: Optional[dict],
    slides: List[Slide],
    footer_source_line: Optional[str] = None,
) -> str:
    deck_parts: List[str] = [CSS_AND_WRAPPER_PREFIX]
    total = (1 + len(slides)) if deck_title_h1 else len(slides)

    slide_num = 1
    if deck_title_h1:
        deck_parts.append(render_title_slide(deck_title_h1, fm, slide_num=slide_num, total=total))
        slide_num += 1

    for s in slides:
        deck_parts.append(render_slide(s, slide_num=slide_num, total=total))
        slide_num += 1

    if footer_source_line:
        deck_parts.append(f'  <div class="deck-footer">{md_inline_to_html(footer_source_line)}</div>')

    deck_parts.append(CSS_AND_WRAPPER_SUFFIX)
    return "\n\n".join(deck_parts).rstrip() + "\n"

def generate_html(md_text: str) -> str:
    # Heal Day One / editor-split ``` fences before any slide parsing (not optional).
    md_text = preprocess_consolidate_fragment_fences(md_text)
    md_text = preprocess_promote_m2s_tt_fence(md_text)
    md_text = preprocess_merge_adjacent_table_fences(md_text)
    raw_lines = md_text.splitlines()
    h1, remaining_lines = extract_h1(raw_lines)
    sections = split_sections(remaining_lines)
    fm, sections_wo_fm = parse_front_matter(sections)
    slides = parse_slides(sections_wo_fm)

    # Footer: use last italic source line if present
    src_line = None
    for l in reversed(raw_lines):
        if l.strip().startswith("*Source:") and l.strip().endswith("*"):
            src_line = l.strip().strip("*").strip()
            break
    return _render_deck(
        deck_title_h1=h1,
        fm=fm,
        slides=slides,
        footer_source_line=src_line,
    )


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


def _pptx_slide_paths(z: zipfile.ZipFile) -> List[str]:
    # Slides live at ppt/slides/slide1.xml, slide2.xml, ...
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
    """
    Returns (max_font_sz, any_monospace).
    Font size is in OOXML attribute 'sz' (1/100 pt) when present.
    """
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


def _pptx_extract_paragraphs(slide_xml: str) -> List[Tuple[str, int, bool]]:
    """Extract (text, max_font_sz, any_monospace) per paragraph, preserving a:br as newlines."""
    try:
        root = ET.fromstring(slide_xml)
    except ET.ParseError:
        return []

    paragraphs: List[Tuple[str, int, bool]] = []
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
            paragraphs.append((text, max_sz, any_mono))
    return paragraphs


def slides_from_pptx(pptx_path: Path) -> Tuple[Optional[str], List[Slide]]:
    """
    Read a .pptx (zip) and create Slide objects.

    Heuristic mapping:
    - first non-empty paragraph on a slide -> slide title
    - remaining paragraphs -> bullets
    """
    deck_title = pptx_path.stem.replace("_", " ").strip() or None
    slides: List[Slide] = []

    with zipfile.ZipFile(pptx_path, "r") as z:
        for slide_path in _pptx_slide_paths(z):
            try:
                xml_bytes = z.read(slide_path)
            except KeyError:
                continue
            paras = _pptx_extract_paragraphs(xml_bytes.decode("utf-8", errors="replace"))
            paras = [(t, sz, mono) for (t, sz, mono) in paras if not _pptx_is_footer_line(t)]
            if not paras:
                continue

            title_idx = max(range(len(paras)), key=lambda i: paras[i][1]) if paras else 0
            title = paras[title_idx][0].strip()
            body_paras = [p for i, p in enumerate(paras) if i != title_idx]

            blocks: List[BodyBlock] = []
            cur_code: List[str] = []
            cur_text: List[str] = []

            def flush_text() -> None:
                nonlocal cur_text
                if not cur_text:
                    return
                if len(cur_text) == 1:
                    blocks.append(BodyBlock(kind="text", lines=cur_text))
                else:
                    blocks.append(BodyBlock(kind="bullets", lines=cur_text))
                cur_text = []

            def flush_code() -> None:
                nonlocal cur_code
                if not cur_code:
                    return
                blocks.append(BodyBlock(kind="code", lines=cur_code))
                cur_code = []

            for (t, _sz, mono) in body_paras:
                text = t.strip()
                if not text:
                    continue
                looks_code = bool(
                    re.search(r"[{}();]|^\s*(public|private|class|def|for|while|if)\b", text)
                )
                if mono or ("\n" in text) or looks_code:
                    flush_text()
                    cur_code.extend(text.splitlines())
                else:
                    flush_code()
                    cur_text.append(text)

            flush_code()
            flush_text()

            slides.append(Slide(title=title, body_lines=[], speaker_notes_lines=[], body_blocks=blocks))

    # If we couldn't extract anything, still produce an empty deck wrapper.
    return deck_title, slides


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate Moodle-ready OpenClaw slide HTML from a Markdown or PPTX source."
    )
    ap.add_argument("source_path", type=Path, help="Path to slide-ready .md or .pptx source file.")
    ap.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Output HTML path. Defaults to <source basename>.moodle.html next to the source.",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    src_path: Path = args.source_path.expanduser()
    out_path: Path = args.out or src_path.with_suffix(".moodle.html")

    suffix = src_path.suffix.lower()
    if suffix == ".pptx":
        h1, slides = slides_from_pptx(src_path)
        html_out = _render_deck(deck_title_h1=h1, fm=None, slides=slides, footer_source_line=None)
    else:
        # Default to markdown workflow
        md_text = src_path.read_text(encoding="utf-8")
        html_out = generate_html(md_text)

    out_path.write_text(html_out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

