# 双工作页面媒体生成能力 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持 `/workspace` 与 React `/canvas` 两个页面独立的前提下，为两页分别加入图片、视频、语音合成和音乐生成，并让管理员按渠道、模型、能力和价格进行配置。

**Architecture:** 以 `capability`（`image|video|speech|music|prompt`）作为共享领域字段，Provider 目录和后端适配器负责模型路由与参数校验。旧版工作区使用主站会话和 generation queue，画布继续使用节点状态与 host proxy；两者仅复用模型目录、统一媒体 API 和资源存储，不共享页面组件或页面状态。

**Tech Stack:** Flask、SQLite/PostgreSQL、requests、Redis/RQ（现有队列）、Jinja2、原生 JavaScript/CSS、Next.js App Router、React、TypeScript、Ant Design、Zustand、pytest、Bun test。

---

## 文件与职责映射

- `huishi/providers.py`：能力枚举、渠道模型目录、协议/模型校验、模型列表获取和测试路由。
- `huishi/audio_api.py`：MiniMax 语音合成和音乐生成请求、hex/二进制解码、错误脱敏。
- `huishi/records.py`：媒体记录/任务的统一字段和序列化输入。
- `huishi/db.py`：`speech`/`music` 的配置字段、媒体类型索引、价格规则初始化和幂等迁移。
- `huishi/routes_workspace.py`：旧版 `/workspace` 生成分发、画布 host proxy 的媒体端点、测试结果返回。
- `huishi/generation_queue.py`：图片、视频、语音、音乐任务的 worker 分发和资源落盘。
- `huishi/billing.py`：按能力、模型和规格选择价格规则。
- `templates/workspace.html`、`static/js/workspace.js`、`static/css/site.css`：旧版功能页的四模式选择、参数区和媒体结果卡片。
- `templates/admin/_config_settings_panels.html`、`templates/admin/config_billing.html`、`static/js/settings.js`：管理员渠道、模型目录、能力/价格的简约表格和测试弹窗。
- `infinite-canvas/web/src/stores/use-config-store.ts`：画布 `speech/music` 配置、模型列表和旧 `audio` 兼容。
- `infinite-canvas/web/src/types/media.ts`、`infinite-canvas/web/src/services/api/audio.ts`、新增 `music.ts`：画布端媒体类型和本地/host 请求。
- `infinite-canvas/web/src/app/(user)/canvas/types.ts`、`components/canvas-config-node-panel.tsx`、`components/canvas-node-prompt-panel.tsx`：画布节点模式、参数和输出 metadata。
- `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`：节点生成分发、结果节点插入、保存/重试。
- `tests/test_unified_media_providers.py`、`tests/test_provider_proxy.py`、`tests/test_generation_queue_backend.py`、`tests/test_generation_billing.py`：后端回归。
- 新增 `tests/test_audio_api.py`、`tests/test_workspace_media_modes.py`、`tests/test_canvas_media_modes.py`：四类能力的接口和页面契约。
- 新增 `infinite-canvas/web/src/services/api/music.test.ts`、`components/canvas-media-modes.test.tsx`：画布 API/组件契约。

## Task 1: 扩展共享能力模型与媒体 Provider 适配器

**Files:**
- Modify: `huishi/providers.py`
- Create: `huishi/audio_api.py`
- Modify: `huishi/config.py`
- Test: `tests/test_unified_media_providers.py`
- Create: `tests/test_audio_api.py`

- [ ] **Step 1: 写能力和模型目录失败测试**

```python
def test_provider_capabilities_include_speech_and_music(app):
    from huishi.providers import normalize_provider_capabilities

    assert normalize_provider_capabilities(["speech", "music"], "audio") == ["speech", "music"]


def test_minimax_audio_catalog_has_separate_speech_and_music_models():
    from huishi.providers import audio_model_options, music_model_options

    assert {item["id"] for item in audio_model_options("minimax")} >= {"speech-2.8-hd", "speech-2.8-turbo"}
    assert {item["id"] for item in music_model_options("minimax")} >= {"music-3.0", "music-2.6", "music-cover"}
```

- [ ] **Step 2: 运行测试确认当前行为失败**

Run: `pytest -q tests/test_unified_media_providers.py tests/test_audio_api.py`

Expected: FAIL，因为当前 Provider 类型/能力只允许 `image|video|prompt`，没有独立语音和音乐目录，也不存在 `huishi.audio_api`。

- [ ] **Step 3: 增加能力、协议和模型目录**

在 `huishi/providers.py` 中把 Provider 类型扩展为 `image|video|audio|prompt`，把能力扩展为 `image|video|speech|music|prompt`；`audio` Provider 仅允许 `speech`/`music` 能力，保持 `video` 的现有协议不变。新增 MiniMax 目录和友好名称，目录项使用以下稳定结构：

```python
MINIMAX_SPEECH_MODELS = (
    {"id": "speech-2.8-hd", "label": "MiniMax Speech 2.8 HD"},
    {"id": "speech-2.8-turbo", "label": "MiniMax Speech 2.8 Turbo"},
    {"id": "speech-2.6-hd", "label": "MiniMax Speech 2.6 HD"},
    {"id": "speech-2.6-turbo", "label": "MiniMax Speech 2.6 Turbo"},
)
MINIMAX_MUSIC_MODELS = (
    {"id": "music-3.0", "label": "MiniMax Music 3.0"},
    {"id": "music-2.6", "label": "MiniMax Music 2.6"},
    {"id": "music-cover", "label": "MiniMax Music Cover"},
)
```

新增 `speech_provider_candidates(model)`、`music_provider_candidates(model)`、`selectable_speech_models()`、`selectable_music_models()`，筛选逻辑与图片/视频候选保持一致，并通过 `models_json` 保存渠道内的多个模型。

- [ ] **Step 4: 实现 MiniMax 语音和音乐请求适配**

新建 `huishi/audio_api.py`，提供以下接口，统一返回 `{"content": bytes, "mime_type": str, "extension": str, "model": str}`：

```python
def generate_speech(provider: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Call MiniMax T2A and return decoded audio bytes plus MIME metadata."""
    payload = build_speech_payload(request)
    response = post_audio_request(provider, "/v1/t2a_v2", payload)
    return decode_audio_response(response, model=str(request.get("model") or ""), default_extension="mp3")


def generate_music(provider: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Call MiniMax music generation and return audio bytes plus MIME metadata."""
    payload = build_music_payload(request)
    response = post_audio_request(provider, "/v1/music_generation", payload)
    return decode_audio_response(response, model=str(request.get("model") or ""), default_extension="mp3")
```

`generate_speech` 调用 `/v1/t2a_v2`，默认 `stream=false`、`format=mp3`、`output_format=hex`，同时支持 `data.audio` 为 hex、base64 或服务端直接返回音频。`generate_music` 调用 `/v1/music_generation`，仅当模型为 `music-cover` 时提交参考音频字段。两个函数都使用 `request_proxy_kwargs(provider["proxy_url"])`，将 HTTP/代理/权限错误经 `redact_sensitive_text` 脱敏后抛出 `AudioApiError`。

- [ ] **Step 5: 增加适配器请求测试**

在 `tests/test_audio_api.py` 通过 monkeypatch `requests.post` 验证：

```python
def test_speech_hex_payload_is_decoded(monkeypatch):
    class Response:
        status_code = 200
        content = b""
        def json(self):
            return {"data": {"audio": "68656c6c6f"}, "base_resp": {"status_code": 0}}
    monkeypatch.setattr("huishi.audio_api.requests.post", lambda *args, **kwargs: Response())
    result = generate_speech({"api_key": "k", "base_url": "https://api.minimaxi.com", "api_format": "minimax"}, {"model": "speech-2.8-hd", "text": "你好"})
    assert result["content"] == b"hello"
    assert result["mime_type"] == "audio/mpeg"


def test_music_cover_only_forwards_reference_audio(monkeypatch):
    captured = {}
    monkeypatch.setattr("huishi.audio_api.requests.post", lambda url, **kwargs: captured.update(kwargs) or FakeMusicResponse())
    generate_music(provider, {"model": "music-cover", "prompt": "钢琴", "audio_base64": "abc"})
    assert captured["json"]["audio_base64"] == "abc"
```

- [ ] **Step 6: 运行 Task 1 测试**

Run: `pytest -q tests/test_unified_media_providers.py tests/test_provider_proxy.py tests/test_audio_api.py`

Expected: PASS，既有图片/视频 Provider 测试保持通过，代理参数和敏感信息脱敏行为不变。

## Task 2: 让任务、记录、队列和主站 API 支持 speech/music

**Files:**
- Modify: `huishi/db.py`
- Modify: `huishi/records.py`
- Modify: `huishi/generation_queue.py`
- Modify: `huishi/routes_workspace.py`
- Modify: `huishi/billing.py`
- Test: `tests/test_generation_queue_backend.py`
- Test: `tests/test_generation_billing.py`
- Create: `tests/test_workspace_media_modes.py`

- [ ] **Step 1: 写主站媒体路由和持久化失败测试**

```python
def test_workspace_speech_request_creates_speech_task(app, monkeypatch):
    monkeypatch.setattr("huishi.routes_workspace.enqueue_generation_task", lambda *args, **kwargs: None)
    client, user_id = logged_in_client(app)
    response = client.post("/generate", data={"prompt": "你好", "media_type": "speech", "model": "speech-2.8-hd", "count": "1"}, headers={"X-Requested-With": "fetch"})
    assert response.status_code == 200
    task = get_db().execute("SELECT media_type, model FROM generation_tasks WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    assert dict(task) == {"media_type": "speech", "model": "speech-2.8-hd"}


def test_music_cost_uses_model_and_duration_rule(app):
    with app.app_context():
        insert_pricing_rule(mode="music", media_type="music", model="music-3.0", resolution="default", points=9)
        assert calculate_cost("music", "default", 1, model="music-3.0", media_type="music") == 9
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest -q tests/test_workspace_media_modes.py tests/test_generation_queue_backend.py tests/test_generation_billing.py`

Expected: FAIL，因为 `/generate` 仍按图片表单解析，队列只分发 `video` 或图片，记录序列化没有 speech/music 的媒体元数据。

- [ ] **Step 3: 扩展数据库和记录归一化**

在 `generation_tasks` 增加 `media_type` 允许值说明和 `metadata_json` 中的媒体参数；在 `records` 增加 `media_type`、`mime_type`、`duration_ms` 字段并更新 SQLite/PostgreSQL 建表及增量迁移。`normalize_record` 与 `serialize_record` 返回：

```python
{
    "media_type": record.get("media_type") or record.get("asset_source") or "image",
    "mime_type": record.get("mime_type") or "",
    "duration_ms": int(record.get("duration_ms") or 0),
}
```

迁移函数只在列不存在时添加，重复初始化不修改现有资源路径和历史图片数量。

- [ ] **Step 4: 扩展计费解析**

将 `calculate_cost(mode, resolution, count, model, media_type, duration_seconds)` 的查找顺序固定为：精确 `media_type + mode + model + resolution`，再回退到该媒体类型的通配模型规则；不存在可用规则时抛出可显示的中文错误。图片/视频现有调用签名和收费结果保持不变，speech/music 默认规格使用 `default`。

- [ ] **Step 5: 扩展队列分发和资源保存**

在 `run_generation_task` 中按 `task["media_type"]` 分发到新增的 `run_audio_generation_task`：

```python
if media_type == "video":
    run_video_generation_task(app, task_id, cleanup_paths or [])
    return
if media_type in {"speech", "music"}:
    run_audio_generation_task(app, task_id, cleanup_paths or [])
    return
```

    worker 使用 Provider 候选、代理和配置参数调用 `generate_speech`/`generate_music`，按 MIME 保存到 `get_upload_storage()`，再使用下列固定字段调用 `_finalize_generation` 创建记录：

```python
record_id = _finalize_generation(
    user_id=int(task["user_id"]),
    prompt=str(task["prompt"]),
    mode=str(task["mode"]),
    ratio=str(task.get("ratio") or "auto"),
    resolution="default",
    count=1,
    quality="auto",
    output_format=result["extension"],
    result={"image_path": public_path, "image_paths": [public_path], "actual_size": "", "model_source": model_id, "elapsed_seconds": elapsed},
    reference_paths=list(task.get("reference_paths") or []),
    dialogue_id=task.get("dialogue_id"),
    bypass_billing=bool(task.get("bypass_billing")),
    model=model_id,
    asset_source="audio",
    media_type=media_type,
    duration_seconds=int(result.get("duration_ms") or 0) // 1000,
    commit=False,
)
```

失败时回收新文件和引用上传，任务状态变为 `failed`。

- [ ] **Step 6: 增加主站 JSON/host API**

扩展 `/generate` 和 `/api/canvas/generate` 接收 `media_type`/`capability`，只解析当前媒体参数；新增 `/api/audio/tasks`、`/api/audio/tasks/<id>`、`/api/audio/tasks/<id>/content`，复用视频任务的 host session、CORS、取消和状态返回模式。所有响应保留 `{ok, task, error}` 结构，`task.media_type` 为 `speech` 或 `music`。

- [ ] **Step 7: 运行后端任务测试**

Run: `pytest -q tests/test_workspace_media_modes.py tests/test_generation_queue_backend.py tests/test_generation_billing.py tests/test_upload_storage.py`

Expected: PASS；图片/视频任务、已有资源目录、代理和积分扣除无回归。

## Task 3: 旧版 `/workspace` 四模式页面

**Files:**
- Modify: `templates/workspace.html`
- Modify: `static/js/workspace.js`
- Modify: `static/css/site.css`
- Modify: `huishi/routes_workspace.py`
- Test: `tests/test_workspace_composer_copy.py`
- Test: `tests/test_workspace_generation_flow.py`
- Test: `tests/test_workspace_media_modes.py`

- [ ] **Step 1: 写页面契约失败测试**

```python
def test_workspace_has_four_independent_generation_modes(app):
    client, _ = logged_in_client(app)
    body = client.get("/workspace").get_data(as_text=True)
    assert 'data-generation-type="image"' in body
    assert 'data-generation-type="video"' in body
    assert 'data-generation-type="speech"' in body
    assert 'data-generation-type="music"' in body
    assert 'name="media_type"' in body
```

- [ ] **Step 2: 运行页面测试确认失败**

Run: `pytest -q tests/test_workspace_composer_copy.py tests/test_workspace_generation_flow.py tests/test_workspace_media_modes.py`

Expected: FAIL，因为当前底部只有图片模型和图片比例/数量控件。

- [ ] **Step 3: 增加并列模式和能力过滤模型**

在 `workspace.html` 的 `.composer-controls` 前加入四项并列模式按钮和隐藏字段：

```html
<div class="generation-type-tabs" data-generation-type-tabs role="tablist">
  <button type="button" data-generation-type="image" role="tab">图片生成</button>
  <button type="button" data-generation-type="video" role="tab">视频生成</button>
  <button type="button" data-generation-type="speech" role="tab">语音合成</button>
  <button type="button" data-generation-type="music" role="tab">音乐生成</button>
</div>
<input type="hidden" name="media_type" value="image" data-media-type>
```

模板提供 `image_models`、`video_models`、`speech_models`、`music_models` 和每类默认参数；参数面板分别使用 `data-media-panel`，隐藏面板不提交字段。图片数量默认 `1`，视频显示比例/时长/质量，语音显示文本/声音/速度/格式，音乐显示描述/歌词/纯音乐/参考音频。

- [ ] **Step 4: 在 `workspace.js` 实现模式状态机**

增加以下单一入口，所有提交、计费刷新和恢复历史都调用它：

```javascript
function setGenerationType(type) {
  const next = ["image", "video", "speech", "music"].includes(type) ? type : "image";
  mediaTypeInput.value = next;
  document.querySelectorAll("[data-generation-type]").forEach((button) => {
    const active = button.dataset.generationType === next;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-media-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.mediaPanel !== next;
  });
  syncModelOptions(next);
  syncGenerationCount(next === "image");
  refreshEstimate();
}
```

提交时构建能力白名单 payload：图片只发送图片字段，视频只发送视频字段，语音只发送 `text/voice_setting/audio_setting`，音乐只发送音乐字段。异步 task 轮询成功后按 `media_type` 渲染 `<img>`、`<video controls>` 或 `<audio controls>`，失败卡片保留重试按钮。

- [ ] **Step 5: 增加媒体结果卡片和可访问状态**

扩展 `workspace.html` 的 generation task template，使用 `data-media-result` 分支；`workspace.js` 将返回的 `record.image_path` 作为媒体 URL，安全设置 `src`，不拼接用户输入到 HTML。加载、成功、失败文案和积分状态都通过现有 `generation-status` 更新，按钮在请求期间禁用并显示取消/重试状态。

- [ ] **Step 6: 调整紧凑响应式 CSS**

在 `static/css/site.css` 增加 `.generation-type-tabs`、`.media-panel`、`.generation-media-result` 的页面私有规则；桌面四项同排，窄屏允许横向滚动但不换成嵌套卡片；保持现有主题变量和深浅色可读性。

- [ ] **Step 7: 运行旧版工作区测试**

Run: `pytest -q tests/test_workspace_composer_copy.py tests/test_workspace_generation_flow.py tests/test_workspace_media_modes.py tests/test_ui_theme_contract.py`

Expected: PASS；原有图片生成、历史恢复、一次生成 1 张、参考素材和对话侧栏行为不变。

## Task 4: 画布配置、模型选择和 host proxy 的独立媒体模式

**Files:**
- Modify: `infinite-canvas/web/src/stores/use-config-store.ts`
- Modify: `infinite-canvas/web/src/components/model-picker.tsx`
- Modify: `infinite-canvas/web/src/components/settings/settings-tabs-content.tsx`
- Modify: `infinite-canvas/web/src/services/api/audio.ts`
- Create: `infinite-canvas/web/src/services/api/music.ts`
- Modify: `infinite-canvas/web/src/services/api/video.ts`
- Modify: `infinite-canvas/web/src/stores/use-canvas-host-session-store.ts`
- Test: `infinite-canvas/web/src/services/api/music.test.ts`

- [ ] **Step 1: 写配置迁移和能力过滤失败测试**

```typescript
test("旧 audio 配置迁移为 speech，music 使用独立字段", () => {
    const merged = mergePersistedConfig({ audioModel: "default::speech-2.8-hd", audioModels: ["default::speech-2.8-hd"] });
    expect(merged.speechModel).toBe("default::speech-2.8-hd");
    expect(merged.musicModel).toBe("");
    expect(merged.audioModel).toBe("default::speech-2.8-hd");
});
```

- [ ] **Step 2: 运行画布类型检查确认失败**

Run: `cd infinite-canvas/web; bun test; bun run typecheck`

Expected: FAIL 或无法覆盖新字段，因为 `AiConfig` 目前只有 `audioModel/audioModels`，ModelCapability 没有 `speech/music`。

- [ ] **Step 3: 扩展 `AiConfig` 和持久化合并**

在 `use-config-store.ts` 增加：

```typescript
speechModel: string;
speechModels: string[];
musicModel: string;
musicModels: string[];
export type ModelCapability = "image" | "video" | "text" | "speech" | "music" | "audio";
```

`merge` 和 `withChannels` 先使用显式 `speech/music` 字段；仅当 `speech` 为空时从旧 `audio` 字段拷贝，`audio` 字段仍保留用于旧节点。模型标签和 `selectableModelsByCapability` 分别按能力过滤，不把语音模型放入音乐列表。

- [ ] **Step 4: 拆分画布音频 API**

保留 `requestAudioGeneration` 作为语音合成兼容入口，内部改为 `/api/audio/tasks` host proxy 或 MiniMax `/v1/t2a_v2`；新增 `requestMusicGeneration(config, prompt, options)`，调用 `/api/audio/tasks` 时提交 `media_type: "music"`，本地模式调用 `/v1/music_generation`。两者都返回 `Blob`，通过现有 `uploadMediaFile` 保存。

- [ ] **Step 5: 增加 host session 字段和 API 测试**

在 host bootstrap/状态中增加 `audioTasksUrl`，API 请求必须附带 `X-Canvas-Session`；测试验证音乐任务请求 body 含 `media_type: "music"`，语音请求 body 含 `media_type: "speech"`，并验证轮询 `/api/audio/tasks/:id` 和内容 URL。

- [ ] **Step 6: 运行画布 API 测试**

Run: `cd infinite-canvas/web; bun test src/services/api/music.test.ts src/services/api/video-host.test.ts; bun run typecheck`

Expected: PASS，旧 `audio` 调用仍能生成语音，新增音乐调用不会复用语音模型字段。

## Task 5: 画布节点分别加入图片、视频、语音合成、音乐生成

**Files:**
- Modify: `infinite-canvas/web/src/app/(user)/canvas/types.ts`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-config-node-panel.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-node-prompt-panel.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-node-generation.ts`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/[id]/canvas-client-page.tsx`
- Modify: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-assistant-panel.tsx`
- Create: `infinite-canvas/web/src/app/(user)/canvas/components/canvas-media-modes.test.tsx`

- [ ] **Step 1: 写画布模式和 metadata 失败测试**

```typescript
test("配置节点模式包含 speech 和 music 且音频 metadata 区分类型", () => {
    expect(CANVAS_GENERATION_MODES).toEqual(["text", "image", "video", "speech", "music"]);
    expect(buildAudioMetadata("speech").audioKind).toBe("speech");
    expect(buildAudioMetadata("music").audioKind).toBe("music");
});
```

- [ ] **Step 2: 运行画布组件测试确认失败**

Run: `cd infinite-canvas/web; bun test src/app/(user)/canvas/components/canvas-media-modes.test.tsx`

Expected: FAIL，因为 `CanvasGenerationMode` 目前只有 `text|image|video|audio`。

- [ ] **Step 3: 扩展类型并保留旧 audio 别名**

将 `CanvasGenerationMode` 改为 `"text" | "image" | "video" | "speech" | "music" | "audio"`；加载画布时把 `audio` 映射到 `speech`，保存节点时保留原始旧值可读。`CanvasNodeMetadata` 增加 `musicLyrics`、`musicInstrumental`、`speechVoice`、`speechSpeed`、`audioKind`、`mediaType`。

- [ ] **Step 4: 更新配置节点和提示词面板**

在 `canvas-config-node-panel.tsx` 和 `canvas-node-prompt-panel.tsx` 使用五项模式选择；模型选择使用对应 `speech`/`music` capability；图片显示数量和尺寸，视频显示时长/质量，语音显示声音/速度/格式，音乐显示歌词/纯音乐/参考音频。模式切换只更新当前节点 metadata，不覆盖全局配置或其他节点。

- [ ] **Step 5: 更新画布生成分发和输出节点**

在 `canvas-client-page.tsx` 的 `handleGenerateNode` 分支中：

```typescript
if (mode === "speech") {
    const blob = await requestAudioGeneration(generationConfig, effectivePrompt, options);
    return insertAudioNode(blob, { audioKind: "speech", mediaType: "speech", model: generationConfig.model });
}
if (mode === "music") {
    const blob = await requestMusicGeneration(generationConfig, effectivePrompt, options);
    return insertAudioNode(blob, { audioKind: "music", mediaType: "music", model: generationConfig.model });
}
```

图片和视频分支保持现有逻辑；生成数量始终从节点 metadata 读取并默认 `1`，修改节点配置后立即保存。音频节点仍使用 `CanvasNodeType.Audio`，通过 metadata 区分 speech/music，避免旧渲染器失效。

- [ ] **Step 6: 更新画布 Agent 工具映射**

保留旧 `canvas_generate_audio` 作为语音合成兼容工具，增加 `canvas_generate_music`，两者分别写入 `mode: "speech"` 或 `mode: "music"`，工具描述明确输出音频但能力不同；不改变图片 Agent 工具和删除确认规则。

- [ ] **Step 7: 运行画布测试和构建**

Run: `cd infinite-canvas/web; bun test; bun run typecheck; bun run build`

Expected: PASS，画布旧项目可打开，图片/视频/语音/音乐节点均能保存模型与参数，生成失败有节点错误状态而不是静默无响应。

## Task 6: 管理员配置页、模型获取、连接测试和模型定价

**Files:**
- Modify: `huishi/routes_workspace.py`
- Modify: `huishi/routes_admin.py`
- Modify: `templates/admin/_config_settings_panels.html`
- Modify: `templates/admin/config_billing.html`
- Modify: `static/js/settings.js`
- Modify: `static/css/settings-console.css`
- Test: `tests/test_settings_config_status.py`
- Test: `tests/test_admin_ui_structure.py`
- Test: `tests/test_unified_media_providers.py`

- [ ] **Step 1: 写配置页契约失败测试**

```python
def test_admin_config_exposes_four_capabilities_and_model_test_dialog(admin_client):
    body = admin_client.get("/admin/config/settings").get_data(as_text=True)
    assert 'data-capability="speech"' in body
    assert 'data-capability="music"' in body
    assert 'data-fetch-models' in body
    assert 'data-provider-test-dialog' in body
```

- [ ] **Step 2: 运行配置页测试确认失败**

Run: `pytest -q tests/test_settings_config_status.py tests/test_admin_ui_structure.py`

Expected: FAIL，因为现有管理表单按 image/video/prompt 分组，测试弹窗也没有四能力模型选择。

- [ ] **Step 3: 扩展后端配置上下文和模型列表**

在配置页面上下文中提供 `speech_providers`、`music_providers`、`speech_model_catalog`、`music_model_catalog`；`/settings/providers/<id>/models` 失败时返回已保存模型和官方目录，不清空列表。保存渠道时要求 `capabilities` 至少包含所选模型能力，Key 为空时保留旧密文，代理按现有规范化函数存储。

- [ ] **Step 4: 实现按能力的测试弹窗**

扩展测试路由接收 `test_capability` 和 `test_model`，响应：

```json
{
  "ok": true,
  "capability": "image|video|speech|music|prompt",
  "model": "model-id",
  "text": "连接测试成功",
  "image": "/static/uploads/provider-test-image.png",
  "video": "/api/video/tasks/42/content",
  "audio": "/static/uploads/provider-test-audio.mp3",
  "message": "测试完成"
}
```

最小测试分别调用图片、视频、语音、音乐和对话接口；所有请求显示进行中、成功、失败和关闭状态，响应错误不含 Key 或完整代理凭据。

- [ ] **Step 5: 将配置页改为简约表格**

`_config_settings_panels.html` 使用一个渠道表格和一个模型表格，行内显示名称、协议、能力、模型数、启用状态和操作；新增/编辑在同一弹窗完成。模型选择支持“先获取模型，再勾选添加”，友好名称和真实 ID 同时可见；价格表按“能力 × 模型 × 规格 × 单次价格”一行展示，支持启用/停用。

- [ ] **Step 6: 补齐前端联动和响应式样式**

`settings.js` 根据能力筛选模型、切换参数字段、保留自定义 Base URL 和已保存 Key；`settings-console.css` 使用现有主题变量，桌面双列、窄屏单列，表格横向滚动不挤压操作列。保留“管理后台”入口、CSRF、权限和审计钩子。

- [ ] **Step 7: 运行管理员 UI 和后端配置测试**

Run: `pytest -q tests/test_settings_config_status.py tests/test_admin_ui_structure.py tests/test_unified_media_providers.py tests/test_admin_audit.py`

Expected: PASS；四种能力、多个模型、代理、Key 掩码、获取模型失败回退和测试结果都可验证。

## Task 7: 文档、回归验证和受控部署

**Files:**
- Modify: `docs/content/docs/backend/api-response.mdx`
- Modify: `docs/content/docs/backend/backend-database.mdx`
- Modify: `docs/content/docs/progress/pending-test.mdx`
- Inspect: `deploy/`、`docs/db/vm-staging-deploy.md`
- Test: `tests/test_check_encoding.py`
- Test: `tests/test_deploy_release_scripts.py`

- [ ] **Step 1: 更新 API 与数据库文档**

记录 `capability`、`media_type`、`audioKind`、`/api/audio/tasks` 的响应字段和错误规则；数据库文档补充 records/generation_tasks 的媒体字段、pricing_rules 的模型/能力维度。`pending-test.mdx` 只记录本次实际变更和需要线上验证的页面。

- [ ] **Step 2: 运行完整本地验证**

Run: `pytest -q`

Expected: 全部现有和新增 Python 测试通过。

Run: `cd infinite-canvas/web; bun test; bun run typecheck; bun run build`

Expected: 画布测试、类型检查和生产构建通过。

- [ ] **Step 3: 检查敏感信息和资源目录边界**

Run: `rg -n -i "api[_ -]?key|password|secret|bearer|BEGIN .*PRIVATE KEY" huishi templates static infinite-canvas/web/src tests`

确认新增日志、测试响应、构建产物和文档没有 API Key、管理员密码或代理认证信息；确认新增媒体全部经过 `get_upload_storage()`，没有写入临时目录之外的任意路径。

- [ ] **Step 4: 构建发布包并记录回滚点**

按照 `docs/db/vm-staging-deploy.md` 和现有 `deploy/` 脚本生成 release，列出变更服务、备份文件、数据库迁移状态和回滚命令。只构建/重启实际变更的 backend、workspace、canvas 服务，不重启 PostgreSQL、Redis、canvas-agent 或无关 worker。

- [ ] **Step 5: 部署前向用户展示摘要并等待明确批准**

在执行 SSH 前报告：本地测试结果、release 文件清单、线上备份位置、预计重启服务和回滚方式。未得到明确部署批准前不执行远程写入或重启。

## 计划自审

- **规格覆盖：** 目标与边界由 Task 3/5 覆盖；共享模型、渠道和代理由 Task 1/6 覆盖；MiniMax 语音/音乐由 Task 1/2/4 覆盖；主站与画布的独立页面由 Task 3/5 覆盖；测试弹窗和模型获取回退由 Task 6 覆盖；旧 `audio`、图片数量和资源目录保护由 Task 2/4/5/7 覆盖。
- **占位符扫描：** 计划没有未展开的代码片段或“自行处理”步骤；响应样例、函数签名、落盘字段、测试命令和预期结果均已具体给出。
- **类型一致性：** 后端使用 `media_type`/`capability`，画布使用 `CanvasGenerationMode`、`speechModel`/`musicModel`、`audioKind`；旧 `audio` 仅作为兼容别名，映射规则在 Task 4/5 一致。
- **风险边界：** 数据库迁移、计费和线上部署都单列验证；不覆盖线上 `.env`，不删除 `/opt/huishi/data/uploads`，不重启无关服务。
