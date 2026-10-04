(() => {
  'use strict';
  const root = document.querySelector('[data-model-management]');
  if (!root) return;
  const base = root.dataset.api;
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];
  const kindNames = {image: '图片生成', video: '视频生成', speech: '语音合成', music: '音乐生成', prompt: '对话'};
  const stateNames = {published: '已上架', active: '已上架', pending: '待完善', draft: '草稿', disabled: '已停用', legacy: '沿用旧配置', queued: '排队中', running: '执行中', succeeded: '成功', failed: '失败'};
  const protocols = {openai: 'OpenAI 兼容', gemini: 'Gemini', banana: 'Nano Banana', grok: 'Grok', jiasuapi: 'JiasuAPI', minimax: 'MiniMax', seedance: 'Seedance 官方', dmc_h3: 'DMC H3', seedance_media: 'Seedance Media'};
  let catalog = {connections: [], models: [], issues: []};
  let connection = null, editing = null, discoveries = [], selectedImports = new Set(), discoveryStates = new Map(), calls = [], page = 1;
  let dirty = false, providerFilter = null;
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
  };
  const button = (text, action) => { const node = el('button', text); node.type = 'button'; node.addEventListener('click', action); return node; };
  const feedback = (node, text = '', error = false) => { node.textContent = text; node.dataset.error = String(error); };
  const dialogFeedback = (dialog, text = '', error = false) => feedback($('[data-mm-dialog-status]', dialog), text, error);
  const empty = (body, count, text) => { const tr = el('tr'); const td = el('td', text, 'mm-empty'); td.colSpan = count; tr.append(td); body.replaceChildren(tr); };
  const status = (state, label) => { const node = el('span', label || stateNames[state] || state, 'mm-status'); node.dataset.state = state; return node; };
  const field = (label, input) => { const node = el('label', label); node.append(input); return node; };
  const input = (type, value, label) => { const node = el('input'); node.type = type; node.value = value ?? ''; if (label) node.setAttribute('aria-label', label); return node; };
  const select = (options, value, label) => {
    const node = el('select');
    Object.entries(options).forEach(([id, name]) => { const option = el('option', name); option.value = id; node.append(option); });
    node.value = value ?? ''; if (label) node.setAttribute('aria-label', label); return node;
  };
  const summary = (cell, title, subtitle) => { cell.append(el('strong', title)); if (subtitle) cell.append(el('small', subtitle)); };
  const modelKey = m => `${m.media_type || ''}:${m.id}`;
  async function request(path, body) {
    const response = await fetch(base + path, {method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers: {'Accept': 'application/json', 'X-Requested-With': 'fetch', 'X-CSRF-Token': root.dataset.csrf, ...(body === undefined ? {} : {'Content-Type': 'application/json'})}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    let data;
    try { data = await response.json(); } catch (_) { throw new Error(response.status === 401 || response.redirected ? '登录已过期，请刷新页面后重新登录。' : `服务返回异常（${response.status}），请重试。`); }
    if (!response.ok || !data.ok) throw new Error(data.error || `操作失败（${response.status}）`);
    return data;
  }
  async function busy(form, callback) {
    if (form.dataset.busy === 'true') return;
    form.dataset.busy = 'true';
    const buttons = $$('button', form); const disabled = buttons.map(b => b.disabled);
    buttons.forEach(b => { b.disabled = true; }); form.setAttribute('aria-busy', 'true');
    try { await callback(); } catch (error) { dialogFeedback(form.closest('dialog'), error.message, true); }
    finally { buttons.forEach((b, i) => { b.disabled = disabled[i]; }); form.removeAttribute('aria-busy'); form.dataset.busy = 'false'; }
  }
  function showDialog(dialog) { dialogFeedbackIfPresent(dialog); dialog.showModal(); dialog.scrollTop = 0; }
  function dialogFeedbackIfPresent(dialog) { const node = $('[data-mm-dialog-status]', dialog); if (node) feedback(node); }
  $$('.mm-dialog [data-mm-close]').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));
  $$('.mm-dialog').forEach(d => d.addEventListener('close', () => { if (d.id === 'mm-connection') { $('[name=api_key]', d).value = ''; $('[name=proxy_url]', d).value = ''; } }));

  function chooseTab(name) {
    $$('[data-mm-tab]', root).forEach(tab => { const current = tab.dataset.mmTab === name; tab.setAttribute('aria-selected', String(current)); tab.tabIndex = current ? 0 : -1; });
    $$('[role=tabpanel]', root).forEach(panel => { panel.hidden = panel.id !== `mm-${name}`; });
    if (name === 'calls') loadCalls();
  }
  $$('[data-mm-tab]', root).forEach(tab => {
    tab.addEventListener('click', () => chooseTab(tab.dataset.mmTab));
    tab.addEventListener('keydown', event => {
      const tabs = $$('[data-mm-tab]', root); let index = tabs.indexOf(tab);
      if (event.key === 'ArrowRight') index = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') index = (index + tabs.length - 1) % tabs.length;
      else if (event.key === 'Home') index = 0;
      else if (event.key === 'End') index = tabs.length - 1;
      else return;
      event.preventDefault(); tabs[index].focus(); chooseTab(tabs[index].dataset.mmTab);
    });
  });
  async function refresh(message = '') {
    const data = await request('/catalog'); catalog = data;
    renderConnections(); renderModels(); renderIssues();
    feedback($('[data-mm-feedback]', root), message);
  }
  function renderConnections() {
    const body = $('[data-mm-connections]', root); body.replaceChildren();
    const query = $('[data-mm-search=connections]', root).value.toLowerCase();
    catalog.connections.filter(p => `${p.name} ${p.base_url}`.toLowerCase().includes(query)).forEach(p => {
      const row = el('tr'); const cells = Array.from({length: 5}, () => el('td'));
      summary(cells[0], p.name, protocols[p.api_format] || p.api_format);
      const address = el('span', p.base_url || '未配置地址', 'mm-address'); address.title = p.base_url || ''; cells[1].append(address, el('small', `${p.proxy_configured ? '已配置代理' : '直连'} · ${p.has_key ? 'Key 已保存' : '缺少 Key'}`));
      cells[2].append(button(`${p.model_count} 个模型`, () => { $('[data-mm-search=models]', root).value = ''; providerFilter = p.id; chooseTab('models'); renderModels(); }));
      cells[3].append(status(p.enabled ? 'active' : 'disabled', p.enabled ? '启用' : '停用'));
      const actions = el('div', undefined, 'mm-actions');
      actions.append(button('编辑', () => openConnection(p)), button('获取模型', () => { openConnection(p); discover(); }), button('测试', () => testConnection(p)));
      cells[4].append(actions); row.append(...cells); body.append(row);
    });
    if (!body.children.length) empty(body, 5, query ? '没有匹配的渠道。' : '尚未配置渠道，点击“新增渠道”开始。');
  }
  function displayState(m) { return m.state === 'published' ? 'active' : (m.state === 'legacy' ? (m.available_count ? 'active' : 'pending') : m.state || 'draft'); }
  function renderModels() {
    const providerId = providerFilter;
    const filter = $('[data-mm-provider-filter]', root);
    filter.hidden = !providerId;
    filter.textContent = providerId ? `${catalog.connections.find(p => p.id === providerId)?.name || '渠道'} · 清除筛选` : '';
    const body = $('[data-mm-models]', root); body.replaceChildren();
    const query = $('[data-mm-search=models]', root).value.toLowerCase(), kind = $('[data-mm-kind]', root).value, state = $('[data-mm-state]', root).value;
    catalog.models.filter(m => (!query || `${m.label} ${m.id} ${m.bindings.map(b => b.upstream_id).join(' ')}`.toLowerCase().includes(query)) && (!kind || (kind === 'unknown' ? !m.media_type : m.media_type === kind)) && (!state || displayState(m) === state) && (!providerId || m.bindings.some(b => b.provider_id === providerId))).forEach(m => {
      const row = el('tr'), cells = Array.from({length: 6}, () => el('td'));
      summary(cells[0], m.label || m.id, m.id); cells[1].textContent = kindNames[m.media_type] || '待分类';
      summary(cells[2], `${m.available_count || 0} / ${m.bindings.length}`, m.bindings.map(b => b.provider_name).join('、'));
      const prices = m.prices.filter(p => p.enabled);
      cells[3].textContent = m.media_type === 'prompt' ? '助手不单独计费' : prices.length ? `${Math.min(...prices.map(p => p.points))}–${Math.max(...prices.map(p => p.points))} 积分` : '未定价';
      cells[4].append(status(displayState(m)));
      if (!m.available_count && m.reasons?.length) cells[4].append(el('small', m.reasons.join('、')));
      const actions = el('div', undefined, 'mm-actions'); actions.append(button('配置', () => openModel(m)), button('预览调度', () => openPreview(m))); cells[5].append(actions);
      row.append(...cells); body.append(row);
    });
    if (!body.children.length) empty(body, 6, '没有匹配的模型。可在渠道连接中获取或手动添加。');
  }
  function renderIssues() {
    const list = $('[data-mm-issues]', root);
    if (!list) return;
    list.replaceChildren();
    (catalog.issues || []).forEach(issue => list.append(el('li', typeof issue === 'string' ? issue : issue.message || issue.reason || JSON.stringify(issue))));
    const count = $('[data-mm-issue-count]', root);
    if (count) count.textContent = catalog.issues?.length ? `（${catalog.issues.length} 项）` : '';
    if (!list.children.length) list.append(el('li', '未发现孤立价格规则。'));
  }
  $$('[data-mm-search]', root).forEach(n => n.addEventListener('input', () => n.dataset.mmSearch === 'connections' ? renderConnections() : renderModels()));
  $('[data-mm-kind]', root).addEventListener('change', () => renderModels()); $('[data-mm-state]', root).addEventListener('change', () => renderModels());
  $('[data-mm-provider-filter]', root).addEventListener('click', () => { providerFilter = null; renderModels(); });

  const connectionDialog = $('#mm-connection'), connectionForm = $('[data-mm-connection-form]');
  function openConnection(p = null) {
    connection = p; discoveries = []; selectedImports = new Set(); discoveryStates = new Map(); connectionForm.reset();
    $('#mm-connection-title').textContent = p ? '编辑渠道' : '新增渠道';
    for (const name of ['name', 'base_url', 'backup_base_url', 'api_format', 'priority', 'max_concurrency']) connectionForm.elements[name].value = p?.[name] ?? ({api_format: 'openai', priority: 100}[name] || '');
    connectionForm.elements.rpm.value = p?.requests_per_minute || '';
    connectionForm.elements.enabled.checked = p?.enabled || false;
    connectionForm.elements.api_key.required = !p?.has_key;
    $('[data-mm-key-hint]').textContent = p?.has_key ? '已保存；留空保持原 Key。' : 'Key 仅保存在服务器，不返回到页面。';
    $('[data-mm-proxy-hint]').textContent = p?.proxy_configured ? '已保存代理；留空保持原值，勾选下方选项可清除。' : '留空直连。';
    $('[data-mm-discovery]').hidden = true; $('[data-mm-manual]').hidden = true;
    $('details', connectionForm).open = false; showDialog(connectionDialog);
  }
  $('[data-mm-new-connection]').addEventListener('click', () => openConnection());
  function draftConnection() {
    const f = connectionForm.elements;
    const data = {name: f.name.value.trim(), base_url: f.base_url.value.trim(), backup_base_url: f.backup_base_url.value.trim(), api_key: f.api_key.value.trim(), api_format: f.api_format.value, enabled: f.enabled.checked, priority: Number(f.priority.value), max_concurrency: f.max_concurrency.value ? Number(f.max_concurrency.value) : 0, requests_per_minute: f.rpm.value ? Number(f.rpm.value) : 0};
    if (connection) Object.assign(data, {id: connection.id, revision: connection.revision});
    if (f.clear_proxy.checked) data.proxy_url = '';
    else if (f.proxy_url.value.trim() || !connection) data.proxy_url = f.proxy_url.value.trim();
    return data;
  }
  async function discover() {
    if (!connectionForm.reportValidity()) return;
    await busy(connectionForm, async () => {
      dialogFeedback(connectionDialog, '正在读取模型目录…');
      const data = await request('/discover', draftConnection()); discoveries = data.models || []; selectedImports = new Set(); discoveryStates = new Map(); renderDiscovery();
      dialogFeedback(connectionDialog, data.warning || `获取到 ${discoveries.length} 个模型。勾选需要添加的模型，保存后进入草稿。`);
    });
  }
  $('[data-mm-discover]').addEventListener('click', discover);
  const existingBinding = model => connection && catalog.models.flatMap(modelEntry => modelEntry.bindings.filter(b => b.provider_id === connection.id && (b.upstream_id === model.id || modelEntry.id === model.id))).find(Boolean);
  function renderDiscovery() {
    $('[data-mm-discovery]').hidden = false;
    const list = $('[data-mm-discovery-list]'); list.replaceChildren();
    const query = $('[data-mm-discovery-search]').value.toLowerCase(), kind = $('[data-mm-discovery-kind]').value;
    discoveries.filter(m => `${m.id} ${m.label}`.toLowerCase().includes(query) && (!kind || (kind === 'unknown' ? !m.media_type : kind === m.media_type))).forEach(m => {
      const current = existingBinding(m), row = el('label'), check = input('checkbox', m.id);
      check.checked = current ? (discoveryStates.has(m.id) ? discoveryStates.get(m.id) : current.enabled !== false) : selectedImports.has(m.id);
      const meta = el('small');
      const updateMeta = () => { meta.textContent = `${m.id} · ${kindNames[m.media_type] || '待分类'}${current ? (check.checked ? ' · 已添加 · 当前启用' : ' · 已添加 · 当前停用') : ''}`; };
      updateMeta();
      check.addEventListener('change', () => {
        if (current) discoveryStates.set(m.id, check.checked);
        else check.checked ? selectedImports.add(m.id) : selectedImports.delete(m.id);
        updateMeta(); updateSelection();
      });
      const text = el('span', m.label || m.id); text.append(meta); row.append(check, text); list.append(row);
    });
    if (!list.children.length) list.append(el('p', '没有匹配的模型。', 'mm-note')); updateSelection();
  }
  function updateSelection() {
    const enabled = discoveries.filter(m => {
      const current = existingBinding(m);
      return current && (discoveryStates.has(m.id) ? discoveryStates.get(m.id) : current.enabled !== false);
    }).length;
    $('[data-mm-selection-count]').textContent = `已选 ${selectedImports.size} 个新模型 · 启用 ${enabled} 个已有模型`;
  }
  $('[data-mm-discovery-search]').addEventListener('input', renderDiscovery); $('[data-mm-discovery-kind]').addEventListener('change', renderDiscovery);
  $('[data-mm-select-visible]').addEventListener('click', () => {
    $$('input', $('[data-mm-discovery-list]')).forEach(c => {
      const model = discoveries.find(m => m.id === c.value), current = model && existingBinding(model);
      c.checked = true;
      if (current) discoveryStates.set(c.value, true); else selectedImports.add(c.value);
    });
    renderDiscovery();
  });
  $('[data-mm-manual-import]').addEventListener('click', () => { $('[data-mm-manual]').hidden = false; $('[data-mm-manual-id]').focus(); });
  $('[data-mm-add-manual]').addEventListener('click', () => {
    const id = $('[data-mm-manual-id]').value.trim(); if (!id) return;
    if (!discoveries.some(m => m.id === id)) discoveries.push({id, label: id, media_type: ''});
    selectedImports.add(id); $('[data-mm-manual-id]').value = ''; renderDiscovery();
  });
  connectionForm.addEventListener('submit', event => {
    event.preventDefault(); busy(connectionForm, async () => {
      const saved = await request('/connections', draftConnection()); connection = saved.connection;
      const existingStates = discoveries.map(m => {
        const current = existingBinding(m); if (!current) return null;
        return {id: m.id, enabled: discoveryStates.has(m.id) ? discoveryStates.get(m.id) : current.enabled !== false};
      }).filter(Boolean);
      if (selectedImports.size || existingStates.length) {
        try { const imported = await request('/import', {provider_id: connection.id, revision: connection.revision, models: discoveries.filter(m => selectedImports.has(m.id)), states: existingStates}); connection = imported.connection; }
        catch (error) { await refresh(); throw new Error(`连接已保存，模型尚未导入：${error.message}`); }
      }
      await refresh('渠道已保存。新增模型可在“模型与定价”中完善后上架。'); dirty = true; connectionDialog.close();
    });
  });
  function testConnection(p) {
    if (dirty) { const url = new URL(window.location.href); url.searchParams.set('test_provider', p.id); url.hash = 'settings-image'; window.location.assign(url); return; }
    const dialog = document.getElementById(`test-provider-${p.id}`);
    if (dialog && p.model_count) dialog.showModal();
    else feedback($('[data-mm-feedback]', root), '请先添加并保存模型，再打开测试窗口。');
  }

  const modelDialog = $('#mm-model'), modelForm = $('[data-mm-model-form]');
  function openModel(m) {
    editing = structuredClone(m); modelForm.reset();
    editing.original_media_type = m.media_type;
    editing.priceUnits = {};
    modelForm.elements.label.value = m.label || m.id; modelForm.elements.media_type.value = m.media_type || '';
    modelForm.elements.media_type.disabled = m.legacy || m.bindings.some(b => b.enabled);
    $('[data-mm-model-identity]').textContent = `平台 ID：${m.id}`;
    $('[data-mm-model-status]').textContent = [...(m.reasons || []), ...(m.legacy ? ['当前沿用旧规则；保存并上架后将使用此处的明确售价。'] : [])].join(' · ');
    renderPrices(); renderBindings(); showDialog(modelDialog);
  }
  function priceRows(m) {
    const rows = [], specs = m.specs || {};
    if (m.media_type === 'prompt' || !m.media_type) return rows;
    const resolutions = specs.resolutions?.length ? specs.resolutions : ['default'];
    if (m.media_type === 'video') {
      resolutions.forEach(resolution => {
        const perSecond = m.prices.find(p => p.resolution === resolution && p.billing_unit === 'per_second');
        const matchingBindings = m.bindings.filter(b => b.specs?.resolutions?.includes(resolution));
        const durations = [...new Set(matchingBindings.flatMap(b => b.specs.durations || []))];
        const hasDurationRange = matchingBindings.some(b => Boolean(b.specs?.duration_range));
        const unit = m.priceUnits[resolution] || (perSecond || hasDurationRange ? 'per_second' : 'per_request');
        if (unit === 'per_second' && (durations.length || hasDurationRange)) rows.push({resolution, mode: 'video', billing_unit: 'per_second', duration_seconds: 0, ...perSecond});
        else durations.forEach(duration => rows.push({resolution, mode: 'video', billing_unit: 'per_request', duration_seconds: duration, ...m.prices.find(p => p.resolution === resolution && p.billing_unit === 'per_request' && p.duration_seconds === duration)}));
      });
    } else resolutions.forEach(resolution => rows.push({resolution, mode: m.media_type === 'image' ? 'text' : m.media_type, ...m.prices.find(p => p.resolution === resolution)}));
    return rows;
  }
  function renderPrices() {
    const target = $('[data-mm-prices]'); target.replaceChildren();
    if (editing.media_type !== editing.original_media_type) {
      target.append(el('p', '类型已变更，请先保存停用配置，再重新打开设置售价。', 'mm-note'));
      $('[data-mm-fill-prices]').hidden = true;
      return;
    }
    const rows = priceRows(editing);
    if (editing.media_type === 'video') (editing.specs.resolutions || []).forEach(resolution => {
      const hasDurationRange = editing.bindings.some(b => b.specs?.resolutions?.includes(resolution) && b.specs.duration_range);
      const unit = editing.priceUnits[resolution] || (editing.prices.some(p => p.resolution === resolution && p.billing_unit === 'per_second') || hasDurationRange ? 'per_second' : 'per_request');
      if (hasDurationRange) {
        editing.priceUnits[resolution] = 'per_second';
        target.append(field(`${resolution} 计费方式`, el('span', '范围时长按秒计费', 'mm-note')));
      } else {
        const chooser = select({per_request: '按条／固定时长', per_second: '按秒'}, unit, `${resolution} 计费方式`);
        chooser.addEventListener('change', () => { editing.prices = readPrices(); editing.priceUnits[resolution] = chooser.value; renderPrices(); });
        target.append(field(`${resolution} 计费方式`, chooser));
      }
    });
    rows.forEach(p => {
      const row = el('div', undefined, 'mm-price-row'); row.dataset.price = JSON.stringify(p);
      const duration = p.billing_unit === 'per_second' ? '每秒' : p.duration_seconds ? `≤${p.duration_seconds} 秒／条` : '不限时长／条';
      const points = input('number', p.enabled === false ? '' : p.points ?? '', `${p.resolution} ${duration} 积分`); points.min = '1'; points.max = '1000000'; points.step = '1'; points.placeholder = '暂不上架';
      row.append(el('span', p.resolution === 'default' ? '标准规格' : p.resolution), el('span', duration, 'mm-note'), points); target.append(row);
    });
    if (!rows.length) target.append(el('p', editing.media_type === 'prompt' ? '在线助手不单独计费。' : '请先确认模型类型及渠道支持的规格，保存草稿后再设置售价。', 'mm-note'));
    $('[data-mm-fill-prices]').hidden = rows.length < 2;
  }
  $('[data-mm-fill-prices]').addEventListener('click', () => { const nodes = $$('[data-mm-prices] input'); const value = nodes[0]?.value; if (value) nodes.forEach(n => { n.value = value; }); });
  function renderBindings() {
    const target = $('[data-mm-bindings]'); target.replaceChildren();
    editing.bindings.forEach((b, index) => {
      const row = el('div', undefined, 'mm-binding'); row.dataset.binding = index;
      const top = el('div', undefined, 'mm-binding-top');
      const provider = catalog.connections.find(p => p.id === b.provider_id);
      const title = el('div'); summary(title, b.provider_name || provider?.name || '选择渠道', provider?.enabled ? '渠道已启用' : '渠道停用');
      const priority = input('number', b.priority ?? 100, '渠道优先级'); priority.min = '0'; priority.max = '10000'; priority.dataset.bindingPriority = '';
      const enabled = input('checkbox', '', '启用此绑定'); enabled.checked = b.enabled !== false; enabled.dataset.bindingEnabled = '';
      top.append(title, field('优先级', priority), field('启用', enabled)); row.append(top);
      const detail = el('details'); detail.append(el('summary', '调用 ID、协议、能力与成本'));
      const fields = el('div', undefined, 'mm-fields');
      const upstream = input('text', b.upstream_id || editing.id, '渠道调用 ID'); upstream.required = true; upstream.dataset.bindingUpstream = '';
      const protocol = select({'': '跟随渠道', ...protocols}, b.api_format || '', '绑定协议'); protocol.dataset.bindingProtocol = '';
      const resolutions = input('text', (b.resolutions || []).join(','), '清晰度限制'); resolutions.dataset.bindingResolutions = ''; resolutions.placeholder = '留空继承，例如 1K,2K';
      const durationRange = b.capabilities?.duration_range || {};
      const durations = input('text', (b.capabilities?.durations || []).join(','), '支持时长'); durations.dataset.bindingDurations = ''; durations.placeholder = '固定时长，例如 5,10';
      const durationMin = input('number', durationRange.min ?? '', '最短时长'); durationMin.min = '1'; durationMin.max = '3600'; durationMin.dataset.bindingDurationMin = ''; durationMin.placeholder = '范围时长';
      const durationMax = input('number', durationRange.max ?? '', '最长时长'); durationMax.min = '1'; durationMax.max = '3600'; durationMax.dataset.bindingDurationMax = ''; durationMax.placeholder = '范围时长';
      const durationStep = input('number', durationRange.step ?? 1, '时长步长'); durationStep.min = '1'; durationStep.max = '3600'; durationStep.dataset.bindingDurationStep = '';
      const ratios = input('text', (b.capabilities?.ratios || []).join(','), '支持比例'); ratios.dataset.bindingRatios = ''; ratios.placeholder = '留空继承，例如 16:9,9:16';
      const cost = input('number', b.cost_amount, '渠道成本'); cost.min = '0'; cost.step = 'any'; cost.dataset.bindingCost = ''; cost.placeholder = '未记录';
      const currency = select({CNY: '人民币 CNY', USD: '美元 USD'}, b.cost_currency || 'CNY', '成本币种'); currency.dataset.bindingCurrency = '';
      const unit = select({request: '每次', image: '每张', second: '每秒', '1000_chars': '每千字符', '1000_tokens': '每千 Token'}, b.cost_unit || 'request', '成本单位'); unit.dataset.bindingUnit = '';
      fields.append(field('渠道调用 ID', upstream), field('调用协议', protocol), field('清晰度限制', resolutions), field('渠道成本', cost), field('成本币种', currency), field('成本单位', unit)); detail.append(fields); row.append(detail);
      if (editing.media_type === 'video') fields.append(field('固定时长（秒）', durations), field('范围时长（秒）', durationMin), field('至', durationMax), field('步长（秒）', durationStep), field('支持比例', ratios));
      if (b.reasons?.length) row.append(el('p', b.reasons.join('、'), 'mm-note'));
      const verification = typeof b.verification === 'string' ? b.verification : b.verification?.generation === 'passed' ? '已验证' : '尚未验证'; row.append(el('small', verification)); target.append(row);
    });
  }
  function readBindings() {
    return $$('[data-binding]', $('[data-mm-bindings]')).map(row => {
      const b = {...editing.bindings[Number(row.dataset.binding)]};
      Object.assign(b, {upstream_id: $('[data-binding-upstream]', row).value.trim(), api_format: $('[data-binding-protocol]', row).value, enabled: $('[data-binding-enabled]', row).checked, priority: Number($('[data-binding-priority]', row).value), cost_amount: $('[data-binding-cost]', row).value, cost_currency: $('[data-binding-currency]', row).value, cost_unit: $('[data-binding-unit]', row).value});
      const resolutions = $('[data-binding-resolutions]', row).value.trim();
      if (resolutions) b.resolutions = resolutions.split(/[,，\s]+/).filter(Boolean); else delete b.resolutions;
      if (editing.media_type === 'video') {
        b.capabilities = {...b.capabilities};
        if (resolutions) b.capabilities.resolutions = b.resolutions;
        else delete b.capabilities.resolutions;
        const durations = $('[data-binding-durations]', row)?.value.trim();
        const durationMin = $('[data-binding-duration-min]', row)?.value.trim();
        const durationMax = $('[data-binding-duration-max]', row)?.value.trim();
        const durationStep = $('[data-binding-duration-step]', row)?.value.trim();
        const ratios = $('[data-binding-ratios]', row)?.value.trim();
        if (durationMin || durationMax) {
          if (!durationMin || !durationMax) throw new Error('范围时长需要同时填写最短和最长时长');
          b.capabilities.duration_range = {min: Number(durationMin), max: Number(durationMax), step: Number(durationStep || 1)};
          delete b.capabilities.durations;
        } else {
          delete b.capabilities.duration_range;
          if (durations) b.capabilities.durations = durations.split(/[,，\s]+/).map(Number);
          else delete b.capabilities.durations;
        }
        if (ratios) b.capabilities.ratios = ratios.split(/[,，\s]+/).filter(Boolean);
      }
      return b;
    });
  }
  $('[data-mm-add-binding]').addEventListener('click', () => {
    if ($('[data-mm-binding-chooser]')) return;
    const available = catalog.connections.filter(p => !editing.bindings.some(b => b.provider_id === p.id));
    if (!available.length) { dialogFeedback(modelDialog, '所有渠道均已关联此模型。'); return; }
    editing.bindings = readBindings();
    const target = $('[data-mm-bindings]');
    const chooser = select(Object.fromEntries(available.map(p => [p.id, p.name])), available[0].id, '选择新增绑定渠道');
    const add = button('确认关联', () => { const p = available.find(p => p.id === Number(chooser.value)); editing.bindings.push({provider_id: p.id, provider_revision: p.revision, provider_name: p.name, upstream_id: editing.id, api_format: '', enabled: true, priority: p.priority}); renderBindings(); });
    const controls = el('div', undefined, 'mm-inline-actions'); controls.dataset.mmBindingChooser = ''; controls.append(chooser, add, button('取消', () => controls.remove())); target.append(controls);
  });
  modelForm.elements.media_type.addEventListener('change', () => { editing.bindings = readBindings(); editing.media_type = modelForm.elements.media_type.value; renderPrices(); renderBindings(); dialogFeedback(modelDialog, '类型变更请先保存停用配置，重新打开后配置规格与价格。'); });
  function readPrices() { return $$('[data-price]', $('[data-mm-prices]')).map(row => ({...JSON.parse(row.dataset.price), points: Number($('input', row).value), enabled: Boolean($('input', row).value)})).filter(p => p.enabled); }
  modelForm.addEventListener('submit', event => {
    event.preventDefault(); const publication = event.submitter?.value || 'draft';
    busy(modelForm, async () => {
      if (publication === 'active' && editing.media_type !== editing.original_media_type) throw new Error('类型变更请先保存停用配置，再配置售价并上架。');
      const prices = readPrices();
      const data = {id: editing.id, media_type: modelForm.elements.media_type.value, original_media_type: catalog.models.find(m => m.id === editing.id && m.revision === editing.revision)?.media_type || '', revision: editing.revision, label: modelForm.elements.label.value.trim(), publish: publication === 'active', bindings: readBindings()};
      if (data.media_type === editing.original_media_type && $('[data-mm-prices] [data-price]')) data.prices = prices;
      await request('/models/save', data); dirty = true;
      await refresh(publication === 'active' ? '模型配置与售价已保存。' : '模型配置已保存，当前停用。'); modelDialog.close();
    });
  });

  const previewDialog = $('#mm-preview'), previewForm = $('[data-mm-preview-form]');
  function openPreview(m) {
    const modelSelect = previewForm.elements.model; modelSelect.replaceChildren();
    catalog.models.filter(m => m.media_type).forEach(m => { const option = el('option', `${m.label} · ${kindNames[m.media_type]}`); option.value = modelKey(m); modelSelect.append(option); });
    if (m?.media_type) modelSelect.value = modelKey(m);
    updatePreviewSpecs(); $('[data-mm-preview-result]').replaceChildren(); showDialog(previewDialog);
  }
  $$('[data-mm-preview]').forEach(b => b.addEventListener('click', () => openPreview()));
  function updatePreviewSpecs() {
    const m = catalog.models.find(m => modelKey(m) === previewForm.elements.model.value);
    const set = (selectNode, values) => { selectNode.replaceChildren(); values.forEach(v => { const o = el('option', v); o.value = v; selectNode.append(o); }); };
    const prices = (m?.prices || []).filter(p => p.enabled);
    const resolutions = m?.specs?.resolutions?.length ? m.specs.resolutions : [...new Set(prices.map(p => p.resolution))];
    set(previewForm.elements.resolution, resolutions.length ? resolutions : [m?.media_type === 'video' ? '720p' : 'default']);
    set(previewForm.elements.ratio, m?.specs?.ratios?.length ? m.specs.ratios : ['16:9']);
    updatePreviewDuration();
    $('[data-mm-ratio-field]').hidden = m?.media_type !== 'video';
    $('[data-mm-duration-field]').hidden = m?.media_type !== 'video'; previewForm.elements.count.max = m?.media_type === 'image' ? '4' : '1'; previewForm.elements.count.value = '1';
  }
  function updatePreviewDuration() {
    const m = catalog.models.find(m => modelKey(m) === previewForm.elements.model.value), resolution = previewForm.elements.resolution.value;
    let durations = [...new Set((m?.bindings || []).flatMap(b => b.specs?.resolutions?.includes(resolution) ? b.specs.durations || [] : []))];
    if (!durations.length) durations = [...new Set((m?.prices || []).filter(p => p.enabled && p.resolution === resolution && p.duration_seconds > 0).map(p => p.duration_seconds))];
    if (!durations.length) durations = [m?.media_type === 'video' ? 6 : 0];
    const target = previewForm.elements.duration_seconds; target.replaceChildren();
    durations.forEach(v => { const o = el('option', v); o.value = v; target.append(o); });
  }
  previewForm.elements.model.addEventListener('change', updatePreviewSpecs);
  previewForm.elements.resolution.addEventListener('change', updatePreviewDuration);
  previewForm.addEventListener('submit', event => {
    event.preventDefault(); busy(previewForm, async () => {
      const m = catalog.models.find(m => modelKey(m) === previewForm.elements.model.value); if (!m) throw new Error('请先添加模型。');
      const data = await request('/preview', {media_type: m.media_type, model: m.id, resolution: previewForm.elements.resolution.value, ratio: previewForm.elements.ratio.value, duration_seconds: Number(previewForm.elements.duration_seconds.value), count: Number(previewForm.elements.count.value)});
      const target = $('[data-mm-preview-result]'); target.replaceChildren();
      target.append(el('p', data.selected ? `首选渠道：${data.selected.name} · 调用 ${data.selected.upstream_id}` : '当前没有可用渠道。'));
      if (data.quote) target.append(el('p', `预计 ${data.quote.points} 积分`));
      (data.reasons || []).forEach(reason => target.append(el('p', reason, 'mm-note')));
      (data.candidates || []).forEach(c => { const row = el('div', undefined, 'mm-preview-row'); row.append(el('strong', c.name), el('div', c.eligible ? `可用 · 优先级 ${c.priority}` : (c.reasons || []).join('、'))); target.append(row); });
    });
  });

  async function loadCalls() {
    const body = $('[data-mm-calls]');
    try {
      const state = $('[data-mm-call-state]').value;
      const data = await request(`/calls?page=${page}${state ? `&status=${encodeURIComponent(state)}` : ''}`); calls = data.calls || []; body.replaceChildren();
      calls.forEach(call => {
        const row = el('tr'), cells = Array.from({length: 6}, () => el('td'));
        summary(cells[0], call.created_at, `#${call.id}`); summary(cells[1], call.model || '未记录', kindNames[call.media_type] || call.media_type);
        cells[2].textContent = call.route?.provider_name || call.provider_name || '未记录'; cells[3].append(status(call.status));
        if (call.timing?.upstream_ms != null) cells[3].append(el('small', `${(call.timing.upstream_ms / 1000).toFixed(1)} 秒`));
        cells[4].textContent = `${call.cost ?? '—'}`; cells[5].append(button('查看', () => showCall(call))); row.append(...cells); body.append(row);
      });
      if (!calls.length) empty(body, 6, '暂无符合条件的调用记录。');
      $('[data-mm-page]').textContent = `第 ${page} 页 · 共 ${data.total} 条`;
      $('[data-mm-prev]').disabled = page <= 1; $('[data-mm-next]').disabled = page * data.page_size >= data.total;
    } catch (error) { empty(body, 6, error.message); }
  }
  function showCall(call) {
    const target = $('[data-mm-call-detail]'); target.replaceChildren(); const list = el('dl', undefined, 'mm-detail-list');
    const fields = {'任务': `#${call.id}`, '平台模型': call.model, '媒体类型': kindNames[call.media_type], '实际渠道': call.route?.provider_name || call.provider_name, '调用 ID': call.route?.upstream_id || call.route?.upstream_model, '协议': call.route?.api_format, '状态': stateNames[call.status], '规格': `${call.resolution || ''} ${call.ratio || ''} ${call.duration_seconds ? call.duration_seconds + ' 秒' : ''}`, '报价积分': call.cost, '上游任务': call.provider_task_id, '创建时间': call.created_at, '完成时间': call.finished_at, '错误': call.error_message, '保存阶段': call.storage_status};
    fields['费用结算'] = call.billing_message;
    Object.entries(fields).forEach(([key, value]) => { list.append(el('dt', key), el('dd', value === 0 ? '0' : value || '未记录')); }); target.append(list); $('#mm-call-detail').showModal();
  }
  $('[data-mm-refresh-calls]').addEventListener('click', loadCalls); $('[data-mm-call-state]').addEventListener('change', () => { page = 1; loadCalls(); });
  $('[data-mm-prev]').addEventListener('click', () => { if (page > 1) { page--; loadCalls(); } }); $('[data-mm-next]').addEventListener('click', () => { page++; loadCalls(); });
    refresh().then(() => {
      if (window.location.hash === '#models') chooseTab('models');
      const url = new URL(window.location.href), pid = Number(url.searchParams.get('test_provider'));
      if (pid) { const p = catalog.connections.find(p => p.id === pid); if (p) testConnection(p); url.searchParams.delete('test_provider'); window.history.replaceState(null, '', url); }
    }).catch(error => feedback($('[data-mm-feedback]', root), error.message, true));
})();
