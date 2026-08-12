"""Submit an application through a company's website contact form.

Contact forms vary wildly, so this is a best-effort crawler:
1. Find the contact page(s) of the guessed company domain (raw HTML, not jina
   text proxy, because we need the real <form> markup).
2. Parse forms, pick the one with an email + message field and no captcha.
3. Fill it with candidate data (name, email, phone, subject, message) and
   submit with requests, attaching the resume PDF if the form has a file field.

This will not work for every site (JS-only forms, captcha, ATS boards like
Greenhouse/Lever/Workday). We record what actually happened so the user can
tell real sends from failures.
"""

import os
import re
from html.parser import HTMLParser

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "job_cache.json")

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

CAPTCHA_RE = re.compile(r"g-recaptcha|recaptcha|hcaptcha|turnstile|captcha", re.I)
SKIP_ACTION_RE = re.compile(r"mailto:|javascript:", re.I)
CONTACT_PATHS = ["/contact", "/contact-us", "/contactus", "/company/contact", "/contact/", "/contact-us/", ""]


class _FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self._form = None
        self._in_form = False
        self._textarea = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._in_form = True
            self._form = {
                "action": a.get("action", ""),
                "method": a.get("method", "get").lower(),
                "fields": [],
                "has_file": False,
                "text": "",
            }
        elif self._in_form and tag in ("input", "textarea", "select", "button"):
            if tag == "input":
                ftype = a.get("type", "text").lower()
                name = a.get("name", "")
                if ftype in ("hidden", "text", "email", "tel", "url", "number", "date", "submit", "checkbox", "radio", "password", "search"):
                    self._form["fields"].append({"name": name, "type": ftype, "value": a.get("value", "")})
                if ftype == "file":
                    self._form["has_file"] = True
                    if name:
                        self._form["fields"].append({"name": name, "type": "file"})
            elif tag == "textarea" and a.get("name"):
                self._form["fields"].append({"name": a["name"], "type": "textarea"})
            elif tag == "button" and a.get("type", "submit").lower() == "submit":
                pass
        elif not self._in_form and tag == "a" and re.search(r"contact", a.get("href", ""), re.I):
            self._form = None

    def handle_data(self, data):
        if self._in_form:
            self._form["text"] += data

    def handle_endtag(self, tag):
        if tag == "form" and self._in_form:
            self.forms.append(self._form)
            self._in_form = False
            self._form = None


def _load_cache():
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def fetch_html(url, timeout=25):
    """Fetch raw HTML: try direct first, then via r.jina.ai with X-Return-Format: html."""
    for headers, prefix in ((UA, ""), ({**UA, "Accept": "text/plain", "X-Return-Format": "html"}, "https://r.jina.ai/")):
        try:
            r = requests.get(prefix + url, headers=headers, timeout=timeout)
            if r.status_code == 200 and "text/html" in r.headers.get("content-type", "text/html"):
                return r.text
        except Exception:
            pass
    return ""


def _abs_url(base, href):
    from urllib.parse import urljoin

    return urljoin(base, href or "")


def parse_forms(html):
    if not html:
        return []
    p = _FormParser()
    try:
        p.feed(html)
    except Exception:
        return []
    return p.forms


def _field_name(name):
    return (name or "").lower()


def _pick_form(forms):
    """Return the best form: POST with email + message, no captcha, no mailto action.

    Prefers forms with both an email and a message field (real contact forms);
    falls back to larger POST forms.
    """
    scored = []
    for f in forms:
        if CAPTCHA_RE.search(f.get("text", "")) or CAPTCHA_RE.search(" ".join(x["name"] for x in f["fields"])):
            continue
        if SKIP_ACTION_RE.search(f.get("action", "")):
            continue
        names = [_field_name(x["name"]) for x in f["fields"]]
        joined = " ".join(names)
        has_email = any(re.search(r"e-?mail", n) or n in ("email", "your_email", "emailaddress") for n in names) or "email" in joined
        has_msg = any(re.search(r"message|comment|body|text|description|letter", n) for n in names)
        has_name = any(re.search(r"name|first|last", n) for n in names)
        # skip pure search/newsletter forms
        if set(names) <= {"s", "q", "search", "search-input"}:
            continue
        score = 0
        if f["method"] == "post":
            score += 10
        if has_email:
            score += 20
        if has_msg:
            score += 15
        if has_name:
            score += 5
        if len(f["fields"]) >= 4:
            score += 3
        if not (has_email or has_msg):
            continue
        scored.append((score, f))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def _fill(f, job, candidate, letter, company):
    data = {}
    for field in f["fields"]:
        name = _field_name(field["name"])
        if field["type"] in ("hidden", "checkbox", "radio", "password"):
            if field["type"] == "hidden" and field["value"]:
                data[field["name"]] = field["value"]
            continue
        if field["type"] == "file":
            continue
        if re.search(r"e-?mail|email", name) or name in ("your_email", "emailaddress"):
            data[field["name"]] = candidate.get("email", "")
        elif re.search(r"phone|tel|mobile|whatsapp", name):
            data[field["name"]] = candidate.get("phone", "")
        elif re.search(r"full-?name|your[-_]?name|first|last|fname|lname", name) or name == "name":
            data[field["name"]] = candidate.get("name", "")
        elif re.search(r"subject|title", name):
            data[field["name"]] = f"Job application: {job.get('title', '')} - {company}"
        elif re.search(r"message|comment|body|text|description|letter|details", name):
            data[field["name"]] = letter[:2500]
        elif name:
            data[field["name"]] = ""
    return data


def find_and_submit(domain, job, candidate, letter, company, resume_pdf=None, timeout=25):
    """Try contact pages of `domain`, submit application via first usable form.

    Returns (ok: bool, detail: str, form_url: str or None).
    """
    if not domain:
        return False, "دامنه شرکت ناشناخته", None
    base = f"https://www.{domain}" if not domain.startswith("http") else domain
    for path in CONTACT_PATHS:
        url = _abs_url(base, path)
        html = fetch_html(url, timeout)
        if not html:
            continue
        if CAPTCHA_RE.search(html) and "form" not in html:
            return False, "صفحه دارای کپچا است", url
        forms = parse_forms(html)
        form = _pick_form(forms)
        if not form:
            continue
        action = _abs_url(url, form["action"])
        data = _fill(form, job, candidate, letter, company)
        post_headers = {
            **UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base,
            "Referer": url,
        }
        try:
            if form["method"] == "get":
                r = requests.get(action, params=data, headers=UA, timeout=timeout)
            else:
                if form["has_file"] and resume_pdf and os.path.exists(resume_pdf):
                    with open(resume_pdf, "rb") as fh:
                        files = {f["name"]: (os.path.basename(resume_pdf), fh, "application/pdf") for f in form["fields"] if f["type"] == "file"}
                        post_headers.pop("Content-Type", None)
                        r = requests.post(action, data=data, files=files or None, headers=post_headers, timeout=timeout)
                else:
                    r = requests.post(action, data=data, headers=post_headers, timeout=timeout)
            if r.status_code >= 400:
                return False, f"فرم رد شد (HTTP {r.status_code}) -> {action}", url
            return True, f"فرم ارسال شد (HTTP {r.status_code}) -> {action}", url
        except Exception as e:
            return False, f"خطا در ارسال فرم: {e}", url
    return False, "فرم قابل استفاده یافت نشد (JS/کپچا/بدون فرم)", base


def lookup_contact_form(company, domain=None):
    """Cache the fact we found (or could not find) a contact form."""
    if not domain:
        return None
    key = f"contact_form_{domain}"
    cache = _load_cache()
    if key in cache:
        return cache[key]
    cache[key] = domain
    _save_cache(cache)
    return domain


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.alfanar.com/en"
    html = fetch_html(url)
    forms = parse_forms(html)
    print(f"{url}: {len(forms)} form(s)")
    for f in forms[:5]:
        print("  action=", f["action"], "method=", f["method"], "fields=", [x["name"] for x in f["fields"][:8]], "file=", f["has_file"])
