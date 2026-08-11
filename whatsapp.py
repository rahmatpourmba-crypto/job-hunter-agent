import re

MAX_LEN = 5000


def normalize_number(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) < 10 or len(digits) > 14:
        return None
    return digits


def send_whatsapp(number, message, wait_seconds=15, close_tab=True):
    digits = normalize_number(number)
    if not digits:
        return False, "شماره نامعتبر"
    if len(message) > MAX_LEN:
        message = message[: MAX_LEN - 3] + "..."
    try:
        import pywhatkit

        pywhatkit.sendwhatmsg_instantly(
            "+" + digits,
            message,
            wait_time=wait_seconds,
            tab_close=close_tab,
            close_time=2,
        )
        return True, digits
    except Exception as e:
        return False, str(e)
