# Telegram / Discord Agents — Consola de Instrumentación

Crea y opera bots de **Telegram** y **Discord** con los 12 patrones de producción de OpenWork/Hermes, y backend de IA intercambiable.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Node](https://img.shields.io/badge/node-%3E%3D18-brightgreen)](https://nodejs.org)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)](https://python.org)

> `git clone` + `.env` + GUI en `http://localhost:8899` — sin rebuild pesado, portable Linux/Windows/macOS.

## ✨ Qué hace

- **GUI en 8899** — dashboard, wizard de creación, switch de modelo en vivo, logs.
- **Skills instrumentados** — `telegram-bot-factory` + `discord-bot-factory` (ACK <1s, background, allowlist, SQLite, flood cap 5s, batching, chunk 2000/4096, Views/slash).
- **CLI Registry** — autodetecta `opencode` / `claudecode` / `kilocode` / `custom` vía `which`/`where` y adapta los dropdowns.
- **Servicios del OS** — los bots quedan como `systemd --user` (Linux) o `pm2` (Windows) con `Restart=always`; puedes matar el GUI y siguen corriendo.

## 🚀 Instalación

```bash
git clone https://github.com/rriostrujillo/telegram-discord-agents.git
cd telegram-discord-agents
./installer/install.sh          # Linux/macOS
# o
.\installer\install.ps1       # Windows (PowerShell)

cp .env.example .env            # pega tus tokens
# edita .env con tu editor

# Opción A: con el server (GUI + API en 8899)
cd app/server && npm install && npm start
# abre http://localhost:8899 — o http://TU_VPN_IP:8899 si es remota

# Opción B: solo prototipo estático (sin API)
xdg-open app/gui/index.html
```

### Requisitos

- Node.js ≥18, Python ≥3.11, `pip`
- Para Discord: `pip install -U discord.py python-dotenv` (o usa `~/.hermes/hermes-agent/venv` si tienes Hermes)
- Para Telegram: `pip install python-telegram-bot python-dotenv`

## 🔑 Tokens

| Plataforma | Dónde |
|---|---|
| Telegram | https://t.me/BotFather → `/newbot` → token `123456:ABC...` + tu user ID |
| Discord | https://discord.com/developers/applications → Bot → Reset Token + tu user ID |

Pégalos en `.env` (o en el wizard de la GUI). **Nunca commitees `.env`** — está en `.gitignore`.

## 📁 Estructura

```
telegram-discord-agents/
├── app/
│   ├── gui/index.html          # dashboard + wizard (sirve en :8899)
│   └── server/src/
│       ├── registry.ts         # which/where + probe
│       ├── serviceManager.ts   # systemd ↔ pm2 ↔ launchd
│       └── botManager.ts       # crea ~/bots/<name>/ + .service
├── skills/
│   ├── telegram-bot-factory/
│   └── discord-bot-factory/
├── config/
│   ├── integrations.json
│   └── bots.example.json
├── installer/
│   ├── install.sh
│   └── install.ps1
└── docs/ARCHITECTURE.md
```

## 🔒 Privacidad

- `.env`, `*.db`, `bots/` están gitignoreados.
- El repo solo trae `.env.example` y `bots.example.json` sin secretos.
- Los bots guardan sesión en SQLite local por chat.

## 📄 Licencia

MIT — ver [LICENSE](LICENSE).
