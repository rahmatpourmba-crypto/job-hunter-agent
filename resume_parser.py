import json
import os
import re

from pypdf import PdfReader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _abs_path(path):
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def extract_pdf_text(path):
    path = _abs_path(path)
    if not path or not os.path.exists(path):
        return ""
    try:
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def find_emails(text):
    return list(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")))


def find_phone(text):
    m = re.search(r"(\+?\d[\d\s\-()]{7,}\d)", text or "")
    return m.group(1).strip() if m else ""


def extract_profile(text, profile_id, keywords):
    text = (text or "").lower()
    found = [kw for kw in keywords if kw.lower() in text]
    return {
        "profile_id": profile_id,
        "emails": find_emails(text),
        "phone": find_phone(text),
        "matched_skills": found,
    }


def build_profiles(cfg):
    profiles = []
    for p in cfg["profiles"]:
        text = extract_pdf_text(p["resume_pdf"])
        profile = extract_profile(text, p["id"], p["keywords"])
        if text:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if lines:
                profile["raw_head"] = lines[0]
        if not profile["matched_skills"]:
            profile["matched_skills"] = [kw for kw in p["keywords"] if kw in p["headline"].lower()]
        profiles.append({"config": p, "skills": profile})
    return profiles
