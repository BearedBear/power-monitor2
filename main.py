import sqlite3
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ================== НАЛАШТУВАННЯ ==================
API_KEY = "DAIKSDNG451JNDASDIO98JSXJHDAS123KNCH"
BOT_TOKEN = "8599545336:AAF_WhKHqUO7AVMI-xTLPU9V2cICyVe9OKA"
OWNER_ID = 309647458

RENDER_URL = "https://power-monitor2.onrender.com"
WEBHOOK_PATH = "/webhook"
TIMEOUT = 180  # сек
# ==================================================

app = FastAPI()
bot = Bot(token=BOT_TOKEN)
tg_app = Application.builder().token(BOT_TOKEN).build()

db = sqlite3.connect("data.db", check_same_thread=False)
cur = db.cursor()

# ------------------ БАЗА ------------------
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
# ------------------------------------------


# ================= HEARTBEAT =================
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
    return datetime.utcnow() - last < timedelta(seconds=TIMEOUT), last
# ============================================


# ================= TELEGRAM ==================
def authorized(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text(
        "🤖 Power Monitor онлайн\n\n"
        "Команди:\n"
        "/status — статус світла\n"
        "/today — статистика за сьогодні\n"
        "/last — останнє відключення"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    online, _ = is_online()
    await update.message.reply_text(
        "🟢 Світло Є" if online else "🔴 Світла НЕМАЄ"
    )


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
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
        await update.message.reply_text(
            f"🔌 Останнє відключення:\n"
            f"Початок: {start}\n"
            f"Кінець: {end}\n"
            f"Тривалість: {end - start}"
        )
    else:
        await update.message.reply_text(f"🔴 Світла нема з {start}")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return

    today = datetime.utcnow().date()
    cur.execute("SELECT start_ts, end_ts FROM outages")
    rows = cur.fetchall()

    no_power = timedelta()
    for s, e in rows:
        start = datetime.fromisoformat(s)
        end = datetime.fromisoformat(e) if e else datetime.utcnow()
        if start.date() == today:
            no_power += end - start

    await update.message.reply_text(
        f"⚡ Сьогодні світло було: {timedelta(hours=24) - no_power}"
    )


tg_app.add_handler(CommandHandler("start", cmd_start))
tg_app.add_handler(CommandHandler("status", cmd_status))
tg_app.add_handler(CommandHandler("today", cmd_today))
tg_app.add_handler(CommandHandler("last", cmd_last))
# ============================================


# ================= WEBHOOK ===================
@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, bot)
    await tg_app.process_update(update)
    return {"ok": True}


@app.on_event("startup")
async def startup():
    await tg_app.initialize()          # 🔥 ОЦЕ КЛЮЧ
    await bot.set_webhook(url=RENDER_URL + WEBHOOK_PATH)

# ============================================
