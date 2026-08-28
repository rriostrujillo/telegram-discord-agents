/**
 * BotManager — crea/arranca/para bots desde templates de skills.
 * Cada bot vive en ~/bots/<name>/ con bot.py + .env + .service
 */

import { execSync } from "node:child_process";
import { existsSync, mkdirSync, cpSync, writeFileSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import * as svc from "./serviceManager.js";

const BOTS_DIR = join(homedir(), "bots");
const SKILLS_DIRS = [
  join(homedir(), "documentos/codigo/telegram-discord-agents/skills"),
  join(homedir(), "OpenWork/starter/.opencode/skills"),
];
function findSkillAsset(skill: string, asset: string): string | null {
  for (const d of SKILLS_DIRS) {
    const p = join(d, skill, asset);
    if (existsSync(p)) return p;
  }
  return null;
}

export interface BotSpec {
  name: string;               // slug filesystem
  platform: "telegram" | "discord";
  cli: string;                // opencode | kilocode | claudecode | custom
  model: string;
  token: string;
  allowedUsers: string;       // "8994867,123..."
  workdir: string;
}

export function createBot(spec: BotSpec) {
  const dir = join(BOTS_DIR, spec.name);
  mkdirSync(dir, { recursive: true });

  const skill = spec.platform === "telegram" ? "telegram-bot-factory" : "discord-bot-factory";
  const template = findSkillAsset(skill, "assets/bot_template.py");
  if (template) cpSync(template, join(dir, "bot.py"));
  else throw new Error(`Template no encontrado para skill ${skill}`);

  writeFileSync(join(dir, ".env"), [
    `TELEGRAM_BOT_TOKEN=${spec.token}`,  // el template lee TELEGRAM_BOT_TOKEN o DISCORD_BOT_TOKEN según plataforma
    `DISCORD_BOT_TOKEN=${spec.token}`,
    `ALLOWED_USERS=${spec.allowedUsers}`,
    `AI_BACKEND=${spec.cli}`,
    `AI_MODEL=${spec.model}`,
    `AI_WORKDIR=${spec.workdir}`,
    `AI_TIMEOUT=1800`,
  ].join("\n") + "\n", { mode: 0o600 });

  // .service desde template con sustitución de placeholders
  const svcTpl = findSkillAsset(skill, "assets/bot.service");
  if (svcTpl) {
    let svc = readFileSync(svcTpl, "utf8");
    svc = svc.replaceAll("{{BOT_DIR}}", dir).replaceAll("{{BOT_FILE}}", "bot.py").replaceAll("{{BOT_NAME}}", spec.name);
    const svcPath = join(homedir(), ".config/systemd/user", `${spec.name}.service`);
    mkdirSync(join(homedir(), ".config/systemd/user"), { recursive: true });
    writeFileSync(svcPath, svc);
    svc.daemonReload();
    svc.enableNow(spec.name);
  }
  return dir;
}

export function botStatus(name: string) {
  return svc.isActive(name);
}

export function botLogs(name: string, lines = 50) {
  try {
    if (process.platform !== "win32") {
      return execSync(`journalctl --user -u ${name} --no-pager -n ${lines} 2>/dev/null || journalctl --user -u ${name}-bot --no-pager -n ${lines} 2>/dev/null`, { encoding: "utf8" });
    }
    // Windows: pm2 logs
    return execSync(`pm2 logs ${name} --lines ${lines} --nostream 2>nul`, { encoding: "utf8" });
  } catch { return ""; }
}
