// CSS modules rename a keyframes name used in a module unless the module defines it or wraps it in global(...). A
// renamed name that does not exist never runs, and a Radix popup then waits for an animation end that never comes
// (the dropdown that would not close, 2026-10-16). Every animation in a module must be local or global(...).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f: string) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : p.endsWith(".module.css") ? [p] : [];
  });
}

const KEYWORDS = new Set(["none", "infinite", "both", "forwards", "backwards", "alternate", "linear", "ease", "ease-in",
  "ease-out", "ease-in-out", "normal", "reverse", "running", "paused"]);

describe("animations in CSS modules", () => {
  it("name keyframes that exist", () => {
    const bad: string[] = [];
    for (const f of files(join(__dirname, ".."))) {
      const css = readFileSync(f, "utf8");
      const local = new Set([...css.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1]));
      for (const m of css.matchAll(/animation(?:-name)?\s*:\s*([^;}]+)/g)) {
        const first = m[1].trim().split(/\s+/)[0];
        if (KEYWORDS.has(first) || first.startsWith("global(") || first.startsWith("var(") || local.has(first)) continue;
        bad.push(`${f}: ${first}`);
      }
    }
    expect(bad).toEqual([]);
  });
});
