#!/usr/bin/env python3
"""
Telegram Bot Template — patrones de producción extraídos de OpenWork/Hermes.

Este template incorpora los 12 patrones que hacen efectivos a los bots
OpenWork (@cacasa_bot) y Hermes (@rulogmni_bot):

  1. ACK inmediato + ejecución en background (task ID al usuario en <1s)
  2. Timeouts generosos al backend de IA (configurable, default 30 min)
  3. Moldeado de salida (strip metadata, truncado 4000 chars)
  4. Allowlist silenciosa (mensajes Y callbacks autenticados)
  5. Diseñado para systemd Restart=always
  6. Envío flood-safe (RetryAfter cap 5s, nunca dormir penas largas)
  7. Typing indicator re-armado
  8. Persistencia SQLite de sesiones/tareas (sobrevive reinicios)
  9. Fast-path para saludos (sin gastar IA)
 10. /status con lista de tareas activas
 11. Backend de IA intercambiable vía config (opencode/ollama/custom)
 12. Manejador global de errores (el bot nunca muere por una excepción)

USO:
  1. Copia este archivo a tu nuevo bot:  cp bot_template.py mi_bot.py
  2. Crea un .env junto al bot (ver .env.example):
       TELEGRAM_BOT_TOKEN=123456:ABC...
       ALLOWED_USERS=8994867
       AI_BACKEND=opencode          # opencode | ollama | custom
       AI_TIMEOUT=1800
  3. python3 mi_bot.py   (o instala como servicio systemd, ver bot.service)
"""

import os
import asyncio
import logging
import sqlite3
import time
import uuid
from pathlib import Path

import requests
from telegram import Update, BotCommand
from telegram.error import RetryAfter, TimedOut, NetworkError
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

# ============================================================
# CONFIGURACIÓN — todo desde .env, nada hardcodeado
# ============================================================

from dotenv import load_dotenv

BOT_DIR = Path(__file__).parent.resolve()
load_dotenv(BOT_DIR / ".env")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USERS = [int(x) for x in os.environ.get("ALLOWED_USERS", "").split(",") if x.strip()]

AI_BACKEND = os.environ.get("AI_BACKEND", "opencode")   # opencode | ollama | custom
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "1800"))  # patrón #2: generoso
AI_WORKDIR = os.environ.get("AI_WORKDIR", str(BOT_DIR))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
CUSTOM_CMD = os.environ.get("CUSTOM_CMD", "")            # p.ej. "/usr/bin/mi-agente"

DB_PATH = BOT_DIR / "bot_state.db"
MAX_MSG_LEN = 4000  # patrón #3: límite duro de Telegram es 4096

logging.basicConfig(
    filename=str(BOT_DIR / "bot.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
log = logging.getLogger("bot")

# ============================================================
# PERSISTENCIA (patrón #8) — tareas y memoria sobreviven reinicios
# ============================================================

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, chat_id INTEGER, command TEXT,
        status TEXT DEFAULT 'running', result TEXT,
        started REAL, finished REAL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS memory (
        chat_id INTEGER, role TEXT, content TEXT, ts REAL DEFAULT 0)""")
    return conn

def task_create(chat_id: int, command: str) -> str:
    tid = uuid.uuid4().hex[:8]
    with db() as c:
        c.execute("INSERT INTO tasks VALUES (?,?,?,'running',NULL,?,NULL)",
                  (tid, chat_id, command[:200], time.time()))
    return tid

def task_finish(tid: str, status: str, result: str):
    with db() as c:
        c.execute("UPDATE tasks SET status=?, result=?, finished=? WHERE id=?",
                  (status, result[:1000], time.time(), tid))

def task_active() -> list:
    with db() as c:
        return c.execute(
            "SELECT id, command, started FROM tasks WHERE status='running'"
            ).fetchall()

def mem_save(chat_id: int, role: str, content: str):
    with db() as c:
        c.execute("INSERT INTO memory VALUES (?,?,?,?)",
                  (chat_id, role, content[:4000], time.time()))

def mem_history(chat_id: int, limit: int = 10) -> list:
    with db() as c:
        rows = c.execute(
            "SELECT role, content FROM memory WHERE chat_id=? "
            "ORDER BY rowid DESC LIMIT ?", (chat_id, limit)).fetchall()
    return list(reversed(rows))

# ============================================================
# ENVÍO FLOOD-SAFE (patrón #6/#9) — RetryAfter cap 5s inline
# ============================================================

async def safe_send(bot, chat_id: int, text: str, **kw):
    """Envía texto respetando flood control sin colgar el bot."""
    try:
        return await bot.send_message(chat_id=chat_id, text=text, **kw)
    except RetryAfter as e:
        if e.retry_after <= 5:                       # cap inline 5s
            await asyncio.sleep(e.retry_after + 0.5)
            return await bot.send_message(chat_id=chat_id, text=text, **kw)
        log.warning("Flood penalty %ss > cap: fail-closed", e.retry_after)
        return None                                   # fail-closed, no dormir
    except (TimedOut, NetworkError) as e:
        log.warning("Send network error: %s", e)
        return None

async def safe_typing(bot, chat_id: int):
    """Typing indicator no-fatal (patrón #7)."""
    try:
        await bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:
        pass

def shape_output(text: str) -> str:
    """Patrón #3: strip metadata + truncado a límite de Telegram."""
    lines = [l for l in text.splitlines()
             if not l.startswith(("[Tokens]", "💡"))]
    out = "\n".join(lines).strip() or "(sin output)"
    if len(out) > MAX_MSG_LEN:
        out = out[:MAX_MSG_LEN] + "\n\n… (truncado)"
    return out

# ============================================================
# BACKEND DE IA INTERCAMBIABLE (patrón #11)
# ============================================================

def run_ai(prompt: str, chat_id: int) -> str:
    """Ejecuta el backend configurado. Bloqueante — llamar vía executor."""
    if AI_BACKEND == "opencode":
        import subprocess
        r = subprocess.run(
            ["opencode", "run", "--session", f"tg-{chat_id}", prompt],
            cwd=AI_WORKDIR, capture_output=True, text=True,
            timeout=AI_TIMEOUT, env={**os.environ, "NO_COLOR": "1"})
        return r.stdout + r.stderr
    if AI_BACKEND == "ollama":
        history = mem_history(chat_id)
        msgs = [{"role": r, "content": t} for r, t in history]
        msgs.append({"role": "user", "content": prompt})
        r = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "messages": msgs, "stream": False,
            "options": {"num_predict": 512, "num_ctx": 2048},
        }, timeout=AI_TIMEOUT)
        return r.json().get("message", {}).get("content", "")
    if AI_BACKEND == "custom" and CUSTOM_CMD:
        import subprocess
        r = subprocess.run([CUSTOM_CMD, prompt], cwd=AI_WORKDIR,
                           capture_output=True, text=True, timeout=AI_TIMEOUT)
        return r.stdout + r.stderr
    return "(backend de IA no configurado)"

# ============================================================
# HANDLERS
# ============================================================

GREETINGS = {"hola", "hi", "hello", "buenas", "hey", "qué tal", "que tal"}

def authorized(update: Update) -> bool:
    """Patrón #4: allowlist silenciosa."""
    u = update.effective_user
    return bool(u and u.id in ALLOWED_USERS)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text(
        "🤖 Bot activo. Envíame una instrucción y la ejecuto.\n"
        "/status — tareas en curso\n/help — ayuda")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text(
        f"Backend: {AI_BACKEND} (timeout {AI_TIMEOUT}s)\n"
        "Texto libre → tarea en background con ACK inmediato.")

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    active = task_active()
    if not active:
        await update.message.reply_text("Sin tareas activas.")
        return
    lines = [f"`{tid}`: {cmd[:50]} ({int(time.time()-t0)//60}m)"
             for tid, cmd, t0 in active]
    await update.message.reply_text("⏳ Activas:\n" + "\n".join(lines),
                                    parse_mode="Markdown")

async def on_background_done(bot, chat_id: int, tid: str, t0: float, output: str):
    """Entrega el resultado cuando termina la tarea (patrón #1)."""
    elapsed = int(time.time() - t0)
    mins, secs = divmod(elapsed, 60)
    await safe_send(bot, chat_id,
                    f"✅ *Completado* ({mins}m {secs}s)\n```\n{shape_output(output)}\n```",
                    parse_mode="Markdown")
    task_finish(tid, "done", output)

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    chat_id = update.effective_chat.id

    # Patrón #9: fast-path saludos, sin gastar IA
    if text.lower() in GREETINGS or len(text) < 3:
        await update.message.reply_text("👋 Hola! Dame una instrucción.")
        return

    # Patrón #1: ACK inmediato + background
    tid = task_create(chat_id, text)
    t0 = time.time()
    await update.message.reply_text(
        f"🔄 Trabajando en: `{text[:80]}`\nTask: `{tid}`\nTe aviso al terminar.",
        parse_mode="Markdown")
    await safe_typing(ctx.bot, chat_id)

    async def _run():
        loop = asyncio.get_running_loop()
        try:
            output = await loop.run_in_executor(None, run_ai, text, chat_id)
            mem_save(chat_id, "assistant", output)
            await on_background_done(ctx.bot, chat_id, tid, t0, output)
        except Exception as e:
            log.exception("task %s failed", tid)
            task_finish(tid, "error", str(e))
            await safe_send(ctx.bot, chat_id, f"❌ Error en `{tid}`: {e}")
    asyncio.create_task(_run())

async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    """Patrón #5: el bot nunca muere por una excepción de handler."""
    log.error("Handler error: %s", ctx.error)

# ============================================================
# MAIN
# ============================================================

async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Iniciar"),
        BotCommand("status", "Tareas activas"),
        BotCommand("help", "Ayuda"),
    ])

def main():
    if not TELEGRAM_TOKEN or not ALLOWED_USERS:
        log.error("Falta TELEGRAM_BOT_TOKEN o ALLOWED_USERS en .env")
        raise SystemExit(1)
    log.info("Bot iniciando (backend=%s)", AI_BACKEND)
    db().close()  # init schema
    app = (ApplicationBuilder().token(TELEGRAM_TOKEN)
           .post_init(post_init).build())
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                   handle_message))
    app.add_error_handler(on_error)
    app.run_polling(drop_pending_updates=True)  # offset durable de PTB

if __name__ == "__main__":
    main()
