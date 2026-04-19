#!/usr/bin/env python3
"""
Read a Day One entry's Markdown body straight from DayOne.sqlite (ZMARKDOWNTEXT).

This does not read DayOnePhotos or any attachment blobs, so a missing file on disk
cannot break extraction. Embedded references (e.g. dayone-moment://…) stay in the
text for later resolution via MCP or a manual export.

Requires: Python 3.9+ (stdlib only).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


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


def list_entries(conn: sqlite3.Connection, journal: str, limit: int) -> None:
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
    for uuid, preview in rows:
        line = preview.replace("\n", " ").strip()
        print(f"{uuid}\t{line}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument(
        "-d",
        "--database",
        type=Path,
        required=True,
        help="Path to DayOne.sqlite",
    )
    ap.add_argument(
        "-j",
        "--journal",
        help="Journal name (ZJOURNAL.ZNAME). Strongly recommended when selecting by UUID.",
    )
    ap.add_argument(
        "-e",
        "--entry-id",
        help="Entry id (ZUUID), same as dayone://view?entryId=…",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write markdown to this file (default: stdout)",
    )
    ap.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List recent entry UUIDs and a one-line preview for --journal",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=30,
        help="With --list, max rows (default: 30)",
    )
    args = ap.parse_args()

    if not args.database.is_file():
        print(f"Not a file: {args.database}", file=sys.stderr)
        sys.exit(2)

    conn = connect_ro(args.database)
    try:
        if args.list:
            if not args.journal:
                ap.error("--list requires --journal")
            list_entries(conn, args.journal, max(1, args.limit))
            return

        if not args.entry_id:
            ap.error("need --entry-id (or use --list)")

        body = fetch_markdown(conn, args.entry_id, args.journal)
        if body is None:
            print(
                "No entry found (check --entry-id and --journal).",
                file=sys.stderr,
            )
            sys.exit(1)

        if args.output:
            args.output.write_text(body, encoding="utf-8")
        else:
            sys.stdout.write(body)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
