import { expect, test } from "bun:test";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { prepareStandalone } from "./prepare-standalone.mjs";

test("standalone preparation copies static and public assets", async () => {
    const root = await mkdtemp(join(tmpdir(), "huishi-standalone-"));
    try {
        await mkdir(join(root, ".next", "static", "chunks"), { recursive: true });
        await mkdir(join(root, ".next", "standalone"), { recursive: true });
        await mkdir(join(root, "public"), { recursive: true });
        await writeFile(join(root, ".next", "standalone", "server.js"), "server");
        await writeFile(join(root, ".next", "static", "chunks", "app.js"), "chunk");
        await writeFile(join(root, "public", "logo.txt"), "logo");

        await prepareStandalone(root);

        expect(await readFile(join(root, ".next", "standalone", ".next", "static", "chunks", "app.js"), "utf8")).toBe("chunk");
        expect(await readFile(join(root, ".next", "standalone", "public", "logo.txt"), "utf8")).toBe("logo");
    } finally {
        await rm(root, { recursive: true, force: true });
    }
});

test("production build prepares the standalone output", async () => {
    const packageJson = await Bun.file(new URL("../package.json", import.meta.url)).json();
    expect(packageJson.scripts.build).toBe("next build && node scripts/prepare-standalone.mjs");
});
