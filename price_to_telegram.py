import os
import re
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


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=SOURCE_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def _to_latin_digits(text: str) -> str:
    return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))


def fetch_white_meat_price() -> int:
    page_html = fetch_html(SOURCE_URL)

    white_card_match = re.search(
        r"<h5 class=\"card-title\">\s*اللحم\s+ال(?:ابيض|أبيض)\s*</h5>(.{0,1500})",
        page_html,
        flags=re.S,
    )
    if not white_card_match:
        raise RuntimeError("Could not find white meat card on homepage.")

    price_match = re.search(
        r"<span class=\"text-muted\">\s*سعر\s*</span>\s*<h5 class=\"h1 mt-1 mb-3\">\s*([^<]+)\s*</h5>",
        white_card_match.group(1),
        flags=re.S,
    )
    if not price_match:
        raise RuntimeError("Could not extract white meat price.")

    price_text = _to_latin_digits(price_match.group(1)).strip()
    num_match = re.search(r"\d+(?:\.\d+)?", price_text)
    if not num_match:
        raise RuntimeError(f"White meat price is not numeric: {price_text!r}")

    return int(float(num_match.group()))


def send_telegram_message(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except urllib.error.HTTPError as err:
        details = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API error {err.code}: {details}") from err


def main() -> None:
    price = fetch_white_meat_price()
    message = f"سعر اللحم الابيض اليوم: {price}"
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("unicode_escape").decode("ascii"))
    send_telegram_message(message)


if __name__ == "__main__":
    main()
