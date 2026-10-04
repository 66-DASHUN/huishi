import { expect, test } from "bun:test";

test("typecheck does not write incremental build metadata", async () => {
    const packageJson = await Bun.file(new URL("../package.json", import.meta.url)).json();

    expect(packageJson.scripts.typecheck).toBe("tsc --noEmit --incremental false");
});

test("format check ignores current and retained Next.js build directories", async () => {
    const prettierIgnore = await Bun.file(new URL("../.prettierignore", import.meta.url)).text();

    expect(prettierIgnore.split(/\r?\n/)).toContain(".next*");
});
