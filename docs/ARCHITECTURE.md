# Telegram / Discord Agents — Arquitectura

> Consola de instrumentación para crear y operar agentes en Telegram y Discord,
> con backend de IA intercambiable (OpenCode, Claude Code, Kilo Code, etc.).
> Repo clonable: `git clone` + `.env` local = todo funciona.

## Objetivo

Un GUI donde cualquier persona que clone el repo pueda:

1. **Instrumentar** bots de Telegram y Discord sin tocar código.
2. **Elegir** el CLI local que ejecuta la inteligencia (opencode / kilocode / claudecode / custom).
3. **Gestionar** modelos (Ox Alpha, Big Pickle, Muse, Gemini, etc.) y hacer switch en vivo.
4. **Instalar** como servicio 24/7 con un click.

## Stack

```
┌─────────────────────────────────────────────┐
│  GUI (Next.js + Tailwind) — puerto 3000     │  ← instrumentación gráfica
│  Instrumentación API (Node + Express)       │  ← orquesta skills + CLIs
└──────────────┬──────────────────────────────┘
               │ spawns / supervisa
     ┌─────────┴──────────┐
     │  Agent Runners     │  ← un proceso por bot (Telegram/Discord)
     │  telegram_runner   │  ← python-telegram-bot, patrones OpenWork/Hermes
     │  discord_runner    │  ← discord.py, websocket + liveness
     └─────────┬──────────┘
               │  subprocess.run  (--model, --session)
     ┌─────────┴──────────────────────────────┐
     │  CLI Registry (pluggable)              │
     │  opencode │ kilocode │ claudecode      │  ← detectados en PATH
     │  + custom CLIs vía config             │
     └────────────────────────────────────────┘
```

## Skills que instrumenta

| Skill | Ruta | Patrones replicados |
|-------|------|---------------------|
| `telegram-bot-factory` | `.opencode/skills/telegram-bot-factory/` | 12 patrones OpenWork/Hermes (ACK, flood cap 5s, SQLite, systemd…) |
| `discord-bot-factory` (a crear) | idem | Adaptados a Discord (2000 chars, Views, slash, threads) |

El GUI no reemplaza los skills — **los orquesta**: genera `.env`, crea `bot.py` desde template, instala el `.service`, muestra logs y permite hot-switch de modelo.

## Integraciones locales

`config/integrations.json` declara CLIs disponibles:

```json
{
  "clis": [
    { "id": "opencode",  "bin": "opencode",  "detect": "which opencode",  "models": "opencode models --json" },
    { "id": "kilocode",  "bin": "kilo",      "detect": "which kilo" },
    { "id": "claudecode","bin": "claude",    "detect": "which claude" },
    { "id": "custom",    "bin": null,        "detect": null }
  ]
}
```

El GUI autodetecta al arrancar (`which <bin>`) y muestra ✓/✗. El usuario elige uno por bot. Cambiar de CLI no requiere reinstalar el bot — solo hot-reload del runner.

## Estructura de carpetas

```
telegram-discord-agents/
├── app/
│   ├── gui/                # Next.js (instrumentación)
│   ├── server/             # Express API (orquestación + spawn)
│   └── shared/             # schema, types
├── skills/                 # submodules o copias de los skills
│   ├── telegram-bot-factory/
│   └── discord-bot-factory/
├── config/
│   ├── integrations.json   # catálogo de CLIs
│   └── bots.example.json   # ejemplo de declaración de bots
├── installer/
│   ├── install.sh          # git clone → npm install → detect CLIs
│   └── doctor.sh           # verifica .env, tokens, systemd
└── docs/
    └── ARCHITECTURE.md     # este archivo
```

## Flujo de uso (GUI)

1. **Dashboard** — lista de bots (Telegram/Discord) con estado (running/stopped), modelo activo, uptime, último error.
2. **Crear bot** — wizard:
   - Plataforma (Telegram | Discord)
   - Token (paste de @BotFather)
   - CLI backend (dropdown autodetectado: OpenCode ✓ / Kilo ✗ / Claude ✓ …)
   - Modelo inicial (dropdown del CLI elegido)
   - Allowlist (user IDs)
   → genera `~/bots/<nombre>/` con `bot.py + .env + .service` y lo arranca.
3. **Detalle de bot** — switch de modelo en vivo (`/modelo` espejado en GUI), ver logs tail, restart/stop, editar prompt del sistema, test de mensaje.
4. **Integraciones** — panel que muestra cada CLI detectado, versión, modelos disponibles, botón “probar” (`<bin> --version` + run de prueba).

## Datos para instalación por terceros

Todo secreto va en `.env` gitignoreado. El repo solo trae:

- `.env.example` con placeholders (`TELEGRAM_BOT_TOKEN=`, `DISCORD_BOT_TOKEN=`, `OPENCODE_API_KEY=`…)
- `config/bots.example.json` sin secretos
- `installer/install.sh` que:
  1. `cp .env.example .env` y pide completar tokens
  2. `npm install` en `app/gui` y `app/server`
  3. detecta CLIs y escribe `config/integrations.json`
  4. `systemctl --user daemon-reload` si hay bots declarados

Quien clona solo necesita: `git clone <repo> && ./installer/install.sh` y abrir `http://localhost:3000`.
