import os
import re
import smtplib
from email.message import EmailMessage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


SKILL_BULLETS = {
    "solidity": "Hands-on <b>Solidity (EVM)</b> development: token contracts, staking, and DeFi logic, tested with Hardhat and Truffle.",
    "smart contract": "Smart contract development and <b>security auditing</b> on EVM chains, with meticulous code review and vulnerability analysis.",
    "smart-contract": "Smart contract development and <b>security auditing</b> on EVM chains, with meticulous code review and vulnerability analysis.",
    "audit": "<b>Security auditing</b> mindset: systematic code review, risk classification, and remediation — the same rigor I applied to ISO 45001 compliance audits.",
    "security": "Security analysis combining risk assessment discipline with smart contract attack-surface review.",
    "blockchain": "Blockchain engineering across Ethereum and Polygon using Web3.js, Hardhat, and Ganache.",
    "web3": "Full Web3 stack: dApp frontends (React/Node.js) wired to smart contracts, with security-first practices.",
    "defi": "DeFi protocol security analysis with focus on reentrancy, access control, and oracle risk classes.",
    "ethereum": "Solidity development and deployment on Ethereum and EVM-compatible chains.",
    "polygon": "Cross-chain Solidity development on Ethereum and Polygon.",
    "token": "ERC-20 / ERC-721 token contract design, implementation, and audit coaching.",
    "crypto": "Deep familiarity with cryptocurrency protocols, wallets, and on-chain tooling.",
    "hardhat": "Day-to-day workflow with Hardhat, Truffle, and Remix for test, deploy, and debug.",
    "foundry": "Solidity development with a focus on test-first smart contract engineering.",
    "truffle": "Day-to-day workflow with Truffle and Ganache for contract lifecycle management.",
    "dapp": "dApp development from contract to React frontend, delivered remotely.",
    "nft": "ERC-721 NFT contract development and marketplace integration experience.",
    "evm": "EVM fundamentals: gas optimization, storage layout, and upgrade patterns.",
    "hse": "16+ years as a Senior HSE Engineer with a 35% reduction in incident rates across 500+ workers.",
    "ehs": "16+ years directing EHS programs across industrial facilities, achieving 98% regulatory compliance.",
    "occupational health": "Occupational health & safety leadership: hygiene programs, exposure control, and workforce wellbeing.",
    "safety engineer": "Senior safety engineering: protocol design, hazard control, and plant-wide training.",
    "safety officer": "Safety program implementation, inspections, and workforce training for industrial teams.",
    "safety manager": "Safety management across multiple facilities: policies, audits, and continuous improvement.",
    "health and safety": "Industrial health & safety program leadership: risk controls, training, and compliance.",
    "industrial hygiene": "Industrial hygiene practice: hazard identification, exposure assessment, and control strategies.",
    "risk assessment": "Risk assessment and hazard analysis for industrial operations with 500+ workers.",
    "iso 45001": "ISO 45001 implementation and audit management with a 98% compliance record.",
    "safety consultant": "Safety consulting: regulatory alignment, policy development, and incident reduction.",
    "workplace safety": "Workplace safety engineering: engineering controls, procedures, and behavior-based training.",
    "hazard analysis": "Hazard analysis and risk matrices applied to complex industrial environments.",
    "incident investigation": "Incident investigation with root-cause analysis and corrective-action closure.",
    "safety compliance": "Compliance auditing, policy development, and regulatory liaison.",
    "osha": "OSHA-aligned safety programs: standards mapping, inspections, and training.",
    "occupational hygiene": "Occupational hygiene assessment: noise, chemical exposure, and ergonomics programs.",
}

DEFAULT_BULLETS = [
    "16+ years of professional experience combining rigorous risk assessment, compliance, and security analysis.",
    "Hands-on <b>Solidity</b> development, <b>smart contract auditing</b>, and <b>DeFi protocol security</b>; familiar with Hardhat, Truffle, Web3.js, and EVM chains.",
    "Track record of reducing incident rates by 35% and achieving 98% regulatory compliance while training 500+ professionals.",
]


def _bullets_for(matched):
    keys = (matched.get("title_hits") or []) + (matched.get("desc_hits") or [])
    bullets, used = [], set()
    for kw in keys:
        norm = kw.lower().strip()
        if norm in used:
            continue
        used.add(norm)
        if norm in SKILL_BULLETS:
            bullets.append(SKILL_BULLETS[norm])
            if len(bullets) >= 3:
                break
    for b in DEFAULT_BULLETS:
        if len(bullets) >= 3:
            break
        bullets.append(b)
    return bullets


def build_letter(job, profile_cfg, candidate, matched):
    name = candidate.get("name") or "Abdolbaset Rahmatpour"
    headline = (profile_cfg.get("headline") or profile_cfg.get("title", "")).rstrip(".")
    company = job.get("company") or "the company"
    location = job.get("location") or "Remote"
    top_hit = ((matched.get("title_hits") or matched.get("desc_hits") or [None])[0]) or "your required area"
    bullets = _bullets_for(matched)
    bullet_html = "".join(f"<li>{b}</li>" for b in bullets)
    links = []
    for key, label in (("linkedin", "LinkedIn"), ("github", "GitHub"), ("website", "Portfolio")):
        if candidate.get(key):
            links.append(f'<a href="{candidate[key]}">{label}</a>')
    links_html = " | ".join(links) if links else ""

    subject = f"{name.split()[0]} {name.split()[-1]} - {job.get('title') or 'Application'}"[:100]

    fa_info = _company_info_fa(job).replace("\n", "<br>")

    body = f"""<html><body dir="ltr" style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222;line-height:1.6">
<p>Hi {company} Hiring Team,</p>
<p>I saw your posting for a <b>{job.get('title')}</b> ({location}) and wanted to say directly: this is exactly the kind of
work I do best. I am <b>{name}</b> — {headline}.</p>
<p><b>Why I'm a strong fit:</b> the role calls for <b>{top_hit}</b>, which is one of my core strengths. Specifically:</p>
<ul>
{bullet_html}
</ul>
<p>I've attached my full CV. I'm fully set up for remote work, can start immediately, and would welcome a 15-minute
call this week to show you how I can deliver from day one. Just reply with a time that suits you.</p>
<p dir="rtl" lang="fa" style="font-family:Tahoma,Arial;background:#f7f7f7;padding:10px;border-radius:6px">
{fa_info}
</p>
<p>Best regards,<br><b>{name}</b><br>Email: {candidate.get('email', '')}<br>Phone: {candidate.get('phone', '')}<br>{links_html}</p>
<p style="color:#888;font-size:12px">Job reference: {job.get('url')}</p>
</body></html>"""
    return subject, body


def build_whatsapp_message(job, profile_cfg, candidate, matched):
    name = candidate.get("name") or "Abdolbaset Rahmatpour"
    headline = (profile_cfg.get("headline") or profile_cfg.get("title", "")).rstrip(".")
    company = job.get("company") or "the company"
    location = job.get("location") or "Remote"
    top_hit = ((matched.get("title_hits") or matched.get("desc_hits") or [None])[0]) or "your required area"
    bullets = _bullets_for(matched)
    bullet_lines = []
    for b in bullets:
        bullet_lines.append("  - " + re_strip_tags(b))
    links = []
    for key, label in (("linkedin", "LinkedIn"), ("github", "GitHub"), ("website", "Portfolio")):
        if candidate.get(key):
            links.append(f"{label}: {candidate[key]}")
    links_text = "\n".join(links) if links else ""

    lines = [
        f"Hello {company} Hiring Team,",
        f"I saw your posting for a {job.get('title')} ({location}) and wanted to say directly: this is exactly the kind of "
        f"work I do best. I am {name} - {headline}.",
        f"Why I'm a strong fit: the role calls for {top_hit}, which is one of my core strengths. Specifically:",
        *bullet_lines,
        "I've attached my full CV. I'm fully set up for remote work, can start immediately, and would welcome a short "
        "call this week to show you how I can deliver from day one.",
        "Best regards,",
        name,
        f"Email: {candidate.get('email', '')}",
        f"Phone: {candidate.get('phone', '')}",
        *([links_text] if links_text else []),
        f"Job reference: {job.get('url')}",
        "",
        _company_info_fa(job),
    ]
    return "\n".join(line for line in lines if line)


def re_strip_tags(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _fa_flags(job):
    parts = []
    if job.get("remote"):
        parts.append("دورکاری (Remote)")
    elif job.get("gulf_onsite"):
        parts.append("حضوری در خاورمیانه/خلیج")
    if job.get("salary_ok"):
        parts.append("حقوق بالا")
    if job.get("salary_str"):
        parts.append("حقوق اعلامی: " + job["salary_str"])
    return parts


def _job_type_fa(job):
    if job.get("remote"):
        return "دورکاری (Remote)"
    if job.get("gulf_onsite"):
        return "حضوری در خاورمیانه/خلیج"
    if job.get("location"):
        return "حضوری"
    return "نامشخص"


def _fa_country(location):
    """ترجمه و تمیزکردن مکان به فارسی (فقط شهر + کشور)."""
    loc = location or ""
    if not loc.strip():
        return "دورکاری"
    parts = [p.strip() for p in re.split(r"[,\u0600-\u06FF]?\s*,\s*", loc) if p.strip()]
    # remove noisy segments (duplicated country words, regions)
    clean = []
    for p in parts:
        low = p.lower()
        if low in ("usa", "united states") or "governorate" in low or "emirate" in low or low in ("uae",):
            continue
        clean.append(p)
    if not clean:
        clean = parts[:1]
    out = ", ".join(clean)
    mapping = [
        ("United Arab Emirates", "امارات متحده عربی"),
        ("UAE", "امارات متحده عربی"),
        ("Abu Dhabi", "ابوظبی"),
        ("Dubai", "دبی"),
        ("Saudi Arabia", "عربستان سعودی"),
        ("Riyadh", "ریاض"),
        ("Jeddah", "جده"),
        ("Mecca", "مکه"),
        ("Basra", "بصره"),
        ("Erbil", "اربیل"),
        ("Baghdad", "بغداد"),
        ("Kurdistan", "کردستان عراق"),
        ("Sulaymaniyah", "سلیمانیه"),
        ("Qatar", "قطر"),
        ("Kuwait", "کویت"),
        ("Bahrain", "بحرین"),
        ("Oman", "عمان"),
        ("Iraq", "عراق"),
        ("Iran", "ایران"),
        ("USA", "ایالات متحده آمریکا"),
        ("United States", "ایالات متحده آمریکا"),
        ("Germany", "آلمان"),
        ("Canada", "کانادا"),
        ("United Kingdom", "انگلستان"),
        ("UK", "انگلستان"),
        ("Netherlands", "هلند"),
        ("Singapore", "سنگاپور"),
        ("Australia", "استرالیا"),
        ("Turkey", "ترکیه"),
        ("Türkiye", "ترکیه"),
        ("India", "هند"),
    ]
    for en, fa in mapping:
        if en.lower() in out.lower():
            out = out.replace(en, fa)
    return out or "دورکاری"


def company_profile_fa(job, company_info=None):
    """گزارش فارسی درباره شغل: نوع کار، مکان، حقوق و مشخصات شرکت."""
    company = job.get("company") or "شرکت کارفرما"
    title = job.get("title") or "این موقعیت"
    location = _fa_country(job.get("location") or "")
    salary = job.get("salary_str") or "نامشخص"
    lines = [
        f"عنوان شغل: {title}",
        f"نوع کار: {_job_type_fa(job)}",
        f"مکان: {location}",
        f"حقوق اعلامی: {salary}",
    ]
    if company_info and company_info.get("about"):
        about = company_info["about"].strip()
        if about:
            lines.append(f"درباره {company}: {about}")
    if job.get("emails"):
        lines.append("ایمیل‌های شرکت: " + ", ".join(job["emails"]))
    if job.get("phones"):
        lines.append("شماره تماس/واتساپ: " + ", ".join(job["phones"]))
    return "\n".join(lines)


def _company_info_fa(job):
    """پاراگراف فارسی درباره شغل و شرکت مقصد."""
    company = job.get("company") or "شرکت کارفرما"
    title = job.get("title") or "این موقعیت"
    location = job.get("location") or "دورکاری"
    source = job.get("source") or ""
    src_fa = {
        "linkedin": "لینکدین",
        "remotive": "Remotive",
        "weworkremotely": "WeWorkRemotely",
        "jobicy": "Jobicy",
        "adzuna": "Adzuna",
    }.get(source.split("_")[0], source)
    flags = _fa_flags(job)
    flag_txt = "، ".join(flags) if flags else ""
    lines = [
        f"اطلاعات موقعیت ({src_fa}):",
        f"شرکت مقصد: {company}",
        f"عنوان شغل: {title}",
        f"محل: {location}",
    ]
    if flag_txt:
        lines.append(flag_txt)
    lines.append(f"لینک آگهی: {job.get('url', '')}")
    if job.get("emails"):
        lines.append("ایمیل درج‌شده در آگهی: " + ", ".join(job["emails"]))
    if job.get("phones"):
        lines.append("شماره تماس درج‌شده در آگهی: " + ", ".join(job["phones"]))
    return "\n".join(lines)


def make_message(sender_name, sender_email, to, subject, html, attachments):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = to
    msg["Reply-To"] = sender_email
    msg.set_content("Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")
    for path in attachments:
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            msg.add_attachment(data, maintype="application", subtype="pdf", filename=os.path.basename(path))
    return msg


def send_via_gmail(user, app_password, msg):
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as srv:
        srv.ehlo()
        srv.starttls()
        srv.ehlo()
        srv.login(user, app_password)
        srv.send_message(msg)


def write_draft(msg, job, index):
    os.makedirs(os.path.join(BASE_DIR, "outbox"), exist_ok=True)
    company = re_safe(job.get("company") or job.get("title") or "job")
    path = os.path.join(BASE_DIR, "outbox", f"{index:02d}_{company}.eml")
    with open(path, "wb") as f:
        f.write(bytes(msg))
    return path


import re as _re


def re_safe(text):
    return _re.sub(r"[^\w\-]+", "_", text)[:60]
