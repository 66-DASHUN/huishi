// 用最小 DOM 桩真正执行 @ 提及逻辑（而非字符串匹配）。
//
// 为什么要跑真代码：本次修复的核心是"图片模式也能用 @"，而它此前只是
// syncSubjectMentionMenu 开头的一行早退。这类缺陷靠 `assert 'xxx' in source`
// 抓不到——必须看实参、分支与调用次数。
//
// 注意：本文件需要 node，容器内没有 node，因此不参与发布门禁，
// 属于本地/CI 侧校验（与 check_settings_models.cjs 同一处境）。
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "..", "static", "js", "workspace.js"), "utf8");

// 从源码中抽出待测函数（按大括号配平），保证测的是真实实现而非副本。
function extract(name) {
    const start = source.indexOf(`function ${name}(`);
    assert.ok(start >= 0, `未找到函数 ${name}`);
    let i = source.indexOf("{", start);
    let depth = 0;
    for (; i < source.length; i += 1) {
        if (source[i] === "{") depth += 1;
        else if (source[i] === "}") {
            depth -= 1;
            if (depth === 0) return source.slice(start, i + 1);
        }
    }
    throw new Error(`函数 ${name} 大括号不配平`);
}

const NAMES = ["referenceMentionEntries", "videoSubjectEntries", "materialDisplayName",
    "mentionAnchor", "syncSubjectMentionMenu", "activeSubjectMention"];
const fnSource = NAMES.map(extract).join("\n\n");

function makeSandbox({ mediaType = "image", value = "", cursor = null, materials = [], triggerVisible = true } = {}) {
    const panel = { hidden: true, dataset: {}, id: "subject-panel" };
    const shell = { tag: "shell" };
    panel.closest = (sel) => (sel === ".composer-prompt-shell" ? shell : null);

    const trigger = {
        offsetParent: triggerVisible ? {} : null,
        attrs: {},
        setAttribute(k, v) { this.attrs[k] = v; },
    };

    const pos = cursor === null ? value.length : cursor;
    const composerPrompt = { value, selectionStart: pos, selectionEnd: pos };
    const calls = { positioned: [], closed: [], rendered: 0 };

    const documentStub = {
        querySelector(sel) {
            if (sel === "#subject-panel") return panel;
            if (sel === "[data-subject-trigger]") return trigger;
            return null;
        },
    };

    const runner = new Function(
        "document", "composerPrompt", "form", "selectedMediaType", "selectedVideoSubjectId",
        "materialFileKind", "visibleReferenceMaterials", "renderVideoSubjects",
        "closeParameterPanels", "positionParameterPanel",
        `${fnSource}\n;return { syncSubjectMentionMenu, mentionAnchor, activeSubjectMention, referenceMentionEntries };`,
    );
    const api = runner(
        documentStub, composerPrompt, { tag: "form" }, mediaType, "",
        (item) => item.kind || "image",
        () => materials,
        () => { calls.rendered += 1; },
        (id) => calls.closed.push(id),
        (anchor) => calls.positioned.push(anchor === trigger ? "trigger" : anchor === shell ? "shell" : "other"),
    );
    return { panel, trigger, calls, api };
}

// 1) 图片模式：打 @ 必须打开并定位面板（本次修复的核心）
{
    const { panel, calls, api } = makeSandbox({ mediaType: "image", value: "@", cursor: 1 });
    api.syncSubjectMentionMenu();
    assert.equal(panel.hidden, false, "图片模式打 @ 应打开面板");
    assert.equal(calls.positioned.length, 1, "图片模式应定位面板");
    assert.equal(calls.rendered, 1, "图片模式应渲染候选");
    assert.equal(panel.dataset.mentionOpen, "1", "应标记 mentionOpen");
}

// 2) 图片模式没有可见的 @ 按钮，锚点应回落到提示词区域
{
    const { calls, api } = makeSandbox({ mediaType: "image", value: "@", triggerVisible: false });
    api.syncSubjectMentionMenu();
    assert.equal(calls.positioned[0], "shell", "图片模式锚点应为提示词区域");
}

// 3) 视频模式有可见按钮，锚点用它
{
    const { calls, api } = makeSandbox({ mediaType: "video", value: "@" });
    api.syncSubjectMentionMenu();
    assert.equal(calls.positioned[0], "trigger", "视频模式锚点应为工具栏按钮");
}

// 4) 没有 @ 时关闭已打开的面板
{
    const { panel, api } = makeSandbox({ mediaType: "image", value: "普通提示词" });
    panel.dataset.mentionOpen = "1";
    api.syncSubjectMentionMenu();
    assert.equal(panel.hidden, true, "无 @ 时应关闭面板");
    assert.equal(panel.dataset.mentionOpen, undefined, "关闭时应清除 mentionOpen");
}

// 5) 已完成的引用（后跟空格）应收起菜单
{
    const { panel, api } = makeSandbox({ mediaType: "image", value: "@图片1 继续描述", cursor: 6 });
    panel.dataset.mentionOpen = "1";
    api.syncSubjectMentionMenu();
    assert.equal(panel.hidden, true, "完整引用后应收起菜单");
}

// 6) 文件名含空格时仍可继续匹配
{
    const { panel, api } = makeSandbox({
        mediaType: "image", value: "@my ph", cursor: 6,
        materials: [{ id: "a", kind: "image", name: "my photo.png" }],
    });
    api.syncSubjectMentionMenu();
    assert.equal(panel.hidden, false, "带空格文件名应可继续匹配");
}

// 7) 换行后不再视为提及
{
    const { panel, api } = makeSandbox({ mediaType: "image", value: "@abc\ndef", cursor: 7 });
    panel.dataset.mentionOpen = "1";
    api.syncSubjectMentionMenu();
    assert.equal(panel.hidden, true, "换行不应触发提及");
}

// 8) 候选入口与媒体类型无关（图片素材在图片模式可见）
{
    const { api } = makeSandbox({
        mediaType: "image",
        materials: [{ id: "m1", kind: "image", name: "参考图A.png" }],
    });
    const entries = api.referenceMentionEntries();
    assert.equal(entries.length, 1, "应返回图片候选");
    assert.equal(entries[0].fileName, "参考图A.png", "候选应带显示名");
}

console.log("workspace @ 提及行为校验通过（8 组）");
