# Telegram/Discord Agents — Windows installer (espejo de install.sh)
$Root = Split-Path -Parent $PSScriptRoot
Write-Host "== Telegram/Discord Agents — installer (Windows) ==" -ForegroundColor Cyan
if (!(Test-Path "$Root\.env")) { Copy-Item "$Root\.env.example" "$Root\.env"; Write-Host "· .env creado desde .env.example — completa tus tokens" -ForegroundColor Yellow }
else { Write-Host "· .env ya existe" }
Write-Host "· Detectando CLIs..."
foreach ($bin in @("opencode","claude","kilo")) {
  $found = Get-Command $bin -ErrorAction SilentlyContinue
  if ($found) { Write-Host "  ✓ $bin $($found.Source)" -ForegroundColor Green } else { Write-Host "  ○ $bin no instalado" -ForegroundColor DarkGray }
}
Write-Host "· Instalando deps del server..."
Push-Location "$Root\app\server"; npm install; Pop-Location
Write-Host "· Listo. Siguiente:" -ForegroundColor Green
Write-Host "  1. Edita .env con tus tokens"
Write-Host "  2. cd app\server; npm start  # GUI en http://localhost:8899"
Write-Host "  3. Bots quedan como pm2 (pm2 save) o servicio Windows"
