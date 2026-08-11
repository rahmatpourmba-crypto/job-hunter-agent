import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "job_cache.json")


def _load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


CACHE = _load_cache()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BANNED_EMAIL_RE = re.compile(r"no-?reply|donotreply|example\.|@2x|\.png|\.jpg", re.I)

SALARY_PATTERNS = [
    re.compile(r"\$\s*(\d{2,3})\s*[kK]"),
    re.compile(r"\$\s*(\d[\d,]*)(?:\s*[-–]\s*(\d[\d,]*))?"),
    re.compile(r"(?:€|eur|euros?)\s*(\d[\d,]*)", re.I),
    re.compile(r"(?:£|gbp|pounds?)\s*(\d[\d,]*)", re.I),
    re.compile(r"(\d[\d,]*)\s*[-–]\s*(\d[\d,]*)\s*(?:usd|aed|sar|qar|omr|kwd|bhd|dhs|us dollars)", re.I),
    re.compile(r"(?:usd|us dollars)\s*(\d[\d,]*(?:\.\d+)?)(?:\s*[-–]\s*(\d[\d,]*))?", re.I),
]

CURRENCY_RATE = {"usd": 1.0, "eur": 1.08, "gbp": 1.27, "cad": 0.73, "aud": 0.66}


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return html.unescape(text)


def clean_whitespace(text):
    return re.sub(r"\s+", " ", text or "").strip()


def extract_emails(text):
    out = []
    for m in EMAIL_RE.findall(text or ""):
        if not BANNED_EMAIL_RE.search(m):
            out.append(m)
    return list(dict.fromkeys(out))


def extract_salary_range(text):
    lo, hi = None, None
    hourly = re.compile(r"/\s*h(?:ou)?r\b|per\s*hour|hourly|p/h|P/H", re.I)
    monthly = re.compile(r"per\s*month|monthly|/\s*mo\b|a\s*month|per\s*annum|annual", re.I)
    for pat in SALARY_PATTERNS:
        for m in pat.finditer(text or ""):
            vals = [g for g in m.groups() if g]
            if not vals:
                continue
            nums = [int(v.replace(",", "")) for v in vals]
            if any(n < 1000 for n in nums):
                nums = [n * 1000 for n in nums]
            ctx = text[max(0, m.start() - 40):m.end() + 40]
            if hourly.search(ctx):
                nums = [n * 2080 for n in nums]
            elif monthly.search(ctx) and "annual" not in ctx.lower():
                nums = [n * 12 for n in nums]
            if lo is None or nums[0] < lo:
                lo = nums[0]
            if hi is None or nums[-1] > hi:
                hi = nums[-1]
    return lo, hi


def _normalize_salary(lo, hi, currency):
    rate = CURRENCY_RATE.get((currency or "usd").lower(), 1.0)
    return (round(lo * rate) if lo else None), (round(hi * rate) if hi else None)


class RemotiveSource:
    def __init__(self):
        self.base = "https://remotive.com/api/remote-jobs"
        self.seen_urls = set()

    def fetch(self, keywords, max_days_old):
        jobs, all_urls = [], set()
        for kw in keywords:
            try:
                r = requests.get(self.base, params={"search": kw}, headers=HEADERS, timeout=25)
                data = r.json()
            except Exception:
                continue
            for j in data.get("jobs", []):
                url = j.get("url") or ""
                if not url or url in all_urls:
                    continue
                all_urls.add(url)
                published = (j.get("publication_date") or "")[:10]
                jobs.append({
                    "source": "remotive",
                    "title": j.get("title") or "",
                    "company": j.get("company_name") or "",
                    "location": j.get("candidate_required_location") or "",
                    "url": url,
                    "description": "",
                    "published": published,
                    "remote": True,
                    "currency": None,
                    "salary_min": None,
                    "salary_max": None,
                })
            time.sleep(0.2)
        self._fetch_details(jobs, max_days_old)
        return jobs

    def _fetch_details(self, jobs, max_days_old):
        fetched = 0
        for j in jobs:
            if fetched >= 60 or j.get("url") in self.seen_urls:
                continue
            try:
                r = requests.get(j["url"].replace("/remote-jobs/", "/api/remote-jobs/") if "/remote-jobs/" in j["url"] else f"{self.base}/{j['url'].rstrip('/').split('/')[-1]}", headers=HEADERS, timeout=25)
                detail = r.json()
            except Exception:
                continue
            desc = clean_whitespace(strip_html(detail.get("description") or ""))
            j["description"] = desc
            lo, hi = extract_salary_range(desc)
            j["salary_min"], j["salary_max"] = lo, hi
            self.seen_urls.add(j["url"])
            fetched += 1
            time.sleep(0.15)


class WeWorkRemotelySource:
    def fetch(self, feeds):
        jobs, seen = [], set()
        for feed in feeds:
            try:
                r = requests.get(feed, headers=HEADERS, timeout=25)
                root = ET.fromstring(r.content)
            except Exception:
                continue
            for item in root.findall(".//item"):
                title = clean_whitespace((item.findtext("title") or ""))
                link = (item.findtext("link") or "").strip()
                if not link or link in seen:
                    continue
                seen.add(link)
                raw = item.findtext("description") or ""
                desc = clean_whitespace(strip_html(raw))
                published = (item.findtext("pubDate") or "")[:16]
                lo, hi = extract_salary_range(desc)
                company = ""
                if ":" in title:
                    company = title.split(":", 1)[0].strip()
                jobs.append({
                    "source": "weworkremotely",
                    "title": title,
                    "company": company,
                    "location": "Remote",
                    "url": link,
                    "description": desc,
                    "published": published,
                    "remote": True,
                    "currency": None,
                    "salary_min": lo,
                    "salary_max": hi,
                })
        return jobs


class JobicySource:
    def fetch(self, tags):
        jobs, seen = [], set()
        for tag in tags:
            try:
                r = requests.get(
                    "https://jobicy.com/api/v2/remote-jobs",
                    params={"count": 30, "tag": tag},
                    headers=HEADERS,
                    timeout=25,
                )
                data = r.json()
            except Exception:
                continue
            for j in data.get("jobs", []):
                url = j.get("url") or ""
                if not url or url in seen:
                    continue
                seen.add(url)
                desc = clean_whitespace(strip_html((j.get("jobDescription") or "") + " " + (j.get("jobExcerpt") or "")))
                lo, hi = j.get("annualSalaryMin"), j.get("annualSalaryMax")
                currency = j.get("salaryCurrency") or "usd"
                if not lo and not hi:
                    lo, hi = extract_salary_range(desc)
                lo, hi = _normalize_salary(lo, hi, currency)
                jobs.append({
                    "source": "jobicy",
                    "title": j.get("jobTitle") or "",
                    "company": j.get("companyName") or "",
                    "location": j.get("jobGeo") or "Remote",
                    "url": url,
                    "description": desc,
                    "published": (j.get("pubDate") or "")[:10],
                    "remote": True,
                    "currency": currency,
                    "salary_min": lo,
                    "salary_max": hi,
                })
            time.sleep(0.2)
        return jobs


class LinkedInSource:
    """LinkedIn jobs via the public guest endpoint (no login required).

    Search URL: https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
    Supports f_WT (2=remote, 1=onsite, 3=hybrid), f_TPR (r604800 = last 7 days),
    location= free text, keywords=.
    """

    SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def fetch(self, keywords, locations=None, max_days_old=30):
        jobs = []
        seen = set()
        locations = locations or [""]
        # Cap search combos: remote search (empty location) for each keyword,
        # plus region search with a combined query to keep runtime sane.
        f_tpr = self._tpr_for(max_days_old)
        keywords = keywords[:4]
        locations = locations[:5]
        for kw in keywords:
            for loc in locations:
                params = {"keywords": kw, "location": loc, "start": 0}
                if f_tpr:
                    params["f_TPR"] = f_tpr
                cards = self._fetch_cards(params)
                for c in cards:
                    job_id = c.get("id")
                    if not job_id or job_id in seen:
                        continue
                    seen.add(job_id)
                    jobs.append({
                        "source": "linkedin",
                        "title": c.get("title") or "",
                        "company": c.get("company") or "",
                        "location": c.get("location") or "",
                        "url": c.get("url") or "",
                        "description": c.get("description") or "",
                        "published": c.get("date") or "",
                        "remote": "remote" in (c.get("location") or "").lower(),
                        "currency": None,
                        "salary_min": None,
                        "salary_max": None,
                    })
                time.sleep(0.2)
        self._fetch_details(jobs)
        return jobs

    def _tpr_for(self, days):
        if not days:
            return ""
        for label, n in (("r2592000", 30), ("r604800", 7), ("r86400", 1)):
            if days <= n:
                return label
        return ""

    def _fetch_cards(self, params):
        try:
            r = requests.get(self.SEARCH, params=params, headers=self.headers, timeout=30)
            if r.status_code != 200:
                return []
            text = r.text
        except Exception:
            return []
        # cards are <li> blocks that contain a job-search-card
        raw_cards = re.findall(r'<li>(.*?)</li>', text, re.S)
        cards = []
        for raw in raw_cards:
            if "job-search-card" not in raw:
                continue
            m_id = re.search(r'data-entity-urn="urn:li:jobPosting:(\d+)"', raw)
            title = self._extract(raw, r'class="base-search-card__title">(.*?)</h3>')
            company = self._extract(raw, r'class="base-search-card__subtitle">(.*?)</h4>')
            location = self._extract(raw, r'class="job-search-card__location">(.*?)</span>')
            date_raw = self._extract(raw, r'class="job-search-card__listdate"[^>]*datetime="([^"]+)"')
            href = self._extract(raw, r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"')
            # fallback: any href containing /jobs/view/
            if not href:
                m_h = re.search(r'href="([^"]*jobs/view/[^"]+)"', raw)
                if m_h:
                    href = m_h.group(1)
            cards.append({
                "id": m_id.group(1) if m_id else "",
                "title": title,
                "company": company,
                "location": location,
                "date": date_raw[:10] if date_raw else "",
                "url": (href.split("?")[0] if href else ""),
            })
        return cards

    @staticmethod
    def _extract(raw, pattern):
        m = re.search(pattern, raw, re.S)
        if not m:
            return ""
        return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip())

    def _fetch_details(self, jobs):
        fetched = 0
        for j in jobs:
            if fetched >= 15:
                break
            job_id = re.search(r"-(\d+)$", j["url"])
            jid = job_id.group(1) if job_id else ""
            if not jid:
                continue
            cache_key = f"linkedin_detail_{jid}"
            if cache_key in CACHE:
                j["description"] = CACHE[cache_key].get("description", "")
                j["salary_min"] = CACHE[cache_key].get("salary_min")
                j["salary_max"] = CACHE[cache_key].get("salary_max")
                fetched += 1
                continue
            try:
                r = requests.get(self.DETAIL.format(job_id=jid), headers=self.headers, timeout=30)
                if r.status_code != 200:
                    continue
                text = r.text
            except Exception:
                continue
            desc = self._extract(text, r'class="show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>')
            if not desc:
                desc = self._extract(text, r'<section class="description">(.*?)</section>')
            desc = re.sub(r"\s+", " ", desc).strip()
            j["description"] = desc[:6000]
            lo, hi = extract_salary_range(desc)
            j["salary_min"], j["salary_max"] = lo, hi
            CACHE[cache_key] = {"description": j["description"], "salary_min": lo, "salary_max": hi}
            fetched += 1
            time.sleep(0.15)
        if CACHE:
            _save_cache(CACHE)


class GulfTalentSource:
    """Gulf + Iraq/Kurdistan on-site jobs via GulfTalent through the jina.ai text proxy.

    GulfTalent blocks direct scraping (Cloudflare), so we fetch via https://r.jina.ai/
    which returns readable markdown/text. Country pages are e.g.
    https://www.gulftalent.com/iraq/jobs , https://www.gulftalent.com/uae/jobs ...
    """

    def __init__(self, countries=None, proxy="https://r.jina.ai/"):
        self.countries = countries or []
        self.proxy = proxy.rstrip("/")

    def fetch(self, keywords, max_days_old=30):
        jobs = []
        seen = set()
        for country in self.countries:
            country_url = f"https://www.gulftalent.com/{country}/jobs"
            rows = self._fetch_listing(country_url)
            for row in rows:
                if not row.get("url") or row["url"] in seen:
                    continue
                seen.add(row["url"])
                jobs.append({
                    "source": f"gulftalent_{country}",
                    "title": row.get("title") or "",
                    "company": row.get("company") or "",
                    "location": row.get("location") or country.replace("-", " ").title(),
                    "url": row["url"],
                    "description": row.get("description") or "",
                    "published": row.get("date") or "",
                    "remote": "remote" in (row.get("location") or "").lower(),
                    "currency": None,
                    "salary_min": None,
                    "salary_max": None,
                })
        self._fetch_details(jobs, max_days_old, keywords)
        return jobs

    def _fetch_listing(self, country_url):
        text = self._fetch_text(country_url)
        if not text:
            return []
        md = text.split("Markdown Content:", 1)[-1]
        # The listing is a markdown table. Rows look like:
        # | [Title](https://www.gulftalent.com/iraq/jobs/slug-123)![](...) Company | [Location](...) | 12 Aug | ... |
        # Find the table block after the "| Position |" header.
        table_start = md.find("| Position")
        if table_start < 0:
            table_start = 0
        rows = []
        for line in md[table_start:].splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 4 or set(cols[0].lower().split()) & {"position", "---", ""}:
                continue
            title_cell, loc_cell = cols[0], cols[1]
            m_title = re.search(r"\[([^\]]+)\]\(([^)]+)\)", title_cell)
            if not m_title:
                continue
            title = m_title.group(1).strip()
            url = m_title.group(2).strip()
            # Company is whatever remains after the title link and the "Easy Apply" image.
            rest = title_cell[m_title.end():]
            m_img = re.search(r"!\[[^\]]*\]\([^)]*\)", rest)
            if m_img:
                rest = rest[m_img.end():]
            company = rest.strip()
            m_co = re.search(r"\[([^\]]+)\]", company)
            if m_co:
                company = m_co.group(1)
            company = re.sub(r"^\s*[\[\(]|[\]\)]\s*$", "", company).strip()
            m_loc = re.search(r"\[([^\]]+)\]", loc_cell)
            location = m_loc.group(1).strip() if m_loc else loc_cell
            date = cols[2].strip()
            rows.append({
                "title": title,
                "url": url,
                "company": company,
                "location": location,
                "date": date,
            })
        return rows

    def _fetch_details(self, jobs, max_days_old, keywords):
        fetched = 0
        for j in jobs:
            if fetched >= 8:
                break
            cache_key = f"gulftalent_detail_{j['url']}"
            if cache_key in CACHE:
                j["description"] = CACHE[cache_key].get("description", "")
                j["salary_min"] = CACHE[cache_key].get("salary_min")
                j["salary_max"] = CACHE[cache_key].get("salary_max")
                j["published"] = CACHE[cache_key].get("published", j.get("published", ""))
                fetched += 1
                continue
            text = self._fetch_text(j["url"])
            if not text:
                continue
            md = text.split("Markdown Content:", 1)[-1]
            body = self._isolate_body(md)
            desc = clean_whitespace(strip_html(body))
            j["description"] = desc[:6000]
            lo, hi = extract_salary_range(desc)
            j["salary_min"], j["salary_max"] = lo, hi
            # published date line like "Posted 17 days ago" -> date
            m = re.search(r"Posted\s+(\d+)\s+days?\s+ago", md, re.I)
            published = j.get("published", "")
            if m:
                days = int(m.group(1))
                published = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                j["published"] = published
            CACHE[cache_key] = {
                "description": j["description"],
                "salary_min": lo,
                "salary_max": hi,
                "published": published,
            }
            fetched += 1
            time.sleep(0.3)
        if CACHE:
            _save_cache(CACHE)

    @staticmethod
    def _isolate_body(md):
        # Keep only the portion that matters: from the job title / description heading.
        for marker in ("Job description", "## ", "### Role", "Salary"):
            i = md.find(marker)
            if i >= 0:
                return md[i:]
        return md

    def _fetch_text(self, url):
        try:
            r = requests.get(
                f"{self.proxy}/{url}",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                    "Accept": "text/plain",
                },
                timeout=45,
            )
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        return ""


class AdzunaSource:
    def __init__(self, app_id, app_key):
        self.app_id = app_id
        self.app_key = app_key
        self.enabled = bool(app_id and app_key)

    def fetch(self, keywords, countries, min_salary, max_days_old):
        if not self.enabled:
            return []
        jobs, seen = [], set()
        for country in countries:
            for kw in keywords:
                try:
                    r = requests.get(
                        f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                        params={
                            "app_id": self.app_id,
                            "app_key": self.app_key,
                            "what": kw,
                            "salary_min": max(min_salary, 1000),
                            "full_time": 1,
                            "max_days_old": max_days_old,
                            "results_per_page": 50,
                        },
                        headers=HEADERS,
                        timeout=25,
                    )
                    data = r.json()
                except Exception:
                    continue
                for j in data.get("results", []):
                    url = j.get("redirect_url") or ""
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    desc = clean_whitespace(strip_html(j.get("description") or ""))
                    lo, hi = extract_salary_range(desc)
                    if lo is None and j.get("salary_min"):
                        lo = j["salary_min"]
                        hi = j.get("salary_max")
                    lo, hi = _normalize_salary(lo, hi, j.get("salary_is_predicted") or "usd")
                    jobs.append({
                        "source": f"adzuna_{country}",
                        "title": j.get("title") or "",
                        "company": (j.get("company") or {}).get("display_name") or "",
                        "location": (j.get("location") or {}).get("display_name") or "",
                        "url": url,
                        "description": desc,
                        "published": (j.get("created") or "")[:10],
                        "remote": bool(re.search(r"\bremote\b", desc, re.I)),
                        "currency": "usd",
                        "salary_min": lo,
                        "salary_max": hi,
                    })
                time.sleep(0.15)
        return jobs
