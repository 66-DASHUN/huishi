import { readdir, stat } from "node:fs/promises";
import { extname, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_CHUNKS_DIR = ".next/static/chunks";
const MAX_LARGEST_FILES = 20;

export async function collectBundleReport(chunksDir = DEFAULT_CHUNKS_DIR) {
    const root = resolve(chunksDir);
    const files = await collectFiles(root);
    const assets = [];

    for (const file of files) {
        const extension = extname(file).toLowerCase();
        if (extension !== ".js" && extension !== ".css") continue;
        const details = await stat(file);
        assets.push({
            path: relative(root, file).split(sep).join("/"),
            bytes: details.size,
            type: extension.slice(1),
        });
    }

    assets.sort((left, right) => right.bytes - left.bytes || left.path.localeCompare(right.path));
    const javascript = summarize(assets, "js");
    const stylesheets = summarize(assets, "css");

    return {
        javascript,
        stylesheets,
        totalBytes: javascript.bytes + stylesheets.bytes,
        largest: assets.slice(0, MAX_LARGEST_FILES),
    };
}

async function collectFiles(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    const files = [];
    for (const entry of entries) {
        const path = resolve(directory, entry.name);
        if (entry.isDirectory()) files.push(...(await collectFiles(path)));
        else if (entry.isFile()) files.push(path);
    }
    return files;
}

function summarize(assets, type) {
    const matches = assets.filter((asset) => asset.type === type);
    return { files: matches.length, bytes: matches.reduce((total, asset) => total + asset.bytes, 0) };
}

export function formatBundleReport(report) {
    const lines = [
        `JavaScript: ${report.javascript.bytes} bytes across ${report.javascript.files} files`,
        `CSS: ${report.stylesheets.bytes} bytes across ${report.stylesheets.files} files`,
        `Total: ${report.totalBytes} bytes`,
        "Largest files:",
        ...report.largest.map((asset) => `${asset.bytes}\t${asset.type}\t${asset.path}`),
    ];
    return lines.join("\n");
}

function parseArgs(argv) {
    let chunksDir = DEFAULT_CHUNKS_DIR;
    let json = false;
    for (let index = 0; index < argv.length; index += 1) {
        const argument = argv[index];
        if (argument === "--json") json = true;
        else if (argument === "--dir" && argv[index + 1]) chunksDir = argv[(index += 1)];
        else throw new Error(`Unknown or incomplete argument: ${argument}`);
    }
    return { chunksDir, json };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
    try {
        const { chunksDir, json } = parseArgs(process.argv.slice(2));
        const report = await collectBundleReport(chunksDir);
        process.stdout.write(`${json ? JSON.stringify(report, null, 2) : formatBundleReport(report)}\n`);
    } catch (error) {
        process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
        process.exitCode = 1;
    }
}
