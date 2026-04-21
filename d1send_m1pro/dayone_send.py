#!/usr/bin/env python3
"""
OpenClaw Day One email sender. All machine-local paths are fixed under SEND_ROOT.
"""
import argparse
import base64
import datetime as dt
import json
import mimetypes
import os
import re
from email import encoders
from email.generator import BytesGenerator
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Config, credentials, token, and sent/ archive live under SEND_ROOT.
# Override with DAYONE_SEND_ROOT for a non-default layout; otherwise use this script's directory.
SEND_ROOT = Path(
    os.environ.get("DAYONE_SEND_ROOT", str(Path(__file__).resolve().parent))
).expanduser().resolve()
CONFIG_JSON = SEND_ROOT / "dayone_config.json"
CREDENTIALS_JSON = SEND_ROOT / "credentials.json"
TOKEN_JSON = SEND_ROOT / "token.json"
SENT_DIR = SEND_ROOT / "sent"

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _now_utc_compact() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slug(s: str, max_len: int = 60) -> str:
    s = s.strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^A-Za-z0-9._-]+", "", s)
    s = s.strip("-._")
    if not s:
        return "untitled"
    return s[:max_len]


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_payload_json(path: Path) -> Dict[str, Any]:
    """
    Load a payload written by an agent. Tolerates common mistakes:
    - Invalid ``\'`` escapes (JSON does not define ``\\'``; apostrophes need no escape).
    - UTF-8 BOM.
    """
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    raw = raw.strip()
    variants = [raw]
    if "\\'" in raw:
        variants.append(raw.replace("\\'", "'"))
    last_err: Optional[json.JSONDecodeError] = None
    for candidate in variants:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
            raise ValueError(f"Payload {path} must be a JSON object at top level.")
        except json.JSONDecodeError as e:
            last_err = e
            continue
    hint = (
        ' Apostrophes: in JSON use a normal apostrophe inside double-quoted strings '
        '(e.g. "it\'s"). Backslash-before-apostrophe is invalid JSON.'
    )
    raise ValueError(f"Invalid JSON in {path}: {last_err}.{hint}") from last_err


def _load_config() -> Dict[str, Any]:
    if not CONFIG_JSON.exists():
        raise FileNotFoundError(
            f"Config not found: {CONFIG_JSON}\n"
            f"Create dayone_config.json under {SEND_ROOT} (see dayone_config.example.json)."
        )
    cfg = _read_json(CONFIG_JSON)
    if not isinstance(cfg, dict):
        raise ValueError("Config must be a JSON object.")
    return cfg


def _resolve_payload_path(arg: str) -> Path:
    p = Path(arg).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (SEND_ROOT / p).resolve()


def _validate_payload(payload: Dict[str, Any], payload_path: Path) -> Tuple[str, str, List[str]]:
    subject = payload.get("subject")
    body = payload.get("body_markdown")
    attachments = payload.get("attachments", [])

    if not isinstance(subject, str) or not subject.strip():
        raise ValueError(f"Payload {payload_path} missing non-empty 'subject' (string).")
    if not isinstance(body, str) or not body.strip():
        raise ValueError(f"Payload {payload_path} missing non-empty 'body_markdown' (string).")
    if attachments is None:
        attachments = []
    if not isinstance(attachments, list) or not all(isinstance(x, str) for x in attachments):
        raise ValueError(f"Payload {payload_path} 'attachments' must be a list of strings.")

    return subject.strip(), body, attachments


def _normalize_body_markdown(body: str) -> str:
    """
    Fix common agent mistakes before building the email:
    - Literal backslash + 'n' / 'r' / 't' pairs (shows as ``\\n`` in Day One). Repeat until
      stable so doubled JSON escaping (e.g. ``\\\\n`` in file → ``\\n`` after one load) still flattens.
    - Unicode line/paragraph separators (U+2028 / U+2029) from copy-paste.
    """
    out = body.replace("\u2028", "\n").replace("\u2029", "\n")
    while "\\r\\n" in out:
        out = out.replace("\\r\\n", "\n")
    while "\\n" in out:
        out = out.replace("\\n", "\n")
    while "\\r" in out:
        out = out.replace("\\r", "\n")
    while "\\t" in out:
        out = out.replace("\\t", "\t")
    return out


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _get_gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    if not CREDENTIALS_JSON.exists():
        raise FileNotFoundError(f"Google OAuth client file not found: {CREDENTIALS_JSON}")

    creds: Optional[Credentials] = None
    if TOKEN_JSON.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_JSON), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_JSON), SCOPES)
            creds = flow.run_local_server(port=0)
        _ensure_dir(TOKEN_JSON.parent)
        TOKEN_JSON.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def _guess_mime(path: Path) -> Tuple[str, str]:
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        return "application", "octet-stream"
    maintype, subtype = mime_type.split("/", 1)
    return maintype, subtype


def _attach_file(msg: MIMEMultipart, path: Path) -> None:
    maintype, subtype = _guess_mime(path)
    data = path.read_bytes()
    filename = path.name

    if maintype == "text":
        try:
            text = data.decode("utf-8")
            part = MIMEText(text, _subtype=subtype, _charset="utf-8")
        except UnicodeDecodeError:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(data)
            encoders.encode_base64(part)
    elif maintype == "application":
        from email.mime.application import MIMEApplication

        part = MIMEApplication(data, _subtype=subtype)
    else:
        part = MIMEBase(maintype, subtype)
        part.set_payload(data)
        encoders.encode_base64(part)

    part.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(part)


def _build_mime(sender: str, recipients: List[str], subject: str, body_markdown: str, attachments: List[str]) -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    msg.attach(MIMEText(body_markdown, "plain", "utf-8"))

    for p in attachments:
        path = Path(p).expanduser()
        if not path.is_absolute():
            raise ValueError(f"Attachment path must be absolute: {p}")
        if not path.exists():
            raise FileNotFoundError(f"Attachment not found: {path}")
        _attach_file(msg, path)

    return msg


def _to_gmail_raw(msg: MIMEMultipart) -> Dict[str, str]:
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return {"raw": raw}


def _render_eml_bytes(msg: MIMEMultipart) -> bytes:
    buf = BytesIO()
    BytesGenerator(buf, maxheaderlen=0).flatten(msg)
    return buf.getvalue()


def _archive(
    payload_path: Path,
    subject: str,
    payload: Dict[str, Any],
    eml_bytes: bytes,
    sent_message_id: Optional[str],
) -> Dict[str, Any]:
    _ensure_dir(SENT_DIR)

    stamp = _now_utc_compact()
    base = f"{stamp}-{_slug(subject)}"

    archived_payload_path = SENT_DIR / f"{base}.json"
    archived_eml_path = SENT_DIR / f"{base}.eml"
    archived_meta_path = SENT_DIR / f"{base}.meta.json"

    archived_payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archived_eml_path.write_bytes(eml_bytes)

    meta = {
        "timestamp_utc": stamp,
        "subject": subject,
        "source_payload_path": str(payload_path),
        "archived_payload_path": str(archived_payload_path),
        "archived_eml_path": str(archived_eml_path),
        "gmail_message_id": sent_message_id,
        "send_root": str(SEND_ROOT),
    }
    archived_meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a Day One email from a JSON payload and archive it.")
    parser.add_argument(
        "--payload",
        required=True,
        help=f"Payload JSON path (absolute, or relative to {SEND_ROOT}).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate/build/archive but do not send.")
    args = parser.parse_args()

    payload_path = _resolve_payload_path(args.payload)

    cfg = _load_config()

    sender = cfg.get("sender")
    recipients = cfg.get("recipients")

    if not isinstance(sender, str) or not sender.strip():
        raise ValueError("dayone_config.json 'sender' must be a non-empty string.")
    if not isinstance(recipients, list) or not recipients or not all(isinstance(x, str) and x.strip() for x in recipients):
        raise ValueError("dayone_config.json 'recipients' must be a non-empty list of strings.")

    if not payload_path.exists():
        raise FileNotFoundError(f"Payload not found: {payload_path}")

    payload = _read_payload_json(payload_path)
    if not isinstance(payload, dict):
        raise ValueError(f"Payload {payload_path} must be a JSON object.")

    subject, body_markdown, attachments = _validate_payload(payload, payload_path)
    body_markdown = _normalize_body_markdown(body_markdown)

    msg = _build_mime(
        sender=sender.strip(),
        recipients=[x.strip() for x in recipients],
        subject=subject,
        body_markdown=body_markdown,
        attachments=attachments,
    )

    eml_bytes = _render_eml_bytes(msg)

    if args.dry_run:
        meta = _archive(
            payload_path=payload_path,
            subject=subject,
            payload=payload,
            eml_bytes=eml_bytes,
            sent_message_id=None,
        )
        print(json.dumps({"ok": True, "dry_run": True, "meta": meta}, indent=2))
        return 0

    service = _get_gmail_service()

    try:
        raw_message = _to_gmail_raw(msg)
        sent = service.users().messages().send(userId="me", body=raw_message).execute()
        message_id = sent.get("id")
        meta = _archive(
            payload_path=payload_path,
            subject=subject,
            payload=payload,
            eml_bytes=eml_bytes,
            sent_message_id=message_id,
        )
        print(json.dumps({"ok": True, "gmail_message_id": message_id, "meta": meta}, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
