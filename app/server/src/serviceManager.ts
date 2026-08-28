/**
 * ServiceManager — abstrae systemd (Linux) vs nssm/pm2 (Windows) vs launchd (macOS)
 * Los bots son servicios del OS, no hijos del servidor — por eso sobreviven si matas el GUI.
 */
import { execSync } from "node:child_process";
import { platform } from "node:os";

const isWin = platform() === "win32";
const isMac = platform() === "darwin";

function sh(cmd: string, silent = true) {
  try { return execSync(cmd, { encoding: "utf8", stdio: silent ? "pipe" : "inherit" }).trim(); }
  catch { return null; }
}

export function isActive(name: string): string {
  if (!isWin && !isMac) {
    // Linux: systemd user
    for (const cand of [name, `${name}-bot`]) {
      const out = sh(`systemctl --user is-active ${cand} 2>/dev/null`);
      if (out === "active") return "active";
    }
    // fallback: pgrep
    const pgrep = sh(`pgrep -f "bots/${name}/bot.py" 2>/dev/null`);
    if (pgrep) return "active";
    return "inactive";
  }
  if (isWin) {
    // Windows: nssm > sc > pm2
    if (sh(`nssm status ${name} 2>nul`)) return sh(`nssm status ${name}`)?.includes("SERVICE_RUNNING") ? "active" : "inactive";
    if (sh(`sc query ${name} 2>nul`)) return "active";
    const pm2 = sh(`pm2 jlist 2>nul`);
    if (pm2 && pm2.includes(`"${name}"`)) return "active";
    return "inactive";
  }
  // macOS launchd
  const out = sh(`launchctl list 2>/dev/null | grep ${name}`);
  return out ? "active" : "inactive";
}

export function daemonReload() {
  if (!isWin && !isMac) sh("systemctl --user daemon-reload 2>/dev/null");
}

export function enableNow(name: string) {
  if (!isWin && !isMac) {
    sh(`systemctl --user enable --now ${name} 2>/dev/null`);
    // legacy -bot suffix
    sh(`systemctl --user enable --now ${name}-bot 2>/dev/null`);
  } else if (isWin) {
    // pm2 es el más portable en Windows sin admin
    const botPy = `${process.env.USERPROFILE || process.env.HOMEDRIVE || "C:"}\\bots\\${name}\\bot.py`;
    if (sh(`pm2 --version 2>nul`)) sh(`pm2 start "${botPy}" --name ${name} --interpreter python 2>nul`);
    else sh(`nssm install ${name} python "${botPy}" 2>nul`);
    sh(`nssm start ${name} 2>nul`);
  } else {
    sh(`launchctl load ~/Library/LaunchAgents/${name}.plist 2>/dev/null`);
  }
}

export function stop(name: string) {
  if (!isWin && !isMac) { sh(`systemctl --user stop ${name} 2>/dev/null`); sh(`systemctl --user stop ${name}-bot 2>/dev/null`); }
  else if (isWin) { sh(`pm2 stop ${name} 2>nul`); sh(`nssm stop ${name} 2>nul`); }
  else sh(`launchctl unload ~/Library/LaunchAgents/${name}.plist 2>/dev/null`);
}

export function restart(name: string) {
  if (!isWin && !isMac) { sh(`systemctl --user restart ${name} 2>/dev/null`); }
  else if (isWin) { sh(`pm2 restart ${name} 2>nul`); }
  else sh(`launchctl unload ~/Library/LaunchAgents/${name}.plist 2>/dev/null && launchctl load ~/Library/LaunchAgents/${name}.plist 2>/dev/null`);
}
