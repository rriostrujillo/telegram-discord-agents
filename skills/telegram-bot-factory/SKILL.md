---
name: telegram-bot-factory
description: >
  Crea bots de Telegram de producción con los patrones exactos que hacen
  efectivos a OpenWork (@cacasa_bot) y Hermes (@rulogmni_bot): ACK inmediato,
  ejecución en background, allowlist, persistencia SQLite, flood-safety,
  systemd. Usar cuando el usuario pida "crear un bot de telegram",
  "bot interactivo", "vincular bot", "replicar openwork bot" o similar.
---

# Telegram Bot Factory

Sistema para crear vínculos con bots de Telegram tan efectivos como los de
OpenWork o Hermes, basado en ingeniería inversa de ambos (2026-08).

## Arquitectura de referencia (lo que copiamos)

```
Telegram → polling → allowlist → ACK inmediato (<1s)
        → ejecución background (asyncio.create_task + executor)
        → backend IA intercambiable (opencode | ollama | custom)
        → salida moldeada (4000 chars) → entrega al chat
```

## Los 12 patrones obligatorios

| # | Patrón | Por qué |
|---|--------|---------|
| 1 | ACK inmediato + task ID + resultado después | Convierte una tarea de 30 min en "cola con ticket", no en "bot muerto" |
| 2 | Timeout IA generoso (1800s default) | 60s mata trabajo agéntico real |
| 3 | Moldeado de salida: strip metadata, truncado 4000 | Límite duro de Telegram = 4096 |
| 4 | Allowlist silenciosa en mensajes Y callbacks | Bot personal nunca procesa extraños |
| 5 | systemd `Restart=always` `RestartSec=10` | Capa principal de supervivencia |
| 6 | Todo await acotado; errores de red no-fatales | Socket muerto bloquea forever, no lanza error |
| 7 | Typing indicator re-armado tras cada mensaje | Telegram lo limpia al entregar |
| 8 | SQLite para tareas/memoria | Sobrevive reinicios (los dicts en memoria NO) |
| 9 | Fast-path saludos sin IA | Respuesta instantánea, cero costo |
| 10 | `/status` lista tareas activas | Visibilidad de la cola |
| 11 | Backend IA por config (`AI_BACKEND` env) | opencode/ollama/custom sin tocar código |
| 12 | `add_error_handler` global | Una excepción nunca tumba el bot |

## Anti-patrones documentados (incidentes reales de Hermes)

- **NUNCA dormir `retry_after` completo**: un penalty de flood durmió un send
  97 minutos en producción. Cap inline: 5s, luego fail-closed.
- **NUNCA confiar en "no exception" como salud**: salud = round-trip
  getUpdates completado.
- **NUNCA partir mensajes durante streaming** (crea objetivos de edición
  duplicados → bucle infinito). Truncar en streaming, partir solo al final.
- **NUNCA hardcodear tokens** en el código del bot — siempre `.env`.

## Cómo crear un bot nuevo (5 pasos)

```bash
# 1. Crear carpeta del bot
mkdir -p ~/bots/mi-bot && cd ~/bots/mi-bot

# 2. Copiar template
cp {{SKILL_DIR}}/assets/bot_template.py bot.py
cp {{SKILL_DIR}}/assets/bot.service .

# 3. Crear .env (token de @BotFather + tu user id de Telegram)
cat > .env <<'EOF'
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
ALLOWED_USERS=8994867
AI_BACKEND=opencode
AI_TIMEOUT=1800
EOF
chmod 600 .env

# 4. Probar en foreground
python3 bot.py

# 5. Instalar como servicio 24/7
sed -i "s|{{BOT_DIR}}|$PWD|; s|{{BOT_FILE}}|bot.py|; s|{{BOT_NAME}}|mi-bot|" bot.service
mkdir -p ~/.config/systemd/user && cp bot.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now mi-bot
```

## Elegir backend de IA

| Backend | Cuándo | Nota |
|---------|--------|------|
| `opencode` | Tareas agénticas, código, archivos | Sesión persistente por chat vía `--session tg-{chat_id}` |
| `ollama` | Chat local privado, sin API keys | En CPU usar modelo pequeño (smollm2) para chat, grande solo para batch |
| `custom` | Cualquier CLI propio | `CUSTOM_CMD=/ruta/bin` recibe el prompt como arg |

## Escalado posterior (opcional, nivel Hermes)

Cuando el bot básico madure, añadir en este orden:

1. **Reconnect ladder**: backoff exponencial 5→10→20→40→60s, máx 10 intentos,
   luego exit para que systemd recicle (Hermes: adapter.py:2900–3029).
2. **Batching inbound**: fusionar mensajes partidos por Telegram con ventanas
   adaptativas 0.18s/0.24s/0.35s según longitud (adapter.py:9711–9816).
3. **Botones inline de aprobación** con callback data compacta
   `ea:{choice}:{id}`, resolver estado ANTES de renderizar resultado
   (adapter.py:6239–6313).
4. **Fallback IPv4-literal** con SNI preservado si la red es inestable
   (telegram_network.py:55+).

## Referencias en esta máquina

- Template: `.opencode/skills/telegram-bot-factory/assets/bot_template.py`
- OpenWork Gen2 (producción): `~/OpenWork/starter/miniapp/telegram_openwork.py`
- Hermes gold standard: `~/.hermes/hermes-agent/plugins/platforms/telegram/adapter.py`
- Doc de arquitectura completa: `.opencode/skills/openwork-bot-architecture/SKILL.md`
