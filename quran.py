import os
import re
import time
import atexit
import logging
import tempfile
import msvcrt
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== QuranFoundation URLs (Prelive) =====
AUTH_BASE = "https://prelive-oauth2.quran.foundation"
API_BASE  = "https://apis-prelive.quran.foundation"

TG_BOT_TOKEN  = "8026866782:AAGR_JWnit7XSB_jPwgyv_K83GLm7rXFVaA"
QF_CLIENT_ID  = "260586c8-fae0-4832-baeb-192bb7a34506"
QF_CLIENT_SEC = "IopQG964PwLD6_K04Aamut3SNX"

if not TG_BOT_TOKEN or not QF_CLIENT_ID or not QF_CLIENT_SEC:
    raise RuntimeError("Missing env vars: TG_BOT_TOKEN, QF_CLIENT_ID, QF_CLIENT_SECRET")

# ===== Logging =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ===== Single-instance lock (Windows local) =====
_lock_file = None
_lock_path = os.path.join(tempfile.gettempdir(), "quran_bot.lock")

def acquire_single_instance_lock():
    global _lock_file
    _lock_file = open(_lock_path, "w")
    _lock_file.seek(0)
    _lock_file.write("1")
    _lock_file.flush()
    try:
        msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        raise RuntimeError(
            "Another local quran.py instance is already running. Stop it, then start only one instance."
        ) from exc

def release_single_instance_lock():
    global _lock_file
    if not _lock_file:
        return
    try:
        _lock_file.seek(0)
        msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    _lock_file.close()
    _lock_file = None

# ===== Token cache =====
_token = {"value": None, "exp": 0}

def get_token(scope="content") -> str:
    now = time.time()
    if _token["value"] and now < _token["exp"] - 30:
        return _token["value"]

    r = requests.post(
        f"{AUTH_BASE}/oauth2/token",
        auth=(QF_CLIENT_ID, QF_CLIENT_SEC),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": scope},
        timeout=15,
    )
    if r.status_code == 401:
        raise RuntimeError(
            "Quran API auth failed (401). Check QF_CLIENT_ID/QF_CLIENT_SECRET."
        )
    r.raise_for_status()
    data = r.json()
    _token["value"] = data["access_token"]
    _token["exp"] = now + int(data.get("expires_in", 3600))
    return _token["value"]

def qf_get(path: str, params: dict | None = None) -> dict:
    token = get_token("content")
    headers = {"x-auth-token": token, "x-client-id": QF_CLIENT_ID}
    r = requests.get(f"{API_BASE}{path}", headers=headers, params=params, timeout=20)

    # لو التوكن انتهى فجأة
    if r.status_code == 401:
        _token["value"] = None
        token = get_token("content")
        headers["x-auth-token"] = token
        r = requests.get(f"{API_BASE}{path}", headers=headers, params=params, timeout=20)
        if r.status_code == 401:
            raise RuntimeError(
                "Quran API returned 401 after token refresh. Check QF credentials."
            )

    r.raise_for_status()
    return r.json()

# ===== Parsing =====
# Accepts: "2:255" or "1:1-7"
AYAH_RE = re.compile(r"^\s*(\d{1,3})\s*:\s*(\d{1,3})(?:\s*-\s*(\d{1,3}))?\s*$")

def parse_ayah_arg(s: str):
    m = AYAH_RE.match(s or "")
    if not m:
        return None
    ch = int(m.group(1))
    a1 = int(m.group(2))
    a2 = int(m.group(3) or a1)
    if ch < 1 or ch > 114 or a1 < 1 or a2 < a1:
        return None
    return ch, a1, a2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "اكتب:\n"
        "• /ayah 2:255\n"
        "• /ayah 1:1-7\n"
        "اختياري ترجمة:\n"
        "• /ayah 2:255 -t 131"
    )
    await update.message.reply_text(msg)

async def ayah_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Support: /ayah 2:255 -t 131
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("اكتب مثال: /ayah 2:255 أو /ayah 1:1-7")
        return

    # extract translation id (optional)
    trans_id = None
    m = re.search(r"(?:^|\s)-t\s+(\d+)\s*$", text)
    if m:
        trans_id = m.group(1)
        text = re.sub(r"(?:^|\s)-t\s+\d+\s*$", "", text).strip()

    parsed = parse_ayah_arg(text)
    if not parsed:
        await update.message.reply_text("صيغة غلط. استخدم: 2:255 أو 1:1-7")
        return

    chapter, v_from, v_to = parsed

    # Fetch chapter verses (paginate if needed)
    params = {
        "fields": "text_uthmani",
        "per_page": 50,
        "page": 1,
    }
    if trans_id:
        params["translations"] = trans_id

    try:
        picked = []
        page = 1
        while True:
            params["page"] = page
            data = qf_get(f"/content/api/v4/verses/by_chapter/{chapter}", params=params)
            verses = data.get("verses", [])
            if not verses:
                break

            for v in verses:
                vn = v.get("verse_number", 0)
                if v_from <= vn <= v_to:
                    picked.append(v)

            # stop conditions:
            # - we passed the end of range
            if verses[-1].get("verse_number", 0) >= v_to:
                break

            # next page?
            pagination = data.get("pagination") or {}
            if page >= int(pagination.get("total_pages", page)):
                break
            page += 1

            # safety
            if page > 30:
                break
    except RuntimeError as exc:
        logging.error("Quran API auth issue: %s", exc)
        await update.message.reply_text(
            "تعذر جلب الآيات: بيانات Quran API غير صحيحة أو منتهية (401)."
        )
        return
    except requests.Timeout:
        await update.message.reply_text("الخدمة بطيئة حاليًا. حاول مرة ثانية بعد قليل.")
        return
    except requests.RequestException as exc:
        logging.error(
            "Quran API request failed",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        await update.message.reply_text("حصل خطأ أثناء جلب الآيات من الخدمة الخارجية.")
        return

    if not picked:
        await update.message.reply_text("ملقتش الآيات دي. جرّب رقم آية صحيح.")
        return

    # Format
    out_lines = []
    for v in picked:
        vn = v.get("verse_number")
        ar = v.get("text_uthmani", "").strip()
        line = f"*{chapter}:{vn}* — {ar}"

        tr = v.get("translations")
        if tr and isinstance(tr, list) and len(tr) > 0:
            ttxt = (tr[0].get("text") or "").strip()
            if ttxt:
                # Telegram MarkdownV2 is annoying; using Markdown (legacy) here for simplicity
                line += f"\n_{ttxt}_"
        out_lines.append(line)

    # Telegram message length limit ~4096
    msg = "\n\n".join(out_lines)
    if len(msg) <= 3900:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    else:
        # split into chunks
        chunk = ""
        for block in out_lines:
            if len(chunk) + len(block) + 2 > 3900:
                await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
                chunk = block
            else:
                chunk = block if not chunk else (chunk + "\n\n" + block)
        if chunk:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, Conflict):
        logging.error(
            "Telegram Conflict: another process/server is using getUpdates with this token."
        )
        logging.error("Keep exactly one running instance per bot token.")
        context.application.stop_running()
        return
    logging.error(
        "Unhandled error in bot update loop",
        exc_info=(type(err), err, err.__traceback__),
    )

def main():
    acquire_single_instance_lock()
    atexit.register(release_single_instance_lock)
    logging.info("Starting Quran bot polling...")

    app = Application.builder().token(TG_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayah", ayah_cmd))
    app.add_error_handler(on_error)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
