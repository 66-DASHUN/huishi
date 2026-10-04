import { expect, test } from "bun:test";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { collectBundleReport } from "./report-bundle.mjs";

test("bundle report totals JS and CSS and sorts largest files deterministically", async () => {
    const root = await mkdtemp(join(tmpdir(), "huishi-bundle-"));
    try {
        await mkdir(join(root, "nested"));
        await writeFile(join(root, "small.js"), "123");
        await writeFile(join(root, "nested", "large.js"), "123456");
        await writeFile(join(root, "styles.css"), "1234");
        await writeFile(join(root, "ignored.map"), "123456789");

        const report = await collectBundleReport(root);

        expect(report).toEqual({
            javascript: { files: 2, bytes: 9 },
            stylesheets: { files: 1, bytes: 4 },
            totalBytes: 13,
            largest: [
                { path: "nested/large.js", bytes: 6, type: "js" },
                { path: "styles.css", bytes: 4, type: "css" },
                { path: "small.js", bytes: 3, type: "js" },
            ],
        });
    } finally {
        await rm(root, { recursive: true, force: true });
    }
});

test("package exposes the deterministic bundle report command", async () => {
    const packageJson = await Bun.file(new URL("../package.json", import.meta.url)).json();
    expect(packageJson.scripts["report:bundle"]).toBe("node scripts/report-bundle.mjs");
});
