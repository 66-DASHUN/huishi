import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { parseChangelog } from "@/lib/release";

const webDir = dirname(fileURLToPath(import.meta.url));
const localVersion = readFileSync(resolve(webDir, "../VERSION"), "utf8").trim() || "dev";
const localChangelog = readFileSync(resolve(webDir, "../CHANGELOG.md"), "utf8");

export default function nextConfig(phase: string): NextConfig {
    const isDev = phase === PHASE_DEVELOPMENT_SERVER;
    const releases = parseChangelog(localChangelog);
    const parentOrigins = (process.env.CANVAS_PARENT_ORIGINS || process.env.CANVAS_PARENT_ORIGIN || "https://huishi.local,http://127.0.0.1:8000,http://localhost:8000")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
    const frameAncestors = ["'self'", ...parentOrigins].join(" ");

    return {
        output: "standalone",
        poweredByHeader: false,
        turbopack: {
            root: webDir,
        },
        devIndicators: false,
        allowedDevOrigins: isDev ? ["*.*.*.*"] : [],
        async headers() {
            return [
                {
                    source: "/:path*",
                    headers: [{ key: "Content-Security-Policy", value: `frame-ancestors ${frameAncestors};` }],
                },
            ];
        },
        env: {
            NEXT_PUBLIC_APP_VERSION: localVersion,
            NEXT_PUBLIC_APP_RELEASES: JSON.stringify(releases),
        },
    };
}
