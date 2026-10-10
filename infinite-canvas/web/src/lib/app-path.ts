/**
 * 应用内的路径前缀。
 *
 * 画布默认挂在主站的同域子路径下（`/canvas-app`），这样用户看到的始终是绘世
 * 的地址，不会出现另一个域名加端口。Next 的 `basePath` 会自动给 `_next/*`
 * 静态资源、`<Link>` 和 `next/navigation` 的路由加上前缀，但**手写的字符串
 * 不会** —— `router.push("/canvas/1")`、`href="/settings"`、`fetch("/webdav-proxy")`
 * 这些必须自己带前缀，否则在子路径部署下会跳到主站的根路径去（404 或串到
 * 主站页面）。这个模块就是那一个出口。
 *
 * 构建时由 `NEXT_PUBLIC_CANVAS_BASE_PATH` 注入；为空表示部署在根路径
 * （本地开发、独立域名部署），此时所有函数退化为原样返回。
 */
const RAW_BASE_PATH = process.env.NEXT_PUBLIC_CANVAS_BASE_PATH || "";

export const APP_BASE_PATH = RAW_BASE_PATH.replace(/\/+$/, "");

/**
 * 给应用内绝对路径加上前缀。
 *
 * 只处理以单个 `/` 开头的路径：外链（`https://…`）、协议相对地址（`//…`）、
 * 相对路径与空串都原样返回，避免把正常的外链改坏。
 */
export function withBasePath(path: string): string {
    if (!APP_BASE_PATH) return path;
    if (!path.startsWith("/") || path.startsWith("//")) return path;
    if (path === "/") return `${APP_BASE_PATH}/`;
    if (path.startsWith(`${APP_BASE_PATH}/`)) return path;
    return `${APP_BASE_PATH}${path}`;
}

/**
 * 去掉 `usePathname()` 结果里可能带的挂载前缀，得到应用内的真实路径。
 *
 * 为什么需要：页面里判断当前位于哪个路由，用的都是应用内路径（`/canvas`、
 * `/prompts`）。挂了 basePath 之后 `usePathname()` 的返回值是否带前缀，
 * 取决于 Next 的版本与渲染路径，不值得依赖。这里统一剥一次：带前缀就剥，
 * 不带就原样——两种情况都得到应用内路径，调用方不必关心。
 */
export function withoutBasePath(pathname: string): string {
    if (!APP_BASE_PATH) return pathname;
    if (pathname === APP_BASE_PATH) return "/";
    if (pathname.startsWith(`${APP_BASE_PATH}/`)) {
        return pathname.slice(APP_BASE_PATH.length);
    }
    return pathname;
}
