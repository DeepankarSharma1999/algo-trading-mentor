// Design lint: fails on banned faces, gradients, emoji, shadow/rounded-card utilities. See DESIGN.md.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
const root = process.argv[2] ?? "src";
const banned = [
  [/font-family:[^;]*\b(Inter|Space Grotesk|Roboto)\b/, "banned typeface"],
  [/\bsystem-ui\b/, "system-ui as a face"],
  [/(?<!repeating-)linear-gradient|radial-gradient|bg-gradient/, "gradient"],
  [/\bshadow-(sm|md|lg|xl|2xl)\b|box-shadow:(?!\s*none)/, "drop shadow"],
  [/\brounded-(xl|2xl|3xl|full)\b/, "rounded card"],
  [/backdrop-blur|backdrop-filter/, "glassmorphism"],
  [/animate-pulse|skeleton/i, "skeleton shimmer"],
  [/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u, "emoji"],
];
let fails = 0;
function walk(d) {
  for (const f of readdirSync(d)) {
    const p = join(d, f);
    if (statSync(p).isDirectory()) { if (f !== "node_modules" && f !== ".next") walk(p); continue; }
    if (!/\.(tsx?|css|mdx?)$/.test(f)) continue;
    const src = readFileSync(p, "utf8");
    src.split("\n").forEach((line, i) => {
      for (const [re, why] of banned) if (re.test(line)) { console.error(`${p}:${i + 1}: ${why}: ${line.trim().slice(0, 80)}`); fails++; }
    });
  }
}
walk(root);
if (fails) { console.error(`design lint: ${fails} violation(s)`); process.exit(1); }
console.log("design lint: clean");
