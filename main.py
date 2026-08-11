import argparse
import json
import os
import re
import sys
import time

import job_sources as js
import replies as rp_mod
import resume_parser as rp
import telegram
import tracker
import whatsapp
from emailer import build_letter, build_whatsapp_message, make_message, send_via_gmail, write_draft
from matcher import rank

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def get_profiles(cfg, arg):
    profs = rp.build_profiles(cfg)
    if arg and arg != "all":
        profs = [p for p in profs if p["config"]["id"] == arg]
    return profs


def fetch_jobs(cfg, profile, prof_skills):
    words = profile["config"]["keywords"]
    search_cfg = cfg["search"]
    locations = search_cfg.get("linkedin_locations", [""])
    print("  [لینکدین] در حال جستجو...", flush=True)
    linkedin = js.LinkedInSource().fetch(words, locations, search_cfg["max_days_old"])
    print(f"  [لینکدین] {len(linkedin)} آگهی", flush=True)
    print("  [Remotive] در حال جستجو...", flush=True)
    remotive = js.RemotiveSource().fetch(words, search_cfg["max_days_old"])
    print("  [WeWorkRemotely] در حال جستجو...", flush=True)
    wwr = js.WeWorkRemotelySource().fetch(search_cfg["weworkremotely_feeds"])
    print("  [Jobicy] در حال جستجو...", flush=True)
    jobicy = js.JobicySource().fetch(search_cfg["jobicy_tags"])
    print("  [Adzuna] در حال جستجو...", flush=True)
    adzuna = js.AdzunaSource(cfg["adzuna"]["app_id"], cfg["adzuna"]["app_key"]).fetch(
        words, search_cfg["adzuna_countries"], search_cfg["min_salary_usd"], search_cfg["max_days_old"]
    )
    print("  [GulfTalent] در حال جستجو (خلیج/عراق)...", flush=True)
    gulf = js.GulfTalentSource(cfg.get("gulf", {}).get("countries", [])).fetch(words, search_cfg["max_days_old"])
    print(f"  [GulfTalent] {len(gulf)} آگهی", flush=True)
    all_jobs = linkedin + remotive + wwr + jobicy + adzuna + gulf
    seen = set()
    uniq = []
    for j in all_jobs:
        if j["url"] in seen:
            continue
        seen.add(j["url"])
        uniq.append(j)
    ranked = rank(uniq, profile, cfg)
    for j in ranked:
        if not tracker.is_seen(j["url"]):
            tracker.mark_seen(j["url"], j["title"], j["company"], j["source"])
    return ranked


def cmd_search(cfg, args):
    profs = get_profiles(cfg, args.profile)
    top = args.top or cfg["search"]["top_n"]
    for p in profs:
        pid = p["config"]["id"]
        skills = p["skills"]["matched_skills"]
        print(f"\n=== پروفایل: {p['config']['title']} ===")
        print(f"مهارت‌های استخراج‌شده از رزومه: {len(skills)} مورد")
        ranked = fetch_jobs(cfg, p, skills)
        print(f"آگهی‌های یافت‌شده: {len(ranked)} | نمایش {min(top, len(ranked))} آگهی برتر")
        result_path = os.path.join(BASE_DIR, "results", f"{pid}.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(ranked[: top * 3], f, ensure_ascii=False, indent=2)
        print(f"ذخیره شد: {result_path}")
        posted = 0
        for j in ranked[:top]:
            if not tracker.is_seen(j["url"]):
                continue
            tg_text = (
                f"🎯 {j['title']}\n"
                f"🏢 {j.get('company') or '-'} | 📍 {j.get('location') or '-'}\n"
                f"💰 {j.get('salary_str') or 'نامشخص'}\n"
                f"{'🖥️ دورکاری' if j.get('remote') else ('🏗️ حضوری (خلیج/عراق)' if j.get('gulf_onsite') else '')}\n"
                f"{', '.join('📧 ' + e for e in (j.get('emails') or []))}\n"
                f"{', '.join('📞 ' + p for p in (j.get('phones') or []))}\n"
                f"🔗 {j['url']}\n"
                f"#{pid}"
            )
            if _tg_post(tg_text, silent_ok=True):
                posted += 1
        if posted:
            print(f"{posted} آگهی جدید در تلگرام پست شد.")
        if not ranked:
            print("هیچ آگهی مرتبطی یافت نشد. برای این پروفایل، کلید رایگان Adzuna را تنظیم کنید:")
            print("  python main.py setup")
            continue
        for i, j in enumerate(ranked[:top], 1):
            flags = []
            if j.get("remote"):
                flags.append("دورکاری")
            elif j.get("gulf_onsite"):
                flags.append("حضوری (خلیج/عراق)")
            if j.get("salary_ok"):
                flags.append("حقوق بالا")
            if j.get("emails"):
                flags.append("ایمیل: " + j["emails"][0])
            print(f"\n{i}. [{j['score']} امتیاز] {j['title']}")
            print(f"   شرکت: {j['company'] or '-'} | محل: {j['location'] or '-'} | منبع: {j['source']}")
            print(f"   حقوق: {j.get('salary_str') or 'نامشخص'}")
            print(f"   کلمات کلیدی تیتر: {', '.join(j['title_hits']) or '-'}")
            print(f"   {', '.join(flags)}")
            print(f"   لینک: {j['url']}")


def _tg_post(text, silent_ok=False):
    ok, err = telegram.send_message(cfg_global["telegram"]["bot_token"], cfg_global["telegram"]["channel_id"], text)
    if ok:
        print("پست شد در تلگرام.")
    elif silent_ok:
        pass
    else:
        print(f"تلگرام: {err}")
    return ok


cfg_global = {}


def _letter_text(subject, html):
    plain = re.sub(r"<[^>]+>", " ", html)
    plain = re.sub(r"\s+", " ", plain).strip()
    return f"موضوع: {subject}\nمتن نامه:\n{plain[:2500]}"


def cmd_email(cfg, args):
    profs = get_profiles(cfg, args.profile)
    gmail = cfg["gmail"]
    if args.send and not gmail.get("app_password"):
        print("خطا: برای ارسال واقعی، App Password جیمیل را در config.json تنظیم کنید.")
        print("راهنما: python main.py setup")
        return
    for p in profs:
        pid = p["config"]["id"]
        result_path = os.path.join(BASE_DIR, "results", f"{pid}.json")
        if not os.path.exists(result_path):
            print(f"ابتدا جستجو کنید: python main.py search --profile {pid}")
            continue
        with open(result_path, "r", encoding="utf-8") as f:
            ranked = json.load(f)
        limit = args.limit or cfg["search"]["top_n"]
        sent, drafted = 0, 0
        print(f"\n=== آماده‌سازی نامه‌ها برای پروفایل: {pid} ===")
        for j in ranked[:limit]:
            if tracker.applied(j["url"]):
                continue
            subject, html = build_letter(j, p["config"], cfg["candidate"], j)
            to = (j.get("emails") or [None])[0]
            attachments = ([os.path.join(BASE_DIR, p["config"]["resume_pdf"]) if not os.path.isabs(p["config"]["resume_pdf"]) else p["config"]["resume_pdf"]] if p["config"].get("resume_pdf") else [])
            msg = make_message(cfg["candidate"]["name"], gmail["user"] or cfg["candidate"]["email"], to or "", subject, html, attachments)
            if args.send and to:
                try:
                    send_via_gmail(gmail["user"], gmail["app_password"], msg)
                    tracker.mark_applied(j["url"], "email", to, j.get("title", ""), j.get("company", ""))
                    tracker.record_sent(j["url"], {"subject": subject, "to": to, "date": time.strftime("%Y-%m-%d %H:%M")})
                    sent += 1
                    print(f"ارسال شد -> {j['title']} به {to}")
                    tg_text = (
                        "ایمیل ارسال شد\n"
                        f"عنوان شغل: {j.get('title')}\n"
                        f"شرکت: {j.get('company') or '-'}\n"
                        f"گیرنده: {to}\n"
                        f"ایمیل‌های آگهی: {', '.join(j.get('emails') or []) or '-'}\n"
                        f"واتساپ/تلفن در آگهی: {', '.join(j.get('phones') or []) or 'ندارد'}\n"
                        f"حقوق اعلامی: {j.get('salary_str') or 'نامشخص'}\n"
                        f"لینک: {j.get('url')}\n\n"
                        + _letter_text(subject, html)
                    )
                    _tg_post(tg_text)
                except Exception as e:
                    print(f"خطا در ارسال {j['title']}: {e}")
            else:
                path = write_draft(msg, j, drafted + 1)
                tracker.mark_applied(j["url"], "draft", to or "manual", j.get("title", ""), j.get("company", ""))
                drafted += 1
                target = to or "بدون ایمیل در آگهی"
                print(f"پیش‌نویس -> {j['title']} | گیرنده: {target} | {path}")
        print(f"خلاصه {pid}: {sent} ارسال واقعی، {drafted} پیش‌نویس")
    if not args.send:
        print("\nتوجه: ایمیل‌ها ارسال نشدند (حالت پیش‌نویس). برای ارسال واقعی: python main.py email --send")


def _job_contacts(j):
    parts = []
    if j.get("emails"):
        parts.append("ایمیل: " + ", ".join(j["emails"]))
    if j.get("phones"):
        parts.append("واتساپ/تلفن: " + ", ".join(j["phones"]))
    return "\n".join(parts) or "تماسی در آگهی نیست"


def _require_results(pid):
    result_path = os.path.join(BASE_DIR, "results", f"{pid}.json")
    if not os.path.exists(result_path):
        print(f"ابتدا جستجو کنید: python main.py search --profile {pid}")
        return None
    with open(result_path, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_whatsapp(cfg, args):
    profs = get_profiles(cfg, args.profile)
    limit = args.limit or cfg["search"]["top_n"]
    for p in profs:
        pid = p["config"]["id"]
        ranked = _require_results(pid)
        if ranked is None:
            continue
        sent = 0
        print(f"\n=== ارسال واتساپ برای پروفایل: {pid} ===")
        for j in ranked[:limit]:
            if tracker.applied(j["url"], "whatsapp"):
                continue
            phones = [ph for ph in (j.get("phones") or []) if whatsapp.normalize_number(ph)]
            if not phones:
                print(f"بدون شماره -> {j['title']} (فقط ایمیل: {', '.join(j.get('emails') or []) or 'ندارد'})")
                continue
            number = phones[0]
            msg_text = build_whatsapp_message(j, p["config"], cfg["candidate"], j)
            print(f"ارسال به {number} -> {j['title']} ({j.get('company') or '-'}) ...")
            ok, info = whatsapp.send_whatsapp(
                number, msg_text, cfg.get("whatsapp", {}).get("wait_seconds", 15), cfg.get("whatsapp", {}).get("close_tab", True)
            )
            if not ok:
                print(f"خطا در ارسال به {number}: {info}")
                continue
            tracker.mark_applied(j["url"], "whatsapp", number, j.get("title", ""), j.get("company", ""))
            tracker.record_sent(j["url"], {"kind": "whatsapp", "to": number, "date": time.strftime("%Y-%m-%d %H:%M")})
            sent += 1
            tg_text = (
                "واتساپ ارسال شد\n"
                f"عنوان شغل: {j.get('title')}\n"
                f"شرکت: {j.get('company') or '-'}\n"
                f"شماره: {number}\n"
                f"{_job_contacts(j)}\n"
                f"حقوق اعلامی: {j.get('salary_str') or 'نامشخص'}\n"
                f"لینک: {j.get('url')}\n\n"
                f"متن پیام:\n{msg_text[:1800]}"
            )
            _tg_post(tg_text)
            print(f"ارسال شد -> {j['title']} به {number}")
        print(f"خلاصه {pid}: {sent} ارسال واتساپ")


def cmd_apply(cfg, args):
    for p in get_profiles(cfg, args.profile):
        pid = p["config"]["id"]
        ranked = _require_results(pid)
        if ranked is None:
            continue
        limit = args.limit or cfg["search"]["top_n"]
        gmail = cfg["gmail"]
        if args.send_email and not gmail.get("app_password"):
            print(f"خطا: برای ارسال ایمیل، gmail.app_password را تنظیم کنید (python main.py setup).")
            args.send_email = False
        sent_mail = sent_wa = 0
        print(f"\n=== ارسال درخواست‌ها برای پروفایل: {pid} ===")
        for j in ranked[:limit]:
            to = (j.get("emails") or [None])[0]
            if args.send_email and to and not tracker.applied(j["url"], "email"):
                subject, html = build_letter(j, p["config"], cfg["candidate"], j)
                attachments = ([os.path.join(BASE_DIR, p["config"]["resume_pdf"]) if not os.path.isabs(p["config"]["resume_pdf"]) else p["config"]["resume_pdf"]] if p["config"].get("resume_pdf") else [])
                msg = make_message(cfg["candidate"]["name"], gmail["user"] or cfg["candidate"]["email"], to, subject, html, attachments)
                try:
                    send_via_gmail(gmail["user"], gmail["app_password"], msg)
                    tracker.mark_applied(j["url"], "email", to, j.get("title", ""), j.get("company", ""))
                    tracker.record_sent(j["url"], {"kind": "email", "to": to, "date": time.strftime("%Y-%m-%d %H:%M")})
                    sent_mail += 1
                    _tg_post(
                        "ایمیل ارسال شد\n"
                        f"عنوان شغل: {j.get('title')}\n"
                        f"شرکت: {j.get('company') or '-'}\n"
                        f"گیرنده: {to}\n"
                        f"{_job_contacts(j)}\n"
                        f"حقوق اعلامی: {j.get('salary_str') or 'نامشخص'}\n"
                        f"لینک: {j.get('url')}"
                    )
                    print(f"ایمیل -> {j['title']} به {to}")
                except Exception as e:
                    print(f"خطا در ایمیل {j['title']}: {e}")
            phones = [ph for ph in (j.get("phones") or []) if whatsapp.normalize_number(ph)]
            if args.send_whatsapp and phones and not tracker.applied(j["url"], "whatsapp"):
                msg_text = build_whatsapp_message(j, p["config"], cfg["candidate"], j)
                ok, info = whatsapp.send_whatsapp(
                    phones[0], msg_text, cfg.get("whatsapp", {}).get("wait_seconds", 15), cfg.get("whatsapp", {}).get("close_tab", True)
                )
                if not ok:
                    print(f"خطا در واتساپ {j['title']} به {phones[0]}: {info}")
                    continue
                tracker.mark_applied(j["url"], "whatsapp", phones[0], j.get("title", ""), j.get("company", ""))
                tracker.record_sent(j["url"], {"kind": "whatsapp", "to": phones[0], "date": time.strftime("%Y-%m-%d %H:%M")})
                sent_wa += 1
                _tg_post(
                    "واتساپ ارسال شد\n"
                    f"عنوان شغل: {j.get('title')}\n"
                    f"شرکت: {j.get('company') or '-'}\n"
                    f"شماره: {phones[0]}\n"
                    f"{_job_contacts(j)}\n"
                    f"حقوق اعلامی: {j.get('salary_str') or 'نامشخص'}\n"
                    f"لینک: {j.get('url')}"
                )
                print(f"واتساپ -> {j['title']} به {phones[0]}")
            if not args.send_email and not args.send_whatsapp:
                print(f"پیش‌نویس -> {j['title']} | ایمیل: {to or 'ندارد'} | تلفن: {', '.join(phones) or 'ندارد'}")
        print(f"خلاصه {pid}: {sent_mail} ایمیل، {sent_wa} واتساپ")
    if not args.send_email and not args.send_whatsapp:
        print("\nتوجه: چیزی ارسال نشد. از: python main.py apply --email --whatsapp")


def cmd_reply(cfg, args):
    from_name = args.frm or input("نام/ایمیل فرستنده پاسخ: ").strip()
    body = args.text or input("متن پاسخ (فشرده، ۱-۲ جمله): ").strip()
    if not body:
        print("متن پاسخ خالی است.")
        return
    reply = {
        "msg_id": f"manual-{int(time.time())}",
        "from": from_name,
        "subject": args.job_title or "",
        "body": body,
        "date": time.strftime("%Y-%m-%d %H:%M"),
    }
    tracker.record_reply(reply)
    text = (
        "پاسخ جدید به درخواست شما\n"
        f"از: {reply['from']}\n"
        f"موضوع: {reply['subject'] or '-'}\n"
        f"تاریخ: {reply['date']}\n"
        f"متن:\n{reply['body']}"
    )
    print(text)
    _tg_post(text)
    print(f"ثبت شد. مجموع پاسخ‌ها: {tracker.reply_count()}")


def cmd_status(cfg, args):
    print("\n=== وضعیت درخواست‌ها ===")
    for a in tracker.applied_list():
        print(f"{a['date']} | {a['title']} | {a['company']} | روش: {a['via']} | گیرنده: {a.get('to') or '-'}")
        print(f"   {a['url']}")
    if not tracker.applied_list():
        print("هنوز درخواستی ثبت نشده است.")
    n = tracker.reply_count()
    print(f"\nپاسخ‌های دریافت‌شده: {n} مورد")


def cmd_monitor(cfg, args):
    gmail = cfg["gmail"]
    tg = cfg["telegram"]
    if not gmail.get("app_password"):
        print("خطا: برای پایش پاسخ‌ها، gmail.app_password را در config.json تنظیم کنید.")
        print("راهنما: python main.py setup")
        return
    loop_min = args.loop or cfg["monitor"]["loop_minutes"]
    while True:
        replies = rp_mod.fetch_replies(
            gmail["user"], gmail["app_password"], cfg["monitor"]["check_days"], cfg["candidate"]["name"]
        )
        new = 0
        for r in replies:
            if tracker.seen_reply(r["msg_id"]):
                continue
            tracker.record_reply(r)
            new += 1
            text = (
                "پاسخ جدید به درخواست شما\n"
                f"از: {r['from']}\n"
                f"موضوع: {r['subject']}\n"
                f"تاریخ: {r['date']}\n"
                f"متن:\n{r['body'][:1500]}"
            )
            print(f"\nپاسخ جدید از: {r['from']}")
            print(r["body"][:500])
            _tg_post(text)
        print(f"\nپایش کامل شد: {new} پاسخ جدید، مجموع: {tracker.reply_count()}")
        if not loop_min:
            break
        time.sleep(loop_min * 60)


def cmd_setup(cfg, args):
    print("""
راهنمای راه‌اندازی:
1) جیمیل (برای ارسال ایمیل):
   - تنظیمات گوگل -> امنیت -> تأیید دو مرحله‌ای را فعال کنید
   - سپس به https://myaccount.google.com/apppasswords بروید و یک App Password بسازید
   - آن را در config.json در فیلد gmail.app_password قرار دهید

2) آدزونا (اختیاری ولی مفید برای فیلتر حقوق):
   - رایگان ثبت‌نام کنید: https://developer.adzuna.com/
   - App ID و App Key را در config.json فیلد adzuna قرار دهید

3) لینکدین/گیت‌هاب خود را در config.json فیلد candidate وارد کنید
   تا در نامه‌ها لینک شوند.

4) تلگرام (برای پست خودکار در کانال شما):
   - در تلگرام به @BotFather پیام دهید: /newbot و نام بات را بدهید -> توکن را کپی کنید
   - کانال خود را بسازید (یا از کانال موجود استفاده کنید) و بات را ادمین کنید
   - به بات پیام بدهید، سپس توکن را در آدرس زیر بگذارید:
     https://api.telegram.org/bot<TOKEN>/getUpdates
     از خروجی آن chat.id را بردارید (برای کانال معمولاً منفی است)
   - هر دو را در config.json در فیلد telegram قرار دهید

5) واتساپ (برای ارسال خودکار پیام به شماره‌های درج‌شده در آگهی):
   - کتابخانه pywhatkit نصب می‌شود: pip install -r requirements.txt
   - باید در مرورگر خود (کروم) در web.whatsapp.com لاگین باشید
   - هنگام اجرای `python main.py whatsapp` پنجره مرورگر باز شده و پیام ارسال می‌شود
   - اگر شماره‌ای در آگهی نباشد، فقط ایمیل ارسال می‌شود

دستورات:
  python main.py search              جستجوی مشاغل دورکاری و حقوق‌دار
  python main.py search --profile web3|hse
  python main.py email               ساخت پیش‌نویس نامه‌ها (در پوشه outbox)
  python main.py email --send        ارسال واقعی ایمیل + پست خودکار در تلگرام
  python main.py whatsapp            ارسال واتساپ به شماره‌های درج‌شده + پست در تلگرام
  python main.py apply --email --whatsapp   ارسال همزمان ایمیل و واتساپ + پست در تلگرام
  python main.py reply --frm "نام" --text "متن پاسخ"   ثبت پاسخ دستی و پست در تلگرام
  python main.py monitor             پایش پاسخ‌ها از جیمیل و پست در تلگرام
  python main.py monitor --loop 30   پایش پیوسته هر ۳۰ دقیقه
  python main.py status              پیگیری درخواست‌ها و پاسخ‌ها
""")


def cmd_reset(cfg, args):
    state_path = os.path.join(BASE_DIR, "state.json")
    if os.path.exists(state_path):
        os.remove(state_path)
        print("state.json حذف شد.")
    else:
        print("state.json وجود ندارد.")

def main():
    parser = argparse.ArgumentParser(prog="job-hunter", description="جستجوی مشاغل دورکاری بر اساس رزومه")
    parser.add_argument("--reset", action="store_true", help="حذف فایل وضعیت")
    sub = parser.add_subparsers(dest="cmd")
    sp = sub.add_parser("search")
    sp.add_argument("--profile", default="all")
    sp.add_argument("--top", type=int, default=None)
    se = sub.add_parser("email")
    se.add_argument("--profile", default="all")
    se.add_argument("--limit", type=int, default=None)
    se.add_argument("--send", action="store_true")
    sw = sub.add_parser("whatsapp")
    sw.add_argument("--profile", default="all")
    sw.add_argument("--limit", type=int, default=None)
    sa = sub.add_parser("apply")
    sa.add_argument("--profile", default="all")
    sa.add_argument("--limit", type=int, default=None)
    sa.add_argument("--email", dest="send_email", action="store_true")
    sa.add_argument("--whatsapp", dest="send_whatsapp", action="store_true")
    sr = sub.add_parser("reply")
    sr.add_argument("--frm", default="")
    sr.add_argument("--text", default="")
    sr.add_argument("--job-title", default="")
    sm = sub.add_parser("monitor")
    sm.add_argument("--loop", type=int, default=None)
    sub.add_parser("status")
    sub.add_parser("setup")
    args = parser.parse_args()
    if args.reset:
        cmd_reset(None, None)
        return
    if not args.cmd:
        parser.print_help()
        return
    global cfg_global
    cfg_global = rp.load_config()
    cfg = cfg_global
    env = os.environ
    if env.get("GMAIL_USER"):
        cfg.setdefault("gmail", {})["user"] = env["GMAIL_USER"]
    if env.get("GMAIL_APP_PASSWORD"):
        cfg.setdefault("gmail", {})["app_password"] = env["GMAIL_APP_PASSWORD"]
    if env.get("TG_BOT_TOKEN"):
        cfg.setdefault("telegram", {})["bot_token"] = env["TG_BOT_TOKEN"]
    if env.get("TG_CHANNEL_ID"):
        cfg.setdefault("telegram", {})["channel_id"] = env["TG_CHANNEL_ID"]
    if args.cmd == "search":
        cmd_search(cfg, args)
    elif args.cmd == "email":
        cmd_email(cfg, args)
    elif args.cmd == "whatsapp":
        cmd_whatsapp(cfg, args)
    elif args.cmd == "apply":
        cmd_apply(cfg, args)
    elif args.cmd == "reply":
        cmd_reply(cfg, args)
    elif args.cmd == "monitor":
        cmd_monitor(cfg, args)
    elif args.cmd == "status":
        cmd_status(cfg, args)
    elif args.cmd == "setup":
        cmd_setup(cfg, args)


if __name__ == "__main__":
    main()
