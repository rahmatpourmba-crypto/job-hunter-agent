import re

REMOTE_WORDS = [r"\bremote\b", r"work from home", r"fully remote", r"100% remote", r"wfh", r"anywhere in the world", r"distributed team"]
ONSITE_WORDS = [r"onsite", r"on-site", r"in[\s-]office", r"must relocate", r"work from office", r"office[\s-]based", r"hybrid"]

# On-site jobs accepted even when remote_only is on, if located in Gulf / Kurdistan region.
GULF_REGION_WORDS = [
    r"\buae\b", r"united arab emirates", r"dubai", r"abu dhabi", r"sharjah", r"ras al khaimah",
    r"saudi", r"riyadh", r"jeddah", r"dammam", r"qatar", r"doha", r"kuwait", r"bahrain",
    r"oman", r"muscat", r"iraq", r"erbil", r"irbil", r"sulaymaniyah", r"kurdistan", r"kurdish",
    r"basra", r"baghdad", r"middle east",
]

PHONE_RE = re.compile(
    r"(?<![$\d])(?:"
    r"(?:\+?\d{1,3}[\s\-]?)?(?:\(\d{2,4}\)[\s\-]?)?\d{3}[\s\-]?\d{3}[\s\-]?\d{3,4}"
    r"|\(\d{2,4}\)[\s\-]?\d{3}[\s\-]?\d{4}"
    r"|\+?\d{1,3}[\s\-]?\d[\d\s\-]{7,12}\d"
    r")(?![$\d])"
)


def _count(text, patterns):
    n = 0
    for p in patterns:
        n += len(re.findall(p, text or "", re.I))
    return n


def score_job(job, profile_keywords, min_salary_usd, remote_only, exclude_hybrid):
    title = job.get("title") or ""
    desc = job.get("description") or ""
    loc = job.get("location") or ""
    text = f"{title} {desc} {loc}".lower()

    score = 0
    title_hits, desc_hits = [], []

    for kw in profile_keywords:
        k = kw.lower()
        if k in title.lower():
            score += 3
            title_hits.append(kw)
        elif k in text:
            score += 1
            desc_hits.append(kw)

    if not title_hits and len(desc_hits) < 2:
        return None

    remote_ok = bool(job.get("remote"))
    gulf_onsite = False
    if remote_only:
        if remote_ok or _count(text, REMOTE_WORDS):
            score += 2
            remote_ok = True
        elif _count(text, ONSITE_WORDS):
            if exclude_hybrid and "hybrid" in text:
                return None
            if _count(loc, GULF_REGION_WORDS) or _count(text, GULF_REGION_WORDS):
                gulf_onsite = True
            else:
                return None
        elif not remote_ok and (_count(loc, GULF_REGION_WORDS) or _count(text, GULF_REGION_WORDS)):
            gulf_onsite = True
        else:
            return None

    salary_ok = False
    salary_str = ""
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if lo:
        salary_ok = lo >= min_salary_usd
        if salary_ok:
            score += 2
        salary_str = f"${lo:,}"
        if hi:
            salary_str += f"-${hi:,}"
    elif hi:
        salary_ok = hi >= min_salary_usd
        if salary_ok:
            score += 2
        salary_str = f"${hi:,}"

    return {
        "score": score,
        "title_hits": title_hits[:8],
        "desc_hits": desc_hits[:8],
        "remote": remote_ok,
        "gulf_onsite": gulf_onsite,
        "salary_ok": salary_ok,
        "salary_str": salary_str,
        "emails": _extract_emails(desc),
        "phones": _extract_phones(desc),
    }


def _extract_phones(desc):
    out = []
    for m in PHONE_RE.findall(desc or ""):
        digits = re.sub(r"\D", "", m)
        if 10 <= len(digits) <= 14:
            out.append(m)
    return list(dict.fromkeys(out))[:3]


def _extract_emails(desc):
    import re as _re

    pat = _re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    banned = _re.compile(r"no-?reply|donotreply|example\.", _re.I)
    out = []
    for m in pat.findall(desc or ""):
        if not banned.search(m):
            out.append(m)
    return list(dict.fromkeys(out))


def rank(jobs, profile, cfg):
    search = cfg["search"]
    scored = []
    for j in jobs:
        info = score_job(
            j,
            profile["config"]["keywords"],
            search["min_salary_usd"],
            search["remote_only"],
            search["exclude_hybrid"],
        )
        if info is None:
            continue
        if search["min_salary_usd"] and j.get("salary_min") is not None:
            if not info["salary_ok"]:
                continue
        scored.append({**j, **info})
    scored.sort(key=lambda x: (-x["score"], 0 if x["remote"] else (1 if x["gulf_onsite"] else 2), -(x.get("salary_min") or 0)))
    return scored