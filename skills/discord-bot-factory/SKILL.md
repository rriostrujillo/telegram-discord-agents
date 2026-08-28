---
name: discord-bot-factory
description: >
  Crea bots de Discord de producción espejo de telegram-bot-factory:
  websocket + liveness probe, allowlist users/roles/channels, batching
  0.6/2.0s, chunking 2000, Views/Selects, slash commands, SQLite,
  systemd. Usar cuando el usuario pida "crear bot de discord",
  "discord bot", "vincular discord".
---

# Discord Bot Factory — espejo de Telegram

Mismos 12 patrones de OpenWork/Hermes adaptados a Discord.

## Diferencias clave vs Telegram

| Patrón | Telegram | Discord |
|--------|----------|---------|
| Transporte | polling `getUpdates` (PTB) | websocket `discord.py` `Bot.start(token)` |
| Límite mensaje | 4096 | **2000** |
| Batching | 0.18–0.35s adaptativo | **0.6s** normal, **2.0s** si ≥1900 (split-aware) |
| Streaming | drafts animados | `edit` + `overflow_split` (8 chunks cap) |
| Typing | `sendChatAction` | `channel.typing()` loop |
| Control | inline keyboards | **Views** (`discord.ui.View`) + **Slash** (`/modelo /status`) |
| Sesión | per-chat + per-topic | per-channel / per-thread |
| Permisos | `ALLOWED_USERS` | `ALLOWED_USERS` + `ALLOWED_ROLES` + `ALLOWED_CHANNELS` |

## Crear un bot nuevo

```bash
mkdir -p ~/bots/mi-discord-bot && cd ~/bots/mi-discord-bot
cp $(skill-dir)/assets/bot_template.py bot.py
cat > .env <<'EOF'
DISCORD_BOT_TOKEN=MTQ4...  # de Discord Developer Portal
ALLOWED_USERS=602871976784297984
ALLOWED_ROLES=
ALLOWED_CHANNELS=
CLI_BACKEND=opencode
CLI_MODEL=opencode-zen/big-pickle
EOF
chmod 600 .env
python3 bot.py  # prueba
# instalar 24/7: cp assets/bot.service ~/.config/systemd/user/mi-discord-bot.service && systemctl --user enable --now mi-discord-bot
```

El `botManager.ts` del proyecto hace estos pasos automáticamente desde el wizard de la GUI (8899).

## Anti-patrones (de Hermes adapter.py)

- Intents: `message_content=True` y `members` solo si hay usernames/roles en allowlist — sin esto `PrivilegedIntentsRequired` fatal.
- No usar polling — Discord es solo websocket.
- Rate limit: no dormir `retry_after` largo; dedup de previews saturados.

## Referencias

- Template: `assets/bot_template.py`
- Hermes gold standard: `~/.hermes/hermes-agent/plugins/platforms/discord/adapter.py` (10,597 líneas)
- Base común: `gateway/platforms/base.py`
