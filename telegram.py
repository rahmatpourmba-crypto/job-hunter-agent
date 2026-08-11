import requests

MAX_LEN = 4000


def send_message(bot_token, channel_id, text):
    if not bot_token or not channel_id:
        return False, "تنظیمات تلگرام در config.json خالی است"
    if len(text) > MAX_LEN:
        text = text[: MAX_LEN - 3] + "..."
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": channel_id, "text": text},
            timeout=25,
        )
        data = r.json()
        if data.get("ok"):
            return True, ""
        return False, data.get("description", "خطای ناشناخته تلگرام")
    except Exception as e:
        return False, str(e)