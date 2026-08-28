#!/usr/bin/env python3
"""
Discord Bot Template — espejo de telegram-bot-factory.
Patrones Hermes: websocket + liveness, batching split-aware, chunk 2000,
Views/Slash, allowlist users/roles/channels, SQLite, systemd.

Requiere: pip install -U discord.py python-dotenv
  (usa el venv de Hermes si lo tienes: ~/.hermes/hermes-agent/venv/bin/python)
"""
import os, asyncio, logging, sqlite3, time, re
from pathlib import Path

from dotenv import load_dotenv
import discord
from discord.ext import commands

BOT_DIR = Path(__file__).parent.resolve()
load_dotenv(BOT_DIR / ".env")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
ALLOWED_USERS = {x.strip() for x in os.environ.get("ALLOWED_USERS","").split(",") if x.strip()}
ALLOWED_ROLES = {x.strip() for x in os.environ.get("ALLOWED_ROLES","").split(",") if x.strip()}
ALLOWED_CHANNELS = {x.strip() for x in os.environ.get("ALLOWED_CHANNELS","").split(",") if x.strip()}
CLI_BACKEND = os.environ.get("CLI_BACKEND", "opencode")
CLI_MODEL = os.environ.get("CLI_MODEL", "opencode-zen/big-pickle")
WORKDIR = os.environ.get("AI_WORKDIR", str(BOT_DIR))
DB_PATH = BOT_DIR / "bot_state.db"
MAX_LEN = 2000  # Discord hard limit

MODELS = {
    "mimo":   {"id": "opencode-zen/mimo-v2.5-free", "label": "⚡ MiMo Free"},
    "pickle": {"id": "opencode-zen/big-pickle",     "label": "🥒 Big Pickle"},
    "laguna": {"id": "opencode-zen/laguna-s-2.1-free","label": "🎨 Laguna Free"},
}
DEFAULT_MODEL = "pickle"

logging.basicConfig(filename=str(BOT_DIR/"bot.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discord-bot")

# ── SQLite ───────────────────────────────────────────────────────
def db():
    c = sqlite3.connect(str(DB_PATH))
    c.execute("CREATE TABLE IF NOT EXISTS prefs (chat_id TEXT PRIMARY KEY, model TEXT, session_id TEXT, updated REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS memory (chat_id TEXT, role TEXT, content TEXT, ts REAL)")
    return c

def get_model(chat_id: str) -> str:
    with db() as c:
        r = c.execute("SELECT model FROM prefs WHERE chat_id=?", (chat_id,)).fetchone()
    return r[0] if r else DEFAULT_MODEL

def set_model(chat_id: str, k: str):
    with db() as c:
        c.execute("INSERT INTO prefs(chat_id,model,updated) VALUES(?,?,?) ON CONFLICT(chat_id) DO UPDATE SET model=?,updated=?",
                  (chat_id,k,time.time(),k,time.time()))

def get_session(chat_id: str):
    with db() as c:
        r = c.execute("SELECT session_id FROM prefs WHERE chat_id=?", (chat_id,)).fetchone()
    return r[0] if r and r[0] else None

def set_session(chat_id: str, sid):
    with db() as c:
        # asegura fila existe
        c.execute("INSERT INTO prefs(chat_id,model,updated,session_id) VALUES(?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET session_id=?",
                  (chat_id, get_model(chat_id), time.time(), sid, sid))

# ── Allowlist (users/roles/channels) ─────────────────────────────
def is_allowed(msg: discord.Message) -> bool:
    if not ALLOWED_USERS and not ALLOWED_ROLES and not ALLOWED_CHANNELS:
        return True  # sin restricción
    uid = str(msg.author.id)
    if uid in ALLOWED_USERS:
        return True
    # roles (requiere members intent)
    if ALLOWED_ROLES and hasattr(msg.author, "roles"):
        if any(str(r.id) in ALLOWED_ROLES for r in getattr(msg.author, "roles", [])):
            return True
    # canales
    if ALLOWED_CHANNELS:
        keys = {str(msg.channel.id), getattr(msg.channel, "name", ""), f"{msg.guild.name} / #{msg.channel.name}" if msg.guild else ""}
        if keys & ALLOWED_CHANNELS or "*" in ALLOWED_CHANNELS:
            return True
        return False
    return False

# ── CLI runner (mismo que Telegram) ─────────────────────────────
def _list_newest_session():
    import subprocess, re
    r = subprocess.run(["opencode","session","list"], capture_output=True, text=True, timeout=120, env={**os.environ,"NO_COLOR":"1"})
    m = re.search(r"(ses_[A-Za-z0-9]+)", r.stdout)
    return m.group(1) if m else None

def run_ai(prompt: str, chat_id: str, model_key: str) -> str:
    import subprocess
    mid = MODELS.get(model_key, MODELS[DEFAULT_MODEL])["id"]
    # override por CLI_MODEL si el usuario fijó uno custom en .env
    if CLI_MODEL and "/" in CLI_MODEL:
        mid = CLI_MODEL
    env = {**os.environ, "NO_COLOR":"1"}
    def _run(sess):
        cmd = ["opencode","run","--model",mid]
        if sess: cmd += ["--session",sess]
        cmd.append(prompt)
        return subprocess.run(cmd, cwd=WORKDIR, capture_output=True, text=True, timeout=1800, env=env)
    sid = get_session(chat_id)
    if sid:
        r = _run(sid)
        if "Session not found" in (r.stdout+r.stderr):
            set_session(chat_id, None)
            sid = None
    if not sid:
        r = _run(None)
        ns = _list_newest_session()
        if ns: set_session(chat_id, ns)
    return r.stdout + r.stderr

def shape(t: str) -> str:
    t = "\n".join(l for l in t.splitlines() if not l.startswith(("[Tokens]","[claude-mem]")))
    t = t.strip() or "(sin output)"
    return t

def chunk2000(t: str):
    # 2000 cap, 8 chunks max (Hermes #86581)
    chunks, cur = [], ""
    for para in t.split("\n\n"):
        if len(cur)+len(para)+2 <= MAX_LEN:
            cur += ("\n\n" if cur else "")+para
        else:
            if cur: chunks.append(cur)
            cur = para
            if len(cur) > MAX_LEN:  # para enano muy largo
                while len(cur) > MAX_LEN:
                    chunks.append(cur[:MAX_LEN]); cur = cur[MAX_LEN:]
            if len(chunks) >= 7:
                # último chunk truncado con aviso
                remaining = len("\n\n".join([cur]+[para]))
                chunks.append(cur[:MAX_LEN-80] + f"\n\n⚠️ truncado — {remaining} chars no entregados")
                return chunks[:8]
    if cur: chunks.append(cur)
    return chunks[:8]

# ── Bot ──────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
intents.guild_messages = True
# members solo si hay roles/usernames en allowlist
if ALLOWED_ROLES or any(not x.isdigit() for x in ALLOWED_USERS):
    intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---- /modelo View ----
class ModelView(discord.ui.View):
    def __init__(self, chat_id: str):
        super().__init__(timeout=300)
        self.chat_id = chat_id
        cur = get_model(chat_id)
        for k,m in MODELS.items():
            label = m["label"] + (" ✅" if k==cur else "")
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.success if k==cur else discord.ButtonStyle.secondary, custom_id=k)
            async def _cb(inter, k=k):
                if str(inter.user.id) not in ALLOWED_USERS and ALLOWED_USERS:
                    return await inter.response.send_message("⛔ No autorizado", ephemeral=True)
                set_model(self.chat_id, k)
                set_session(self.chat_id, None)  # sesión atada al modelo anterior
                await inter.response.edit_message(content=f"🔀 Modelo → {MODELS[k]['label']}\n`{MODELS[k]['id']}`\nSesión reiniciada.", view=None)
            btn.callback = _cb
            self.add_item(btn)

@bot.event
async def on_ready():
    log.info("Conectado como %s (%s)", bot.user, bot.user.id)
    try:
        # registra slash /modelo y /status
        bot.tree.add_command(discord.app_commands.Command(name="modelo", description="Cambiar modelo IA", callback=slash_modelo))
        bot.tree.add_command(discord.app_commands.Command(name="status", description="Ver modelo activo", callback=slash_status))
        await bot.tree.sync()
        log.info("Slash sync OK")
    except Exception as e:
        log.warning("Slash sync: %s", e)
    print(f"✅ Discord bot {bot.user} listo — allowlist {ALLOWED_USERS or 'abierto'}")

async def slash_modelo(inter: discord.Interaction):
    if ALLOWED_USERS and str(inter.user.id) not in ALLOWED_USERS:
        return await inter.response.send_message("⛔ No autorizado", ephemeral=True)
    chat_id = str(inter.channel_id)
    await inter.response.send_message(f"Modelo actual: {MODELS[get_model(chat_id)]['label']}", view=ModelView(chat_id), ephemeral=True)

async def slash_status(inter: discord.Interaction):
    chat_id = str(inter.channel_id)
    m = MODELS[get_model(chat_id)]
    await inter.response.send_message(f"📊 {m['label']}\n`{m['id']}`", ephemeral=True)

# ---- batching split-aware ----
_pending = {}  # chat_id -> {text, task}
SPLIT_DELAY = 2.0
NORMAL_DELAY = 0.6

async def _flush(chat_id: str):
    await asyncio.sleep(SPLIT_DELAY if len(_pending[chat_id]["text"]) >= 1900 else NORMAL_DELAY)
    data = _pending.pop(chat_id, None)
    if not data: return
    await _dispatch(data["msg"], data["text"])

def _enqueue(msg: discord.Message, text: str):
    cid = str(msg.channel.id)
    if cid in _pending:
        _pending[cid]["text"] += "\n" + text
        _pending[cid]["msg"] = msg
        _pending[cid]["task"].cancel()
    else:
        _pending[cid] = {"text": text, "msg": msg, "task": None}
    _pending[cid]["task"] = asyncio.create_task(_flush(cid))

async def _dispatch(msg: discord.Message, text: str):
    cid = str(msg.channel.id)
    model_key = get_model(cid)
    # typing loop
    async with msg.channel.typing():
        try:
            loop = asyncio.get_running_loop()
            out = await loop.run_in_executor(None, run_ai, text, cid, model_key)
        except Exception as e:
            await msg.reply(f"❌ Error: {e}\nPrueba `!modelo`")
            return
    # error del servidor Zen
    if "UnknownError" in out or "Unexpected server error" in out:
        await msg.reply(f"❌ {MODELS[model_key]['label']} caído en Zen. Usa `!modelo` y cambia.")
        return
    if "is not supported" in out:
        set_session(cid, None)
        await msg.reply(f"❌ Modelo no soportado en esta sesión — limpiada. Reenvía tu mensaje.")
        return
    # chunk 2000 + overflow
    t = shape(out)
    chunks = chunk2000(t)
    first = True
    last_msg = None
    for ch in chunks:
        try:
            if first:
                last_msg = await msg.reply(ch)
                first = False
            else:
                last_msg = await msg.channel.send(ch, reference=last_msg.to_reference() if last_msg else None)
        except discord.errors.HTTPException as e:
            if e.code in (50035, 10008):  # mensaje muy largo o desconocido → sin reference
                last_msg = await msg.channel.send(ch[:MAX_LEN])
            else:
                raise

@bot.event
async def on_message(msg: discord.Message):
    if msg.author.bot:
        return
    if not is_allowed(msg):
        return
    # comandos
    if msg.content.strip() == "!modelo":
        return await msg.reply("Elige modelo:", view=ModelView(str(msg.channel.id)))
    if msg.content.strip() == "!status":
        m = MODELS[get_model(str(msg.channel.id))]
        return await msg.reply(f"📊 {m['label']}\n`{m['id']}`")
    # ignora otros prefijos
    if msg.content.startswith("!"):
        return
    # batching: si es texto largo, encola; si no, dispatch directo
    text = msg.content.strip()
    if not text and not msg.attachments:
        return
    # adjuntos: solo texto por ahora
    if len(text) < 500:
        await _dispatch(msg, text)
    else:
        _enqueue(msg, text)
    await bot.process_commands(msg)

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Falta DISCORD_BOT_TOKEN en .env")
    bot.run(TOKEN)
