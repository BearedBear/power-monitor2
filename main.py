import sqlite3
import asyncio
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, HTTPException
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================== НАЛАШТУВАННЯ ==================
API_KEY = "DAIKSDNG451JNDASDIO98JSXJHDAS123KNCH"              # той самий ключ, що в heartbeat.ps1
BOT_TOKEN = "8599545336:AAF_WhKHqUO7AVMI-xTLPU9V2cICyVe9OKA"    # токен з @BotFather
OWNER_ID = 309647458                      # твій Telegram ID (ЧИСЛО!)
TIMEOUT = 180                             # сек, через скільки вважати "нема світла"
CHECK_INTERVAL = 30                       # як часто перевіряти стан
# ==================================================

app = FastAPI()

db = sqlite3.connect("data.db", check_same_thread=False)
cur = db.cursor()

# ------------------ БАЗА ДАНИХ -------------------
cur.execute("""
CREATE TABLE IF NOT EXISTS heartbeat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS outages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts TEXT,
    end_ts TEXT
)
""")
db.commit()
# -------------------------------------------------


# ================== HEARTBEAT API =================
@app.post("/alive")
def alive(x_api_key: str = Header()):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403)

    cur.execute(
        "INSERT INTO heartbeat (ts) VALUES (?)",
        (datetime.utcnow().isoformat(),)
    )
    db.commit()
    return {"ok": True}


def is_online():
    cur.execute("SELECT ts FROM heartbeat ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        return False, None

    last = datetime.fromisoformat(row[0])
    online = datetime.utcnow() - last < timedelta(seconds=TIMEOUT)
    return online, last
# ==================================================


# ================== TELEGRAM ======================
def is_authorized(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🤖 Power Monitor онлайн\n\n"
        "Команди:\n"
        "/status — статус світла\n"
        "/today — статистика за сьогодні\n"
        "/last — останнє відключення"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    online, _ = is_online()
    if online:
        await update.message.reply_text("🟢 Світло Є")
    else:
        await update.message.reply_text("🔴 Світла НЕМАЄ")


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    cur.execute("""
        SELECT start_ts, end_ts FROM outages
        ORDER BY id DESC LIMIT 1
    """)
    row = cur.fetchone()

    if not row:
        await update.message.reply_text("Відключень ще не було")
        return

    start = datetime.fromisoformat(row[0])
    end = datetime.fromisoformat(row[1]) if row[1] else None

    if end:
        duration = end - start
        await update.message.reply_text(
            f"🔌 Останнє відключення:\n"
            f"Початок: {start}\n"
            f"Кінець: {end}\n"
            f"Тривалість: {duration}"
        )
    else:
        await update.message.reply_text(f"🔴 Світла нема з {start}")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    today = datetime.utcnow().date()
    cur.execute("SELECT start_ts, end_ts FROM outages")
    outages = cur.fetchall()

    no_power = timedelta()
    for s, e in outages:
        start = datetime.fromisoformat(s)
        end = datetime.fromisoformat(e) if e else datetime.utcnow()

        if start.date() == today:
            no_power += end - start

    power = timedelta(hours=24) - no_power
    await update.message.reply_text(
        f"⚡ Сьогодні світло було: {power}"
    )
# ==================================================


# ============ МОНИТОРИНГ СТАНУ =====================
async def monitor(application):
    was_online = True

    while True:
        online, _ = is_online()

        if was_online and not online:
            cur.execute(
                "INSERT INTO outages (start_ts) VALUES (?)",
                (datetime.utcnow().isoformat(),)
            )
            db.commit()
            await application.bot.send_message(
                OWNER_ID, "🔴 Світло ЗНИКЛО"
            )

        if not was_online and online:
            cur.execute("""
                UPDATE outages
                SET end_ts = ?
                WHERE end_ts IS NULL
            """, (datetime.utcnow().isoformat(),))
            db.commit()
            await application.bot.send_message(
                OWNER_ID, "🟢 Світло ЗʼЯВИЛОСЬ"
            )

        was_online = online
        await asyncio.sleep(CHECK_INTERVAL)
# ==================================================


# ================== ЗАПУСК БОТА ===================
async def start_bot():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()

    app_tg.add_handler(CommandHandler("start", cmd_start))
    app_tg.add_handler(CommandHandler("status", cmd_status))
    app_tg.add_handler(CommandHandler("today", cmd_today))
    app_tg.add_handler(CommandHandler("last", cmd_last))

    asyncio.create_task(monitor(app_tg))
    await app_tg.run_polling()


@app.on_event("startup")
async def startup():
    asyncio.create_task(start_bot())
# ==================================================
