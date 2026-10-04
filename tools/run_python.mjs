import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const candidates = [
  process.env.HUISHI_PYTHON,
  resolve(".venv/bin/python"),
  resolve(".venv/Scripts/python.exe"),
  "python3",
  "python",
].filter(Boolean);

for (const executable of candidates) {
  const result = spawnSync(executable, process.argv.slice(2), { stdio: "inherit" });
  if (result.error?.code === "ENOENT") {
    continue;
  }
  if (result.error) {
    throw result.error;
  }
  process.exit(result.status ?? 1);
}

throw new Error("No Python interpreter found");
