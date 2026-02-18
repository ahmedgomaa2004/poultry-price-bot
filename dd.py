from datetime import datetime

import requests

from price_to_telegram import fetch_white_meat_prices, safe_print

WEBHOOK_URL = "https://discord.com/api/webhooks/1472664114756321494/ca0rws2hONEhdYikZFWNv6ecA3ZRMKNXRf4-OM4HNnUzTYHUWM0Z2ieE6-z3R--GH7i9"


def send_discord_message(text: str) -> None:
    if not WEBHOOK_URL:
        return

    response = requests.post(WEBHOOK_URL, json={"content": text}, timeout=20)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Discord webhook error {response.status_code}: {response.text}"
        )


def main() -> None:
    price, execution_price = fetch_white_meat_prices()
    today = datetime.now().strftime("%Y-%m-%d")
    message = (
        f"\u0633\u0639\u0631 \u0627\u0644\u0644\u062d\u0645 \u0627\u0644\u0627\u0628\u064a\u0636 \u0627\u0644\u064a\u0648\u0645: {price}\n"
        f"\u0633\u0639\u0631 \u0627\u0644\u062a\u0646\u0641\u064a\u0630: {execution_price}\n"
        f"\u062a\u0627\u0631\u064a\u062e \u0627\u0644\u064a\u0648\u0645: {today}"
    )
    safe_print(message)
    send_discord_message(message)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        error_message = (
            "\u062d\u062f\u062b \u062e\u0637\u0623 \u0623\u062b\u0646\u0627\u0621 \u062a\u0634\u063a\u064a\u0644 \u0628\u0648\u062a \u062f\u064a\u0633\u0643\u0648\u0631\u062f.\n"
            f"\u0646\u0648\u0639 \u0627\u0644\u062e\u0637\u0623: {type(err).__name__}\n"
            f"\u062a\u0641\u0627\u0635\u064a\u0644 \u0627\u0644\u062e\u0637\u0623: {err}"
        )
        safe_print(error_message)
        try:
            send_discord_message(error_message)
        except Exception as notify_err:
            safe_print(
                f"\u0641\u0634\u0644 \u0625\u0631\u0633\u0627\u0644 \u0631\u0633\u0627\u0644\u0629 \u0627\u0644\u062e\u0637\u0623: {notify_err}"
            )
        raise
