import { access, cp, mkdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export async function prepareStandalone(projectRoot = ".") {
    const root = resolve(projectRoot);
    const nextDir = resolve(root, ".next");
    const standaloneDir = resolve(nextDir, "standalone");
    const staticSource = resolve(nextDir, "static");
    const staticTarget = resolve(standaloneDir, ".next", "static");
    const publicSource = resolve(root, "public");
    const publicTarget = resolve(standaloneDir, "public");

    await access(resolve(standaloneDir, "server.js"));
    await access(staticSource);
    await rm(staticTarget, { recursive: true, force: true });
    await mkdir(resolve(standaloneDir, ".next"), { recursive: true });
    await cp(staticSource, staticTarget, { recursive: true });

    try {
        await access(publicSource);
        await rm(publicTarget, { recursive: true, force: true });
        await cp(publicSource, publicTarget, { recursive: true });
    } catch (error) {
        if (!(error instanceof Error) || !Object.hasOwn(error, "code") || error.code !== "ENOENT") throw error;
    }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
    try {
        await prepareStandalone();
        process.stdout.write("Standalone assets prepared\n");
    } catch (error) {
        process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
        process.exitCode = 1;
    }
}
