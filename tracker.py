import json
import os
import time

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


def _load():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"seen": {}, "applied": {}, "sent": {}, "replies": []}


def _ensure(state):
    for key in ("seen", "applied", "sent", "replies"):
        if key not in state:
            state[key] = {} if key != "replies" else []
    return state


def _save(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_seen(url):
    return url in _load()["seen"]


def mark_seen(url, title, company, source):
    state = _ensure(_load())
    if url not in state["seen"]:
        state["seen"][url] = {"title": title, "company": company, "source": source, "first_seen": time.strftime("%Y-%m-%d")}
        _save(state)


def _entry(url, via):
    return f"{url}::{via}" if via else url


def mark_applied(url, via, to="", title="", company=""):
    state = _ensure(_load())
    state["applied"][_entry(url, via)] = {"date": time.strftime("%Y-%m-%d %H:%M"), "via": via, "to": to, "title": title, "company": company}
    _save(state)


def applied(url, via=None):
    state = _load()
    if via:
        return _entry(url, via) in state["applied"]
    return any(k.startswith(url + "::") or k == url for k in state["applied"])


def applied_list():
    state = _load()
    out = []
    for key, info in state["applied"].items():
        url = key.split("::", 1)[0]
        seen = state["seen"].get(url, {})
        out.append({"url": url, "title": seen.get("title", ""), "company": seen.get("company", ""), **info})
    return sorted(out, key=lambda x: x["date"], reverse=True)


def record_sent(url, info):
    state = _ensure(_load())
    state["sent"][url] = info
    _save(state)


def seen_reply(msg_id):
    state = _ensure(_load())
    return any(r.get("msg_id") == msg_id for r in state["replies"])


def record_reply(reply):
    state = _ensure(_load())
    state["replies"].append(reply)
    _save(state)


def reply_count():
    return len(_ensure(_load())["replies"])
