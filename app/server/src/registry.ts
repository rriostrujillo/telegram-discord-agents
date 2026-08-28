/**
 * CLI Registry — detecta CLIs locales (opencode, kilocode, claudecode, custom)
 * y expone modelos disponibles para el GUI.
 */

import { execSync } from "node:child_process";

export type CliId = "opencode" | "kilocode" | "claudecode" | "custom";

export interface CliDef {
  id: CliId;
  label: string;
  bin: string;          // comando en PATH
  modelsCmd?: string;   // comando que lista modelos (opcional)
}

export const CLI_CATALOG: CliDef[] = [
  { id: "opencode",   label: "OpenCode",   bin: "opencode", modelsCmd: "opencode models" },
  { id: "kilocode",   label: "Kilo Code",  bin: "kilo",     modelsCmd: "kilo models" },
  { id: "claudecode", label: "Claude Code",bin: "claude",   modelsCmd: "claude models" },
  { id: "custom",     label: "Custom CLI", bin: "",         modelsCmd: undefined },
];

export interface CliStatus {
  id: CliId;
  label: string;
  bin: string;
  installed: boolean;
  version?: string;
  models: string[];
  error?: string;
}

function which(bin: string): boolean {
  const cmd = process.platform === "win32" ? `where ${bin} 2>nul` : `which ${bin} 2>/dev/null`;
  try { execSync(cmd, { stdio: "ignore" }); return true; } catch { return false; }
}

export function probeCli(def: CliDef): CliStatus {
  if (def.id === "custom") return { ...def, installed: true, models: [] };
  const installed = which(def.bin);
  if (!installed) return { ...def, installed: false, models: [] };
  let version: string | undefined = undefined;
  let models: string[] = [];
  let error: string | undefined = undefined;
  // --version deshabilitado por lentitud (opencode --version tarda 8s) — solo which
  // try { version = execSync(`${def.bin} --version`, { encoding: "utf8", timeout: 3000 }).trim().split("\n")[0]; } catch (e: any) { error = e.message?.slice(0, 200); }
  // models es best-effort y lento (opencode models tarda 30s) — lo dejamos vacío por ahora para no colgar /api/clis
  if (false && def.modelsCmd) {
    try {
      const out = execSync(def.modelsCmd, { encoding: "utf8", timeout: 8000 });
      // opencode models lista texto plano, no JSON
      models = out.split("\n").map(s=>s.trim()).filter(s=>s && !s.startsWith("Available") && !s.startsWith("-"));
      // fallback: si parece JSON, intenta parsear
      try { const j=JSON.parse(out); const arr=Array.isArray(j)?j:j.models??j.data??[]; if(arr.length) models=arr.map((m:any)=>m.id??m.name??String(m)); } catch {}
    } catch { /* modelos es best-effort */ }
  }
  return { ...def, installed, version, models, error };
}

export function probeAll(): CliStatus[] {
  return CLI_CATALOG.map(probeCli);
}
