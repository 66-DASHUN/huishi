(function settingsModelModule(root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.HuishiSettingsModels = api;
  if (root?.document) api.enhance(root.document);
})(typeof window !== "undefined" ? window : globalThis, () => {
  function parseImageProviderCatalog(rawCatalog) {
    if (!rawCatalog) return null;
    try {
      const parsed = typeof rawCatalog === "string" ? JSON.parse(rawCatalog) : rawCatalog;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
      if (!parsed.catalog || typeof parsed.catalog !== "object" || Array.isArray(parsed.catalog)) return null;
      if (!parsed.metadata || typeof parsed.metadata !== "object" || Array.isArray(parsed.metadata)) return null;
      if (!Array.isArray(parsed.catalog.openai) || !parsed.catalog.openai.length) return null;
      if (!parsed.metadata.openai || typeof parsed.metadata.openai !== "object") return null;
      return parsed;
    } catch (_) {
      return null;
    }
  }

  function rememberProtocolState(states, protocol, model, resolutions) {
    states[protocol] = { model, resolutions: { ...resolutions } };
  }

  function protocolStateFor(catalog, states, protocol, fallback) {
    const options = catalog?.catalog?.[protocol];
    const metadata = catalog?.metadata?.[protocol];
    if (!Array.isArray(options) || !options.length || !metadata || !Array.isArray(metadata.resolutions)) return null;
    const saved = states[protocol] || fallback || { model: "", resolutions: {} };
    const model = options.some((option) => option.id === saved.model) ? saved.model : options[0].id;
    const sourceResolutions = saved.resolutions || {};
    const knownTiers = new Set([...Object.keys(sourceResolutions), ...metadata.resolutions]);
    const resolutions = {};
    knownTiers.forEach((tier) => {
      resolutions[tier] = metadata.resolutions.includes(tier) && Boolean(sourceResolutions[tier]);
    });
    return { model, resolutions };
  }

  function defaultUrlFor(catalog, protocol, currentValue, force = false) {
    const current = String(currentValue || "");
    if (current.trim() && !force) return current;
    return catalog?.metadata?.[protocol]?.default_base_url || current;
  }

  function testImageUrl(value, documentRoot) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    if (raw.startsWith("data:image/")) return raw;
    try {
      const url = new URL(raw, documentRoot?.baseURI || "http://localhost/");
      if (["http:", "https:"].includes(url.protocol)) return url.href;
    } catch (_) {
      return "";
    }
    return "";
  }

  function modelEntryFromValues(id, label, enabled, mediaType = "") {
    const entry = {
      id: String(id || "").trim(),
      label: String(label || "").trim(),
      enabled: Boolean(enabled),
    };
    const capability = String(mediaType || "").trim().toLowerCase();
    if (["image", "video", "speech", "music", "prompt"].includes(capability)) entry.media_type = capability;
    return entry;
  }

  function mergeFetchedModels(existing, fetched) {
    const result = Array.isArray(existing) ? existing.map((entry) => ({ ...entry })) : [];
    const seen = new Set(result.map((entry) => String(entry?.id || "").trim()).filter(Boolean));
    (Array.isArray(fetched) ? fetched : []).forEach((entry) => {
      const id = String(entry?.id || "").trim();
      if (!id || seen.has(id)) return;
      seen.add(id);
      result.push({ ...entry, ...modelEntryFromValues(id, entry?.label || id, entry?.enabled === true, entry?.media_type || entry?.capability || "") });
    });
    return result;
  }

  function enhanceForm(container, catalog) {
    const protocolSelect = container.querySelector("[data-model-protocol]");
    const modelSelect = container.querySelector("[data-model-select]");
    if (!protocolSelect || !modelSelect) return;
    if (!protocolStateFor(catalog, {}, protocolSelect.value || "openai", null)) return;

    const customToggle = container.querySelector("[data-custom-model-toggle]");
    const customField = container.querySelector("[data-custom-model-field]");
    const customModel = container.querySelector("[data-custom-model]");
    const modelId = container.querySelector("[data-model-id]");
    const baseUrl = container.querySelector("[data-base-url]");
    const restoreDefaultUrl = container.querySelector("[data-restore-default-url]");
    const resolutionInputs = [...container.querySelectorAll("[data-resolution]")];
    const states = {};
    let activeProtocol = protocolSelect.value || "openai";

    const readResolutions = () => Object.fromEntries(
      resolutionInputs.map((input) => [input.value, input.checked]),
    );
    const updateModelId = () => {
      const id = customToggle?.checked ? customModel?.value.trim() : modelSelect.value;
      if (modelId) modelId.replaceChildren(`真实 ID：${id || "未选择"}`);
    };
    const renderOptions = (protocol, selectedModel) => {
      const options = catalog.catalog[protocol];
      modelSelect.replaceChildren(...options.map(({ id, label }) => {
        const option = modelSelect.ownerDocument.createElement("option");
        option.value = id;
        option.textContent = label;
        return option;
      }));
      modelSelect.value = selectedModel;
    };
    const renderResolutions = (protocol, selectedResolutions) => {
      const supported = new Set(catalog.metadata[protocol].resolutions);
      resolutionInputs.forEach((input) => {
        input.disabled = !supported.has(input.value);
        input.checked = Boolean(selectedResolutions[input.value]);
      });
    };
    const fillDefaultUrl = (force = false) => {
      if (!baseUrl) return;
      baseUrl.value = defaultUrlFor(catalog, activeProtocol, baseUrl.value, force);
    };
    const syncCustomModel = () => {
      const enabled = Boolean(customToggle?.checked);
      customField?.toggleAttribute("hidden", !enabled);
      if (customModel) customModel.required = enabled;
      updateModelId();
    };
    const applyProtocol = (protocol, fallback) => {
      const next = protocolStateFor(catalog, states, protocol, fallback);
      if (!next) return false;
      renderOptions(protocol, next.model);
      renderResolutions(protocol, next.resolutions);
      activeProtocol = protocol;
      return true;
    };

    rememberProtocolState(states, activeProtocol, modelSelect.value, readResolutions());
    applyProtocol(activeProtocol, { model: modelSelect.value, resolutions: readResolutions() });
    syncCustomModel();
    fillDefaultUrl();

    protocolSelect.addEventListener("change", () => {
      rememberProtocolState(states, activeProtocol, modelSelect.value, readResolutions());
      if (applyProtocol(protocolSelect.value || "openai", { model: modelSelect.value, resolutions: readResolutions() })) {
        fillDefaultUrl();
        updateModelId();
      }
    });
    modelSelect.addEventListener("change", () => {
      fillDefaultUrl();
      updateModelId();
    });
    customToggle?.addEventListener("change", syncCustomModel);
    customModel?.addEventListener("input", updateModelId);
    restoreDefaultUrl?.addEventListener("click", () => fillDefaultUrl(true));
  }

  function enhanceModelEditor(container) {
    const editor = container.querySelector("[data-model-editor]");
    if (!editor || editor.dataset.enhanced === "1") return;
    const body = editor.querySelector("[data-model-editor-body]");
    const jsonInput = editor.querySelector("[data-model-json]");
    if (!body || !jsonInput) return;
    editor.dataset.enhanced = "1";

    const rows = () => [...body.querySelectorAll("[data-model-entry]")];
    const metadata = new Map(JSON.parse(jsonInput.value || "[]").map((entry) => [entry.id, entry]));
    rows().forEach((row) => { row.dataset.originalModelId = row.querySelector('[data-model-id]')?.value || ''; });
    const sync = () => {
      const entries = rows().map((row) => ({ ...metadata.get(row.dataset.originalModelId), ...modelEntryFromValues(
        row.querySelector("[data-model-id]")?.value,
        row.querySelector("[data-model-label]")?.value,
        row.querySelector("[data-model-enabled]")?.checked,
        row.querySelector("[data-model-capability]")?.value,
      ), media_type: row.querySelector("[data-model-capability]")?.value || "", api_format: row.querySelector("[data-entry-protocol]")?.value || "",
      upstream_id: row.querySelector('[data-model-upstream]')?.value.trim() || row.querySelector('[data-model-id]')?.value.trim(),
      managed: row.querySelector('[data-model-managed]')?.checked === true,
      cost_amount: row.querySelector('[data-model-cost]')?.value.trim() || '',
      cost_currency: row.querySelector('[data-model-currency]')?.value || 'CNY',
      cost_unit: row.querySelector('[data-model-cost-unit]')?.value || 'request' })).filter((entry) => entry.id);
      jsonInput.value = JSON.stringify(entries);
    };
    const addRow = (entry = { id: "", label: "", enabled: false, media_type: editor.dataset.modelKind === "audio" ? "speech" : editor.dataset.modelKind === "mixed" ? "" : editor.dataset.modelKind }) => {
      if (entry.id) metadata.set(entry.id, entry);
      const row = document.createElement("tr");
      row.dataset.modelEntry = "";
      row.dataset.originalModelId = entry.id || '';
      const capabilityCell = `<td><select data-model-capability aria-label="模型类型">${[["","待分类"],["image","图片生成"],["video","视频生成"],["speech","语音合成"],["music","音乐生成"],["prompt","对话"]].map(([value,label]) => `<option value="${value}" ${entry.media_type === value ? "selected" : ""}>${label}</option>`).join("")}</select></td>`;
      row.innerHTML = `
        <td><input data-model-label aria-label="模型展示名称" value="${escapeAttribute(entry.label)}"></td>
        <td><input data-model-id aria-label="平台模型 ID" placeholder="平台模型 ID" value="${escapeAttribute(entry.id)}"><input data-model-upstream aria-label="渠道调用 ID" placeholder="默认同平台 ID" value="${escapeAttribute(entry.upstream_id || entry.id)}"></td>
        ${capabilityCell}
        <td><select data-entry-protocol aria-label="模型调用协议">${[["","跟随渠道"],["openai","OpenAI 兼容"],["gemini","Gemini"],["banana","Nano Banana"],["grok","Grok"],["jiasuapi","JiasuAPI"],["minimax","MiniMax"],["seedance","Seedance 官方"],["dmc_h3","DMC H3"],["seedance_media","Seedance Media"]].map(([value,label]) => `<option value="${value}" ${entry.api_format === value ? "selected" : ""}>${label}</option>`).join("")}</select></td>
        <td><small>保存后检查上架条件</small><a href="/admin/config/billing">配置售价</a><small>尚未验证</small><label><input type="checkbox" data-model-managed checked>明确售价后上架</label></td>
        <td><input type="checkbox" data-model-enabled aria-label="启用模型" ${entry.enabled !== false ? "checked" : ""}></td>
        <td><button type="button" data-model-remove aria-label="删除模型">删除</button></td>`;
      body.appendChild(row);
      const costs = document.createElement('details');
      costs.innerHTML = `<summary>渠道成本</summary><input data-model-cost aria-label="渠道成本金额" inputmode="decimal" placeholder="未记录"><select data-model-currency aria-label="成本币种"><option value="CNY">CNY</option><option value="USD">USD</option></select><select data-model-cost-unit aria-label="成本单位"><option value="request">每次</option><option value="image">每张</option><option value="second">每秒</option><option value="1000_chars">每千字符</option><option value="1000_tokens">每千Token</option></select><small>仅成本记录，不参与用户扣费。</small>`;
      row.querySelector('[data-entry-protocol]').parentElement.appendChild(costs);
      sync();
      row.querySelector("[data-model-id]")?.focus();
    };
    const fetchModelsButton = editor.querySelector("[data-fetch-models-editor]");
    const fetchModelsStatus = editor.querySelector("[data-model-fetch-editor-status]");
    fetchModelsButton?.addEventListener("click", async () => {
      const providerId = fetchModelsButton.dataset.fetchModelsEditor;
      if (!providerId) return;
      fetchModelsButton.disabled = true;
      if (fetchModelsStatus) fetchModelsStatus.textContent = "正在获取…";
      try {
        const response = await fetch(`/settings/providers/${encodeURIComponent(providerId)}/models`, { headers: { Accept: "application/json", "X-Requested-With": "fetch" } });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || "获取失败");
        const current = rows().map((row) => modelEntryFromValues(row.querySelector("[data-model-id]")?.value, row.querySelector("[data-model-label]")?.value, row.querySelector("[data-model-enabled]")?.checked, row.querySelector("[data-model-capability]")?.value)).filter((entry) => entry.id);
        const merged = mergeFetchedModels(current, result.models);
        const currentIds = new Set([...current.map((entry) => entry.id),...rows().map(row=>row.querySelector('[data-model-upstream]')?.value).filter(Boolean)]);
        const pending = merged.filter((entry) => !currentIds.has(entry.id));
        const preview = document.createElement("div");
        preview.className = "provider-model-catalog-preview";
        pending.forEach((entry) => {
          const label = document.createElement("label");
          const check = document.createElement("input"); check.type = "checkbox"; check.value = entry.id;
          const kindLabels = {image:"图片",video:"视频",speech:"语音",music:"音乐",prompt:"对话"};
          label.append(check, document.createTextNode(` ${entry.label} · ${entry.id} · ${kindLabels[entry.media_type] || "待分类"}`));
          preview.appendChild(label);
        });
        const apply = document.createElement("button"); apply.type = "button"; apply.textContent = "添加勾选模型";
        apply.onclick = () => {
          const selected = new Set([...preview.querySelectorAll("input:checked")].map((input) => input.value));
          pending.filter((entry) => selected.has(entry.id)).forEach((entry) => addRow(entry));
          preview.remove();
          if (fetchModelsStatus) fetchModelsStatus.textContent = `已添加 ${selected.size} 个模型，保存后生效；新模型默认停用`;
        };
        preview.appendChild(apply);
        editor.querySelector(".provider-model-catalog-preview")?.remove();
        if (pending.length) editor.appendChild(preview);
        if (fetchModelsStatus) fetchModelsStatus.textContent = result.warning || (pending.length ? `获取到 ${pending.length} 个新模型，请勾选添加` : "目录中没有新模型");
      } catch (error) {
        if (fetchModelsStatus) fetchModelsStatus.textContent = `获取失败：${error.message}`;
      } finally {
        fetchModelsButton.disabled = false;
      }
    });
    editor.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest("[data-model-add]")) {
        event.preventDefault();
        addRow();
        return;
      }
      const remove = target.closest("[data-model-remove]");
      if (remove) {
        event.preventDefault();
        const row = remove.closest("[data-model-entry]");
        if (row) row.remove();
        if (!rows().length) addRow(); else sync();
      }
    });
    editor.addEventListener("input", sync);
    editor.closest("form")?.addEventListener("submit", sync);
    sync();
  }

  function escapeAttribute(value) {
    return String(value || "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
  }

  function enhance(documentRoot) {
    const catalogNode = documentRoot.getElementById("image-provider-catalog");
    const catalog = parseImageProviderCatalog(catalogNode?.textContent);
    if (!catalog) return false;
    documentRoot.querySelectorAll("[data-model-protocol]").forEach((protocolSelect) => {
      const container = protocolSelect.closest("dialog") || protocolSelect.closest("form");
      if (container) enhanceForm(container, catalog);
    });
    documentRoot.querySelectorAll("[data-model-editor]").forEach((editor) => enhanceModelEditor(editor.closest("form") || editor));
    const providerFilter = documentRoot.querySelector("[data-provider-filter]");
    providerFilter?.addEventListener("input", () => {
      const query = providerFilter.value.trim().toLowerCase();
      documentRoot.querySelectorAll("[data-provider-row]").forEach((row) => {
        row.hidden = Boolean(query && !String(row.dataset.providerSearch || "").includes(query));
      });
    });
    documentRoot.querySelectorAll("[data-fetch-models]").forEach((button) => {
      button.addEventListener("click", async () => {
        const dialog = button.closest("dialog");
        const select = dialog?.querySelector("[data-test-model]");
        const status = dialog?.querySelector("[data-model-fetch-status]");
        button.disabled = true;
        if (status) status.textContent = "正在获取…";
        try {
          const testForm = dialog?.querySelector("form");
          const csrf = testForm?.querySelector("[name=csrf_token]")?.value || "";
          const response = await fetch(`/settings/providers/${button.dataset.fetchModels}/models`, { headers: { Accept: "application/json", "X-Requested-With": "fetch" } });
          const result = await response.json();
          if (!response.ok || !result.ok) throw new Error(result.error || "获取失败");
          const current = select?.value;
          select.replaceChildren(...result.models.map((model) => new Option(model.label, model.id)));
          if ([...select.options].some((option) => option.value === current)) select.value = current;
          if (status) status.textContent = result.warning ? `已使用配置目录：${result.warning}` : `已获取 ${result.models.length} 个模型（${result.source === "builtin" ? "文档内置" : "远程目录"}）`;
          select.dataset.catalog = JSON.stringify(result.models);
          select.dispatchEvent(new Event("change"));
        } catch (error) {
          if (status) status.textContent = `获取失败：${error.message}`;
        } finally { button.disabled = false; }
      });
    });
    documentRoot.querySelectorAll(".provider-test-dialog form").forEach((form) => {
      const testCacheKey = `huishi:provider-test:${form.getAttribute("action")}`;
      const cachedTest = () => { try { return JSON.parse(sessionStorage.getItem(testCacheKey) || "{}"); } catch (_) { return {}; } };
      const resumeButton = documentRoot.createElement("button");
      resumeButton.type = "button";
      resumeButton.textContent = "查看上次测试";
      resumeButton.hidden = !cachedTest().taskId;
      form.querySelector("footer")?.prepend(resumeButton);
      resumeButton.addEventListener("click", () => { form.dataset.resumeTest = "1"; form.requestSubmit(); });
      const modelSelect = form.querySelector("[data-test-model]");
      const syncTestParameters = () => {
        const model = JSON.parse(modelSelect?.dataset.catalog || "[]").find((entry) => entry.id === modelSelect.value);
        const caps = model?.capabilities || {};
        const kind = form.dataset.providerKind === "mixed" ? (model?.media_type || "") : form.dataset.providerKind;
        const videoFields = form.querySelector("[data-video-test-fields]");
        if (videoFields) {
          videoFields.style.display = kind === "video" ? "" : "none";
          videoFields.querySelectorAll("input,select").forEach((input) => { input.disabled = kind !== "video"; });
        }
        if (form.dataset.providerKind === "mixed") {
          const heading = form.querySelector("h3");
          if (heading) heading.textContent = ({image:"生图测试",video:"视频测试",speech:"语音测试",music:"音乐测试",prompt:"对话测试"})[kind] || "模型测试";
          const hint = form.querySelector(".provider-test-hint");
          if (hint) hint.textContent = kind ? "按所选模型类型实际生成并展示结果，会产生渠道费用。关闭窗口不会取消任务。" : "先在渠道编辑窗口添加模型、确认类型并保存，再开始测试。";
          const submit = form.querySelector("[type=submit]");
          if (submit) submit.disabled = !kind;
        }
        const durationSelect = form.querySelector("[data-test-duration-select]");
        const durationRangeField = form.querySelector("[data-test-duration-range]");
        const durationSlider = form.querySelector("[data-test-duration-slider]");
        const durationValue = form.querySelector("[data-test-duration-value]");
        const range = caps.duration_range;
        const durations = [...new Set((Array.isArray(caps.durations) ? caps.durations : []).map(Number).filter((value) => Number.isInteger(value) && value > 0))].sort((a, b) => a - b);
        const rangeValid = Number.isInteger(Number(range?.min)) && Number.isInteger(Number(range?.max)) && Number.isInteger(Number(range?.step || 1)) && Number(range.min) > 0 && Number(range.max) >= Number(range.min) && Number(range.step || 1) > 0;
        if (durationSelect && durationRangeField && durationSlider && durationValue) {
          const useRange = kind === "video" && rangeValid;
          const durationSelectWrap = form.querySelector("[data-test-duration-select-wrap]");
          if (durations.length) {
            const previous = Number(durationSelect.value);
            durationSelect.replaceChildren(...durations.map((value) => new Option(String(value), String(value))));
            durationSelect.value = String(durations.includes(previous) ? previous : durations[0]);
          }
          if (durationSelectWrap) durationSelectWrap.hidden = useRange;
          durationRangeField.hidden = !useRange;
          durationSelect.disabled = kind !== "video" || useRange || durations.length === 1;
          durationSlider.disabled = !useRange;
          durationValue.disabled = !useRange;
          if (useRange) {
            durationSlider.min = String(range.min);
            durationSlider.max = String(range.max);
            durationSlider.step = String(range.step || 1);
            durationSlider.value = String(range.min);
            durationSlider.setAttribute("aria-valuetext", `${range.min} 秒`);
            durationValue.value = String(range.min);
            form.querySelector("[data-test-duration-output]").textContent = `${range.min} 秒`;
          }
        }
        for (const [name, values] of [["test_resolution", caps.resolutions], ["test_ratio", caps.ratios]]) {
          const select = form.querySelector(`[name=${name}]`);
          if (select && Array.isArray(values) && values.length) {
            const previous = select.value;
            select.replaceChildren(...values.map((value) => new Option(String(value), String(value))));
            if (values.map(String).includes(previous)) select.value = previous;
          }
        }
        const omni = (caps.modes || []).includes("omni_reference");
        const mode = form.querySelector("[name=reference_mode]");
        if (mode) {
          const previous = mode.value;
          const modes = omni ? [["reference","全能参考"],["first_frame","首帧"],["last_frame","尾帧"],["keyframes","首尾帧（按上传顺序）"]] : [["reference","参考图片"]];
          mode.replaceChildren(...modes.map(([value,label]) => new Option(label,value)));
          if (modes.some(([value]) => value === previous)) mode.value = previous;
        }
        const files = form.querySelector("[name=media_references]");
        if (files) files.accept = omni ? "image/*,video/mp4,video/quicktime,audio/*" : "image/*";
        const hint = form.querySelector("[data-test-reference-hint]");
        if (hint) hint.textContent = omni ? "不上传为文生；图片≤9、视频≤3、音频≤3，合计≤12。音视频至少2秒，超过15秒使用片头15秒；各类有效总长≤15秒。首尾帧与全能参考不可混用。" : `不上传即为文生视频；参考图片最多${caps.max_reference_images || 9}张。`;
        const camera = form.querySelector("[data-test-camera]");
        if (camera) { camera.hidden = !caps.camera_movement; camera.style.display = caps.camera_movement ? "" : "none"; }
        const prompt = form.querySelector("[name=test_prompt]");
        if (prompt) prompt.maxLength = caps.max_prompt_chars || 7000;
      };
      form.querySelector("[data-test-duration-slider]")?.addEventListener("input", (event) => {
        const slider = event.currentTarget;
        const value = form.querySelector("[data-test-duration-value]");
        if (value) value.value = slider.value;
        slider.setAttribute("aria-valuetext", `${slider.value} 秒`);
        const output = form.querySelector("[data-test-duration-output]");
        if (output) output.textContent = `${slider.value} 秒`;
      });
      modelSelect?.addEventListener("change", syncTestParameters);
      syncTestParameters();
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = form.querySelector("[type=submit]");
        const result = form.querySelector("[data-test-result]");
        button.disabled = true;
        if (result) { result.className = "provider-test-result is-running"; result.textContent = "正在测试，请稍候…"; }
        try {
          const submitted = new FormData(form);
          const cached = cachedTest();
          const identity = JSON.stringify([...submitted.entries()].filter(([key]) => key !== "csrf_token").map(([key,value]) => [key,value instanceof File ? [value.name,value.size,value.lastModified] : value]));
          const requestKey = cached.requestKey && cached.identity === identity ? cached.requestKey : crypto.randomUUID();
          submitted.set("request_key", requestKey);
          let payload;
          if (cached.taskId && (cached.pending || form.dataset.resumeTest === "1")) payload = {ok:true,task_id:cached.taskId};
          else {
            sessionStorage.setItem(testCacheKey, JSON.stringify({requestKey,identity}));
            const response = await fetch(form.action, { method: "POST", headers: { Accept: "application/json" }, body: submitted, redirect: "follow" });
            payload = await response.json().catch(() => ({}));
            if (!response.ok || payload.ok === false) {
              if (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) sessionStorage.removeItem(testCacheKey);
              throw new Error(payload.error || payload.message || `服务器返回 HTTP ${response.status}`);
            }
          }
          delete form.dataset.resumeTest;
          if (payload.task_id) {
            sessionStorage.setItem(testCacheKey, JSON.stringify({taskId:payload.task_id,pending:true}));
            resumeButton.hidden = false;
            form.dataset.taskId = String(payload.task_id);
            const phases = { submitting: "正在提交", polling: "正在生成", persisting: "正在保存", settling: "正在入库", needs_reconciliation: "待管理员核对" };
            for (;;) {
              const statusResponse = await fetch(`/api/generation/tasks/${encodeURIComponent(payload.task_id)}`, { headers: { Accept: "application/json" }, cache: "no-store" });
              const state = await statusResponse.json();
              if (!statusResponse.ok || !state.ok) throw new Error(state.error || "查询任务失败，可到资产库查看");
              const task = state.task;
              if (task.status === "failed") { sessionStorage.setItem(testCacheKey, JSON.stringify({taskId:payload.task_id,pending:false})); delete form.dataset.requestKey; throw new Error(task.error_message || "视频生成失败"); }
              if (task.status === "succeeded") {
                payload.video = task.record?.image_path;
                payload.message = "视频已生成并保存";
                delete form.dataset.requestKey;
                sessionStorage.setItem(testCacheKey, JSON.stringify({taskId:payload.task_id,pending:false}));
                break;
              }
              if (task.phase === "needs_reconciliation") throw new Error(`任务 ${payload.task_id} 待管理员核对：${task.recovery_error || "请核对上游状态"}；不会重新生成`);
              if (result) result.textContent = `${phases[task.phase] || "正在排队"} · 任务 ${payload.task_id}${task.recovery_error ? ` · ${task.recovery_error}` : ""}`;
              await new Promise((resolve) => setTimeout(resolve, 4000));
            }
          } else { delete form.dataset.requestKey; }
          if (result) {
            result.className = "provider-test-result is-ok";
            result.textContent = payload.video_task_id ? `${payload.message || "测试成功"}，任务 ID：${payload.video_task_id}` : (payload.message || "测试成功");
            if (payload.text) {
              const text = documentRoot.createElement("p"); text.className = "provider-test-text"; text.textContent = payload.text; result.appendChild(text);
            }
            const imageUrl = testImageUrl(payload.image, documentRoot);
            if (imageUrl) {
              const image = new Image(); image.src = imageUrl; image.alt = "测试生成图片"; image.className = "provider-test-image";
              image.addEventListener("error", () => { image.replaceWith("测试图片加载失败，请检查资源目录权限或存储配置"); });
              result.appendChild(image);
            }
            const videoUrl = testImageUrl(payload.video, documentRoot);
            if (videoUrl) {
              const video = documentRoot.createElement("video"); video.src = videoUrl; video.controls = true; video.preload = "metadata"; video.className = "provider-test-video"; result.appendChild(video);
            } else if (payload.video_task_id && payload.video_status === "pending") {
              const pending = documentRoot.createElement("small"); pending.className = "provider-test-pending"; pending.textContent = "视频仍在生成，请稍后到业务流水或资产库查看结果。"; result.appendChild(pending);
            }
            const audioUrl = testImageUrl(payload.audio, documentRoot);
            if (audioUrl) {
              const audio = documentRoot.createElement("audio");
              audio.src = audioUrl;
              audio.controls = true;
              audio.preload = "metadata";
              audio.className = "provider-test-audio";
              result.appendChild(audio);
            }
          }
        } catch (error) {
          if (result) { result.className = "provider-test-result is-error"; result.textContent = `测试失败：${error.message}`; }
        } finally { button.disabled = false; }
      });
    });
    documentRoot.querySelectorAll('[data-provider-restore]').forEach((form) => {
      if (form.dataset.enhanced === '1') return;
      form.dataset.enhanced = '1';
      const result = form.querySelector('[data-restore-result]');
      const confirm = form.querySelector('[data-restore-confirm]');
      form.addEventListener('input',()=>{ confirm.hidden=true; });
      form.addEventListener('submit',async(event)=>{
        event.preventDefault();
        const confirming=event.submitter?.value==='1';
        const body=new FormData(form);
        body.set('confirm',confirming?'1':'0');
        form.querySelectorAll('button').forEach(button=>{button.disabled=true;});
        result.textContent=confirming?'正在恢复…':'正在解密并检查配置…';
        try {
          const response=await fetch(form.action,{method:'POST',body,headers:{Accept:'application/json'}});
          const payload=await response.json();
          if (!response.ok || !payload.ok) throw new Error(payload.error || '操作失败');
          if (payload.preview) {
            const p=payload.preview;
            result.textContent=`${p.connections} 个渠道，${p.models} 个模型绑定，${p.prices} 条定价。${p.conflicts.length ? `存在价格冲突：${p.conflicts.join('、')}` : p.message}`;
            confirm.hidden=p.conflicts.length>0;
          } else {
            result.textContent=payload.message;
            confirm.hidden=true;
            form.querySelector('[name=backup_password]').value='';
          }
        } catch(error) { result.textContent=error.message; confirm.hidden=true; }
        finally {form.querySelectorAll('button').forEach(button=>{button.disabled=false;});}
      });
    });
    return true;
  }

  return { defaultUrlFor, enhance, mergeFetchedModels, modelEntryFromValues, parseImageProviderCatalog, protocolStateFor, rememberProtocolState, testImageUrl };
});
