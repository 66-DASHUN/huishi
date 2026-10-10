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
    // 挂载前缀。生产由部署环境传入（主站同域子路径，如 /canvas-app），
    // 为空则部署在根路径——本地开发与独立域名部署走这条路。
    // 手写路径必须用 @/lib/app-path 的 withBasePath 带上它，Next 只自动
    // 处理 _next/* 与 <Link>/router 的导航目标。
    const basePath = (process.env.CANVAS_BASE_PATH || "").replace(/\/+$/, "");
    const releases = parseChangelog(localChangelog);
    const parentOrigins = (process.env.CANVAS_PARENT_ORIGINS || process.env.CANVAS_PARENT_ORIGIN || "https://huishi.local,http://127.0.0.1:8000,http://localhost:8000")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
    const frameAncestors = ["'self'", ...parentOrigins].join(" ");

    return {
        output: "standalone",
        poweredByHeader: false,
        basePath: basePath || undefined,
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
            // 客户端也要知道前缀：见 src/lib/app-path.ts 的说明。
            NEXT_PUBLIC_CANVAS_BASE_PATH: basePath,
        },
    };
}
