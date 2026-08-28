#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "== Telegram/Discord Agents — installer =="
[ -f "$ROOT/.env" ] || cp "$ROOT/.env.example" "$ROOT/.env" 2>/dev/null || echo -e "TELEGRAM_BOT_TOKEN=\nDISCORD_BOT_TOKEN=\nALLOWED_USERS=\nAI_BACKEND=opencode" > "$ROOT/.env"
echo "· .env listo (completa tus tokens)"
echo "· Detectando CLIs..."
for bin in opencode claude kilo; do
  if which "$bin" >/dev/null 2>&1; then echo "  ✓ $bin $($bin --version 2>/dev/null | head -1)"; else echo "  ○ $bin no instalado"; fi
done
echo "· Prototipo GUI: xdg-open $ROOT/app/gui/index.html"
echo "Listo. Siguiente: edita .env y abre el GUI."
