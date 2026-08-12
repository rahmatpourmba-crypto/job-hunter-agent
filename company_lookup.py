"""Find a company's website domain, HR/contact email, phone numbers and an
"about" snippet so we can apply by email/contact form.

Search engines are blocked/captcha'd from GitHub Actions datacenters, so we:
1. Use a known-domain map, else derive a candidate domain from the company
   name (e.g. "Rotana Hotels" -> rotana.com).
2. Check the company's own site (via the r.jina.ai text proxy) for a
   contact/careers page and extract emails + phones from it.
3. Cache results in job_cache.json under company_lookup_{slug}.
"""

import json
import os
import re
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "job_cache.json")

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/124.0 Safari/537.36",
    "Accept": "text/plain",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BANNED = re.compile(
    r"no-?reply|donotreply|example\.|\.png|\.jpg|\.gif|sentry|wixpress|@2x|godaddy|sitemaps?|"
    r"user@website|your@email|domain\.com$|website\.com$|email\.com$",
    re.I,
)
# International phone numbers: +country code with groups (spaces/dashes/parens).
PHONE_RE = re.compile(
    r"(?:\+?[1-9]\d{0,2}[\s\-.]?)?\(?\d{2,4}\)?[\s\-.]\d{3,4}[\s\-.]\d{3,4}"
)
# wa.me / api.whatsapp.com phone links
WA_RE = re.compile(r"(?:wa\.me/|whatsapp\.com/send\?phone=|api\.whatsapp\.com/send\?phone=)(\d+)", re.I)
STOPWORDS = {"the", "a", "an", "and", "or", "of", "for", "co", "inc", "ltd", "llc", "group",
             "hotels", "hotel", "company", "corporation", "corp", "international", "intl",
             "technologies", "technology", "systems", "solutions", "services", "holdings",
             "hiring", "careers"}

# Reliable domains for well-known employers (name -> domain).
KNOWN_DOMAINS = {
    "fortive": "fortive.com",
    "khidmah": "khidmah.com",
    "penspen": "penspen.com",
    "convergint": "convergint.com",
    "mace": "macegroup.com",
    "alfanar": "alfanar.com",
    "larsen & toubro": "larsentoubro.com",
    "l&t": "larsentoubro.com",
    "ehs consultants": "ehsconsultants.com",
    "i8is": "i8is.com",
    "infiniti software": "i8is.com",
    "business needs inc": "businessneeds.com",
    "altimetrik": "altimetrik.com",
    "hamonis": "hamonis.io",
    "1inch": "1inch.io",
    "coinbase": "coinbase.com",
    "certik": "certik.com",
    "wood": "woodplc.com",
    "rotana": "rotanatimes.com",
    "anton": "anton-oil.com",
    "sardar group": "sardargroup.com",
    "abdullah al-othaim": "alothaimgroup.com",
    "al-othaim": "alothaimgroup.com",
    "al othaim markets": "alothaimgroup.com",
    "jobicy": "jobicy.com",
    "launch legends": "launchlegends.com",
}


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


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def _guess_domains(company):
    """Turn a company name into candidate domains (known map first)."""
    name = (company or "").strip()
    if not name:
        return []
    lower = name.lower()
    for known, dom in KNOWN_DOMAINS.items():
        if known in lower:
            return [dom]
    words = [w for w in re.split(r"[^a-zA-Z0-9]+", lower) if w and w not in STOPWORDS]
    if not words:
        words = re.findall(r"[a-zA-Z0-9]+", lower)
    cands = set()
    for w in words:
        cands.add(f"{w}.com")
    if len(words) >= 2:
        cands.add(f"{words[0]}{words[-1]}.com")
        cands.add(f"{'.'.join(words[:2])}.com")
    # strip common suffixes already in name
    for suf in ("ltd", "llc", "inc", "co", "group"):
        if words and words[-1] == suf:
            base = ".".join(words[:-1])
            cands.add(f"{base}.com")
    return sorted(cands, key=len)


def _fetch_via_jina(url, timeout=20):
    try:
        r = requests.get("https://r.jina.ai/" + url, headers=UA, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""


def _clean_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 10 or len(digits) > 14:
        return None
    return "+" + digits


def _collect_phones(text):
    phones = set()
    for m in WA_RE.findall(text or ""):
        p = _clean_phone(m)
        if p:
            phones.add(p)
    # strip blob:/url noise: remove UUID-like hex strings before matching
    clean_text = re.sub(r"[0-9a-f]{16,}", " ", text or "")
    clean_text = re.sub(r"blob:http[^ )\"]*", " ", clean_text)
    for m in PHONE_RE.findall(clean_text):
        # require an explicit "+" (international format) to avoid years/ids/JS noise
        if not m.startswith("+"):
            continue
        p = _clean_phone(m)
        if p:
            phones.add(p)
    bad = {"2026", "2025", "2024", "0000000000", "00000000000"}
    return sorted(p for p in phones if p[1:] not in bad and len(set(p[1:])) > 2)


def _about_snippet(text, limit=220):
    """Take a short meaningful snippet from an about page."""
    t = re.sub(r"\s+", " ", text or "")
    # drop jina header, nav/cookie noise
    t = re.sub(r"^(Title:.*?URL Source:.*?)(Markdown Content:|\*{2,})", "", t)
    t = re.sub(r"(Cookie|Privacy|Terms|skip to content|©[\d\s]+)", " ", t)
    sentences = re.split(r"(?<=[.!?])\s+", t)
    for s in sentences:
        s = s.strip()
        if 60 < len(s) < 400 and s[0].isupper() and not re.search(r"cookie|privacy|consent|subscribe|newsletter", s, re.I):
            return s[:limit]
    if t:
        return t[:limit]
    return ""


def _crawl_for_emails(domain):
    """Try homepage + common contact/careers paths, collect emails, phones, about."""
    found = []
    phones = []
    about = ""
    paths = ["", "/contact", "/contact-us", "/careers", "/about", "/about-us"]
    for path in paths:
        text = _fetch_via_jina(f"https://www.{domain}{path}")
        if not text:
            continue
        for m in EMAIL_RE.findall(text):
            if not BANNED.search(m):
                found.append(m)
        phones.extend(_collect_phones(text))
        if not about and ("about" in path or path == ""):
            about = _about_snippet(text)
        if len(found) >= 3:
            break
        time.sleep(0.15)
    return sorted(set(found)), sorted(set(phones)), about


def lookup(company, force=False):
    """Return {'emails', 'phones', 'domain', 'about'} for a company."""
    key = "company_lookup_" + slug(company)
    cache = _load_cache()
    if not force and key in cache:
        return cache[key]
    result = {"emails": [], "phones": [], "domain": None, "about": ""}
    first_domain = None
    for domain in _guess_domains(company)[:3]:
        emails, phones, about = _crawl_for_emails(domain)
        if emails or phones:
            result["emails"] = emails
            result["phones"] = phones
            result["domain"] = domain
            result["about"] = about
            break
        if first_domain is None and about:
            # domain loads fine (we got a snippet) even if no contacts found
            first_domain = domain
    if result["domain"] is None and first_domain:
        result["domain"] = first_domain
    cache[key] = result
    _save_cache(cache)
    return result


if __name__ == "__main__":
    import sys

    for c in sys.argv[1:]:
        r = lookup(c)
        print(f"{c}: domain={r['domain']} emails={r['emails']} phones={r['phones']}")
        print(f"   about: {r['about'][:120]}")
