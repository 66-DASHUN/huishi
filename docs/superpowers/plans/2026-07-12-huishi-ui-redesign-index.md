# 绘世全站 UI 优化实施总计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement these plans task-by-task. Subagents are not authorized unless the user explicitly requests them. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有业务结构的前提下，将 Flask 主站、Next.js 画布与后台管理统一为已确认的瓷白/曜黑 UI 系统。

**Architecture:** 四个独立计划按顺序交付。第一阶段建立主题与首页基础；第二阶段覆盖 Flask 用户端；第三阶段同步 Next.js 画布；第四阶段优化后台并提供统一业务流水 DTO。每个阶段都可独立回归。

**Tech Stack:** Flask/Jinja2、React 18、Tailwind 3、原生 CSS/JS、Next.js 16、React 19、Ant Design 6、Tailwind 4、Zustand、SQLite/PostgreSQL。

---

## 执行约束

- Huishi 命令必须通过 `ssh huishi-vm "cd /opt/huishi && <具体命令>"` 执行。
- 不自动提交、推送或创建 PR。
- 不回滚用户已有改动。
- 画布子项目遵守 `infinite-canvas/AGENTS.md`：Codex 不运行 `bun test`、`bun run typecheck` 或 `bun run build`，只记录用户验证命令。
- 每阶段修改前读取相关文件和当前状态；修改后做源码检查、允许的 Flask 测试和浏览器验证。
- 设计规范：`docs/superpowers/specs/2026-07-12-huishi-ui-redesign-design.md`。

## 子计划顺序

- [ ] **Phase 1:** `docs/superpowers/plans/2026-07-12-huishi-ui-foundations-home.md`
- [ ] **Phase 2:** `docs/superpowers/plans/2026-07-12-huishi-flask-user-ui.md`
- [ ] **Phase 3:** `docs/superpowers/plans/2026-07-12-huishi-canvas-ui.md`
- [ ] **Phase 4:** `docs/superpowers/plans/2026-07-12-huishi-admin-ledger-ui.md`

## 跨阶段验收

- [ ] 主站和画布使用相同语义主题值：`system | light | dark`。
- [ ] 首页继续使用 `static/media/shouyeshipin-home.mp4`，不添加全局暗色遮罩。
- [ ] 工作台保留窄工具栏、对话历史、结果流和固定输入区。
- [ ] 提示词页仍为 iframe 边界。
- [ ] 无限画布、生图和视频页面不改变栏位或工具结构。
- [ ] 账户、API Key、价格页不添加工作台左栏。
- [ ] 管理端侧栏与内容区统一跟随主题。
- [ ] “业务流水”合并展示，不迁移或合并底层表。
- [ ] 缺图、超长文本、空白、加载、失败、退款和权限状态均有设计。
- [ ] 无非预期页面级横向溢出；表格只在自身容器横向滚动。

## 最终验证

```powershell
ssh huishi-vm "cd /opt/huishi && npm run verify:home"
ssh huishi-vm "cd /opt/huishi && npm test"
```

预期：允许执行的主站测试全部通过。画布验证命令交给用户：

```bash
cd /opt/huishi/infinite-canvas/web
bun test
bun run typecheck
bun run build
```

浏览器检查尺寸：`1440x900`、`1280x720`、`768x1024`、`390x844`、`320x568`。
