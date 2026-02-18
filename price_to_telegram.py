import os
import re
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request

SOURCE_URL = "https://www.elmorshdledwagn.com/"
BOT_TOKEN = "8508240829:AAGjQ5YV1nX92xDsNwKPhAZeymUCSSt0ZW0"
CHAT_ID = "1052952229"

SOURCE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}

# file used to remember the last-seen price values between runs. the
# GitHub Actions workflow commits it back to the repository when it
# changes, so the script can compare subsequent runs.
STATE_PATH = "last_price.json"


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=SOURCE_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def _to_latin_digits(text: str) -> str:
    return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))


def _extract_number(text: str) -> int:
    value_text = _to_latin_digits(text).strip()
    num_match = re.search(r"\d+(?:\.\d+)?", value_text)
    if not num_match:
        raise RuntimeError(f"Value is not numeric: {value_text!r}")
    return int(float(num_match.group()))


def fetch_white_meat_prices() -> tuple[int, int]:
    page_html = fetch_html(SOURCE_URL)

    white_card_match = re.search(
        r"<h5 class=\"card-title\">\s*اللحم\s+ال(?:ابيض|أبيض)\s*</h5>(.{0,1500})",
        page_html,
        flags=re.S,
    )
    if not white_card_match:
        raise RuntimeError("Could not find white meat card on homepage.")

    card_html = white_card_match.group(1)
    fields = re.findall(
        r"<span class=\"text-muted\">\s*([^<]+)\s*</span>\s*<h5 class=\"h1 mt-1 mb-3\">\s*([^<]+)\s*</h5>",
        card_html,
        flags=re.S,
    )
    if not fields:
        raise RuntimeError("Could not extract white meat fields from the card.")

    price = None
    execution_price = None
    for label, raw_value in fields:
        label = label.strip()
        value = _extract_number(raw_value)
        if "سعر" in label:
            price = value
        elif "تنفيذ" in label:
            execution_price = value

    if price is None:
        raise RuntimeError("Could not extract white meat price.")
    if execution_price is None:
        raise RuntimeError("Could not extract white meat execution price.")

    return price, execution_price


def send_telegram_message(text: str) -> None:
    token = BOT_TOKEN or os.getenv("TG_BOT_TOKEN")
    chat_id = CHAT_ID or os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except urllib.error.HTTPError as err:
        details = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API error {err.code}: {details}") from err


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("unicode_escape").decode("ascii"))


def _load_last_prices() -> tuple[int, int] | None:
    """Return previously stored (price, execution_price) or ``None``.

    The state file is expected to be a small JSON object with two
    integer fields. If the file is missing or invalid the function
    logs an informational message and returns ``None`` so the caller can
    treat the run as a first-time execution.
    """
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = f.read()
    except FileNotFoundError:
        return None
    except Exception as err:  # pragma: no cover - unlikely but safe
        safe_print(f"could not read {STATE_PATH}: {err}")
        return None

    try:
        import json

        obj = json.loads(data)
        return obj.get("price"), obj.get("execution_price")
    except Exception as err:  # pragma: no cover - malformed JSON
        safe_print(f"invalid state file {STATE_PATH}: {err}")
        return None


def _save_last_prices(price: int, execution_price: int) -> None:
    """Persist the two values to ``STATE_PATH`` atomically."""
    try:
        import json
        # write to temporary file then rename to avoid partial writes
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"price": price, "execution_price": execution_price}, f)
        os.replace(tmp, STATE_PATH)
    except Exception as err:  # pragma: no cover
        safe_print(f"failed to save state: {err}")


def main() -> None:
    price, execution_price = fetch_white_meat_prices()

    prev = _load_last_prices()
    if prev is not None:
        prev_price, prev_exec = prev
        if (price, execution_price) == (prev_price, prev_exec):
            safe_print("no change in white meat price; skipping notification")
            # still update state to ensure file exists on first good run
            _save_last_prices(price, execution_price)
            return

    today = datetime.now().strftime("%Y-%m-%d")
    message = (
        f"سعر اللحم الابيض اليوم: {price}\n"
        f"سعر التنفيذ: {execution_price}\n"
        f"تاريخ اليوم: {today}"
    )
    safe_print(message)
    send_telegram_message(message)
    _save_last_prices(price, execution_price)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        error_message = (
            "حدث خطأ أثناء تشغيل البوت.\n"
            f"نوع الخطأ: {type(err).__name__}\n"
            f"تفاصيل الخطأ: {err}"
        )
        safe_print(error_message)
        try:
            send_telegram_message(error_message)
        except Exception as notify_err:
            safe_print(f"فشل إرسال رسالة الخطأ: {notify_err}")
        raise
