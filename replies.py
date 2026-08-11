import imaplib
import re
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime

STRIP_HTML_RE = re.compile(r"<[^>]+>")


def _decode(value):
    if not value:
        return ""
    parts = decode_header(value)
    out = ""
    for raw, enc in parts:
        if isinstance(raw, bytes):
            try:
                out += raw.decode(enc or "utf-8", errors="replace")
            except (LookupError, ValueError):
                out += raw.decode("utf-8", errors="replace")
        else:
            out += raw
    return out


def _body_text(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain" and not part.get_filename():
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    return re.sub(r"\s+", " ", STRIP_HTML_RE.sub(" ", html)).strip()
                except Exception:
                    continue
            elif part.get_content_type().startswith("text/"):
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
    try:
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
    except Exception:
        return ""


def fetch_replies(user, app_password, days=10, my_name=""):
    replies = []
    M = None
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
        M.login(user, app_password)
        M.select("INBOX")
        typ, data = M.search(None, "SINCE", imaplib_imap_date(days))
        if typ != "OK":
            return replies
        ids = data[0].split()
        my_email = user.lower()
        for mid in ids[-200:]:
            typ, msg_data = M.fetch(mid, "(RFC822)")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            msg = None
            try:
                from email import message_from_bytes
                msg = message_from_bytes(raw)
            except Exception:
                continue
            frm = _decode(msg.get("From", "")).lower()
            subj = _decode(msg.get("Subject", ""))
            if my_email in frm:
                continue
            if not (re.search(r"\bre\s*:", subj, re.I) and my_name.lower() in subj):
                continue
            body = _body_text(msg)[:1200]
            when = ""
            try:
                when = parsedate_to_datetime(msg.get("Date")).strftime("%Y-%m-%d %H:%M")
            except Exception:
                when = msg.get("Date", "")
            replies.append({
                "msg_id": mid.decode() if isinstance(mid, bytes) else str(mid),
                "from": frm,
                "subject": subj,
                "body": body.strip(),
                "date": when,
            })
    except Exception:
        pass
    finally:
        if M is not None:
            try:
                M.logout()
            except Exception:
                pass
    return replies


def imaplib_imap_date(days):
    from datetime import datetime, timedelta

    return (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")