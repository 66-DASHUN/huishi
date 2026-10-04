import { expect, test } from "bun:test";

test("project card uses semantic theme surfaces", async () => {
    const source = await Bun.file(new URL("./canvas-project-card.tsx", import.meta.url)).text();

    expect(source).toContain("bg-card");
    expect(source).toContain("border-border");
    expect(source).toContain("shadow-xs");
    expect(source).not.toContain("#f1eee8");
    expect(source).not.toContain("stone-");
    expect(source).not.toContain("rounded-2xl");
});

test("desktop controls use the collision-free side rail", async () => {
    const toolbar = await Bun.file(new URL("./canvas-toolbar.tsx", import.meta.url)).text();
    const zoom = await Bun.file(new URL("./canvas-zoom-controls.tsx", import.meta.url)).text();
    const minimap = await Bun.file(new URL("./canvas-mini-map.tsx", import.meta.url)).text();

    expect(toolbar).toContain("data-canvas-side-tools");
    expect(toolbar).toContain('aria-label="画布工具"');
    expect(toolbar).toContain("md:flex-col");
    expect(toolbar).toContain("renderMobileToolbar");
    expect(toolbar).toContain("renderMobileToolbar = true");
    expect(toolbar).toContain("zoomControls: ReactNode | null;");
    expect(toolbar).toContain("left-4");
    expect(toolbar).toContain("top-1/2");
    expect(toolbar).toContain("-translate-y-1/2");
    expect(toolbar).toContain("rounded-xl");
    expect(toolbar).toContain('className="mx-0.5 h-px w-6"');
    expect(toolbar).toContain("onResetView");
    expect(toolbar).toContain("重置视图");
    expect(toolbar).toContain("onClick={() => runMoreAction(onResetView)}");
    expect(toolbar).toContain("getTipY");
    expect(toolbar).toContain("top={tipY}");
    expect(toolbar).not.toContain("data-canvas-main-toolbar");
    expect(toolbar).not.toContain("data-canvas-bottom-rail");
    expect(toolbar).not.toContain("inset-y-0");
    expect(toolbar).not.toContain("h-full");
    expect(toolbar).not.toContain("border-r");
    expect(zoom).toContain('aria-label="选择工具"');
    expect(zoom).toContain('aria-label="小地图"');
    expect(zoom).toContain('aria-label="显示连线"');
    expect(zoom).toContain("showConnections");
    expect(zoom).toContain("Waypoints");
    expect(zoom).not.toContain("Share2");
    expect(zoom).not.toContain('type="range"');
    expect(zoom).not.toContain('aria-label="重置视图"');
    expect(zoom).not.toContain('aria-label="快捷键"');
    expect(zoom).not.toMatch(/className="[^"]*absolute/);
    expect(minimap).toContain("data-canvas-minimap");
    expect(minimap).toContain('className="relative z-50');
    expect(toolbar).toContain('if (id === "tool-assistant") return "画布助手"');
});

test("canvas page mounts the workspace shell and delegates bottom controls", async () => {
    const source = await Bun.file(new URL("../[id]/canvas-client-page.tsx", import.meta.url)).text();

    expect(source).toContain('import { CanvasWorkspaceShell } from "../components/canvas-workspace-shell"');
    expect(source).toContain("<CanvasWorkspaceShell");
    expect(source).toContain("bottomControls=");
    expect(source).toContain("zoomControls={null}");
    expect(source).toContain("const [showConnections, setShowConnections] = useState(true)");
    expect(source).toMatch(/showConnections\s*&&\s*connections/);
    expect(source).toMatch(/showConnections\s*=\s*\{\s*showConnections\s*\}/);
    expect(source).toMatch(/onToggleConnections\s*=\s*\{\s*\(\)\s*=>\s*setShowConnections\(\(value\)\s*=>\s*!value\)\s*\}/);
});

test("node context actions stay compact and limited to existing capabilities", async () => {
    const toolbar = await Bun.file(new URL("./canvas-node-hover-toolbar.tsx", import.meta.url)).text();
    const node = await Bun.file(new URL("./canvas-node.tsx", import.meta.url)).text();
    const config = await Bun.file(new URL("./canvas-config-node-panel.tsx", import.meta.url)).text();

    expect(toolbar).toContain('role="toolbar"');
    expect(toolbar).toContain('aria-label="节点工具"');
    expect(toolbar).toContain("theme.toolbar.panel");
    expect(toolbar).toContain('id: "delete"');
    expect(toolbar).toContain('id: "retry"');
    expect(toolbar).toContain("onPointerDown={(event) => event.stopPropagation()}");
    expect(toolbar).not.toContain("局部重绘");
    expect(toolbar).not.toContain("视频反解");
    expect(toolbar).not.toContain("导演台");

    expect(node).toContain("data-canvas-node-panel");
    expect(config).toContain("canvas-config-mode");
    expect(config).toContain("canvas-compact-control");
});

test("canvas hides the prompt library entry and themes generation controls", async () => {
    const page = await Bun.file(new URL("../[id]/canvas-client-page.tsx", import.meta.url)).text();
    const promptPanel = await Bun.file(new URL("./canvas-node-prompt-panel.tsx", import.meta.url)).text();
    const configPanel = await Bun.file(new URL("./canvas-config-node-panel.tsx", import.meta.url)).text();

    expect(page).not.toContain("data-canvas-prompt-library-anchor");
    expect(page).not.toContain("提示词库");
    expect(promptPanel).not.toContain("CanvasPromptLibrary");
    expect(promptPanel).toContain("ConfigProvider");
    expect(configPanel).toContain("ConfigProvider");
    expect(configPanel).toContain("theme.toolbar.activeBg");
});
