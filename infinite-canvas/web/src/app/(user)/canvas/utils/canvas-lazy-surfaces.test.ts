import { expect, test } from "bun:test";

test("heavy canvas surfaces are dynamically imported and mounted only when open", async () => {
    const source = await Bun.file(new URL("../[id]/canvas-client-page.tsx", import.meta.url)).text();

    expect(source).toContain('import dynamic from "next/dynamic"');
    expect(source).toContain('dynamic(() => import("../components/canvas-assistant-panel")');
    expect(source).toContain('dynamic(() => import("../components/asset-picker-modal")');
    expect(source).not.toMatch(/import \{[^}]*CanvasAssistantPanel[^}]*\} from "\.\.\/components\/canvas-assistant-panel"/s);
    expect(source).not.toMatch(/import \{[^}]*AssetPickerModal[^}]*\} from "\.\.\/components\/asset-picker-modal"/s);
    expect(source).toContain("{assistantMounted ? (");
    expect(source).toContain("{assetPickerOpen ? <AssetPickerModal");
    expect(source).not.toContain("promptLibraryOpen");
    expect(source).not.toContain("提示词库");
});
