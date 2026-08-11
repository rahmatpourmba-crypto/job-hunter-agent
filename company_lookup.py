"""Find a company's website domain and HR/contact email so we can apply by email.

Search engines are blocked/captcha'd from GitHub Actions datacenters, so we:
1. Derive a candidate domain from the company name (e.g. "Rotana Hotels" -> rotana.com).
2. Check the company's own site (via the r.jina.ai text proxy) for a contact/careers
   page and extract emails from it.
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
    r"no-?reply|donotreply|example\.|\.png|\.jpg|\.gif|sentry|wixpress|@2x|godaddy|sitemaps?",
    re.I,
)
STOPWORDS = {"the", "a", "an", "and", "or", "of", "for", "co", "inc", "ltd", "llc", "group",
             "hotels", "hotel", "company", "corporation", "corp", "international", "intl",
             "technologies", "technology", "systems", "solutions", "services", "holdings",
             "hiring", "careers"}


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
    """Turn a company name into candidate domains."""
    name = (company or "").strip()
    if not name:
        return []
    words = [w for w in re.split(r"[^a-zA-Z0-9]+", name.lower()) if w and w not in STOPWORDS]
    if not words:
        words = re.findall(r"[a-zA-Z0-9]+", name.lower())
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


def _crawl_for_emails(domain):
    """Try homepage + common contact/careers paths, collect emails."""
    found = []
    paths = ["", "/contact", "/contact-us", "/careers", "/about", "/about-us"]
    for path in paths:
        text = _fetch_via_jina(f"https://www.{domain}{path}")
        if not text:
            continue
        for m in EMAIL_RE.findall(text):
            if not BANNED.search(m):
                found.append(m)
        if len(found) >= 3:
            break
        time.sleep(0.15)
    return sorted(set(found))


def lookup(company, force=False):
    """Return {'emails': [...], 'domain': str or None} for a company."""
    key = "company_lookup_" + slug(company)
    cache = _load_cache()
    if not force and key in cache:
        return cache[key]
    result = {"emails": [], "domain": None}
    for domain in _guess_domains(company)[:3]:
        emails = _crawl_for_emails(domain)
        if emails:
            result["emails"] = emails
            result["domain"] = domain
            break
    cache[key] = result
    _save_cache(cache)
    return result


if __name__ == "__main__":
    import sys

    for c in sys.argv[1:]:
        r = lookup(c)
        print(f"{c}: domain={r['domain']} emails={r['emails']}")
