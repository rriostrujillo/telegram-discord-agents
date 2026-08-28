import express from "express";
import cors from "cors";
import { execSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { probeAll } from "./registry.js";
import { createBot, botStatus, botLogs } from "./botManager.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = Number(process.env.PORT || 8899);
const GUI_DIR = join(__dirname, "../../gui");
const BOTS_DIR = join(homedir(), "bots");

app.use(cors());
app.use(express.json());
app.use(express.static(GUI_DIR));

app.get("/api/clis", (_req, res) => res.json(probeAll()));

app.get("/api/bots", (_req, res) => {
  if (!existsSync(BOTS_DIR)) return res.json([]);
  const bots = readdirSync(BOTS_DIR).filter(d => {
    try { return statSync(join(BOTS_DIR, d)).isDirectory(); } catch { return false; }
  }).map(name => {
    let platform = "unknown";
    try {
      const env = readFileSync(join(BOTS_DIR, name, ".env"), "utf8");
      if (env.includes("DISCORD_BOT_TOKEN")) platform = "discord";
      else if (env.includes("TELEGRAM_BOT_TOKEN")) platform = "telegram";
      const py = existsSync(join(BOTS_DIR, name, "bot.py")) ? readFileSync(join(BOTS_DIR, name, "bot.py"), "utf8") : "";
      if (py.includes("discord.py") || py.includes("DISCORD_BOT_TOKEN")) platform = "discord";
    } catch {}
    return { name, platform, status: botStatus(name) };
  });
  res.json(bots);
});

app.post("/api/bots", (req, res) => {
  const { name, platform, cli, model, token, allowedUsers, workdir } = req.body;
  if (!name || !platform || !token) return res.status(400).json({ error: "name, platform, token requeridos" });
  if (!/^[a-z0-9-]+$/.test(name)) return res.status(400).json({ error: "name: solo a-z 0-9 y -" });
  try {
    const dir = createBot({ name, platform, cli: cli || "opencode", model: model || "opencode-zen/big-pickle", token, allowedUsers: allowedUsers || "", workdir: workdir || homedir() });
    res.json({ ok: true, dir });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/api/bots/:name/start", (req, res) => {
  try { execSync(`systemctl --user start ${req.params.name}`, { stdio: "ignore" }); res.json({ ok: true, status: botStatus(req.params.name) }); }
  catch (e:any) { res.status(500).json({ error: e.message }); }
});
app.post("/api/bots/:name/stop", (req, res) => {
  try { execSync(`systemctl --user stop ${req.params.name}`, { stdio: "ignore" }); res.json({ ok: true, status: botStatus(req.params.name) }); }
  catch (e:any) { res.status(500).json({ error: e.message }); }
});
app.post("/api/bots/:name/restart", (req, res) => {
  try { execSync(`systemctl --user restart ${req.params.name}`, { stdio: "ignore" }); res.json({ ok: true, status: botStatus(req.params.name) }); }
  catch (e:any) { res.status(500).json({ error: e.message }); }
});
app.get("/api/bots/:name/logs", (req, res) => {
  res.type("text/plain").send(botLogs(req.params.name, Number(req.query.lines || 80)) || "(sin logs)");
});
app.get("/api/bots/:name/status", (req, res) => res.json({ name: req.params.name, status: botStatus(req.params.name) }));

// SPA fallback
app.get("*", (_req, res) => res.sendFile(join(GUI_DIR, "index.html")));

app.listen(PORT, "0.0.0.0", () => console.log(`✅ TDA server en http://0.0.0.0:${PORT}  (GUI + API)`));
