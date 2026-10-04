# 绘世性能与安全审计

更新时间：2026-07-09

## 结论

本轮已修复 P0/P1 中可以低风险直接落地的项：登录 CSRF、首页 meta description、生成图保存压缩、图片 lazy/async decoding、按保留天数治理的存储清理与可配置单次删除上限、在途文件最小年龄保护、Claude MCP bridge 默认超时配置，并补强了 PostgreSQL 生成任务预占检查的行锁。首页也已移除浏览器端 Babel 和 Tailwind CDN，改为本地构建产物，并压缩首屏背景视频。

首页 Lighthouse 最新结果：

| 项目 | 分数 |
| --- | --- |
| Performance | 0.71 |
| Accessibility | 1.00 |
| Best Practices | 1.00 |
| SEO | 1.00 |

性能已从本轮中段的 `0.28` 提升到 `0.71`；主线程阻塞降到 `0ms`，总传输量降到约 `3.3MB`。仍可继续优化的瓶颈是首屏 LCP 约 `4.4s`、外部 React/Framer Motion 脚本和跨域字体。

## 已修复

| 优先级 | 问题 | 处理 |
| --- | --- | --- |
| P0 | `/login` 被 CSRF 豁免 | 移除登录/注册/找回密码/邮箱验证 POST 的 CSRF 豁免，首页 auth fetch 发送 `X-CSRF-Token`，相关表单补 hidden token |
| P0 | 存储清理策略需要按日期治理，而不是按固定批次治理 | 保留天数由 `HUISHI_STORAGE_ORPHAN_RETENTION_DAYS` / `HUISHI_STORAGE_HIDDEN_RETENTION_DAYS` 决定；`HUISHI_STORAGE_SWEEP_MAX_DELETE_FILES` 仅作为单次任务安全上限，默认 `20000`，`0` 表示不限；`HUISHI_STORAGE_SWEEP_MIN_AGE_SECONDS` 默认 `300`，保护刚生成但尚未写入记录的在途文件；CLI 输出 `delete_limit_reached`、`remaining_deletable_files` 和 `min_age_seconds` |
| P0 | PostgreSQL 下生成任务预占检查缺少用户行锁 | 在创建 queued task 的事务内、二次积分/任务槽检查前执行 `SELECT ... FOR UPDATE`，并补锁顺序和 PG SQL 测试 |
| P1 | 生成图未压缩 | 新增 Pillow 优化路径，PNG/JPEG/WebP 保存前压缩；失败时安全回退原始 bytes |
| P1 | 图片未统一 lazy/async decoding | 主站模板和画布前端原生 `<img>` 补 `loading="lazy"`、`decoding="async"` |
| P1 | 缺少 meta description | `base.html` 增加默认 description，首页覆盖产品描述 |
| P1 | Claude bridge 默认超时不是 30 分钟 | bridge 源码、README、项目 `.codex/config.toml` 改为 `1800000ms`；新增 async plan/review/PR job 工具，避免长 review 被单次 `tools/call` 300 秒外层限制中断 |
| P1 | 首页浏览器端 Babel / Tailwind CDN 运行成本高 | 新增 `npm run build:home`，用 esbuild 预编译 `home.js`，用 Tailwind CLI 生成 `home-tailwind.css`，模板加载本地产物 |
| P1 | 首页视频负载过大 | 生成 `shouyeshipin-home.mp4`（约 2.9MB，无音轨）和 `shouyeshipin-poster.jpg`（约 53KB），视频使用 poster 与延迟/视口加载 |
| P2 | 首页 React key warning | 首页卡片补稳定 key；Lighthouse console error 清零 |

## 仍需优化

| 优先级 | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| P1 | 首页仍依赖外部 React / Framer Motion UMD | 跨域脚本仍影响稳定性和缓存控制 | 后续把首页 React/Motion 一并纳入本地 bundle，或用 CSS 动画替代 Motion |
| P1 | 第三方字体过多且跨域 | 阻塞首屏，稳定性差 | 自托管关键字体或减少字体族/字重 |
| P1 | 首页仍加载全站 `site.css` | 约 240KB CSS，不全是首页需要 | 拆分首页关键 CSS，减少未使用样式 |
| P1 | 上传/生成文件仍是本地磁盘模型 | 单机可用，多机和 CDN 能力弱 | 后续接对象存储 + CDN，数据库只保存对象 key 和变体信息 |
| P2 | `.env` 仍在 git 追踪范围内 | 密钥误提交风险 | 单独做密钥治理：移除追踪、轮换、本地模板化 |

## 六维检查

| 维度 | 当前状态 | 缺口 |
| --- | --- | --- |
| 目标 | 核心目标是让用户快速生成、保存、复用视觉资产；首页首屏已轻量化 | 后续还可补更明确的真实案例入口 |
| 体验 | 设置、资产、画布流程已有基础闭环；首页去掉运行时编译和过大视频 | 慢网下外部字体/React/Framer 仍可能波动 |
| 内容 | 首页已有价值表达和创作流程 | 需要更明确展示实际案例、价格入口和使用边界 |
| 转化 | 登录/注册入口存在，CSRF 已补；首页 LCP 和 TTI 已明显下降 | 可继续强化价格入口、案例入口和首屏 CTA 对比 |
| 性能 | SEO/无障碍/最佳实践已达标；Performance 提升到 `0.71`，TBT 为 `0ms` | 继续优化 LCP、外部脚本和字体 |
| 数据 | PostgreSQL/Redis/RQ、生成任务预占行锁、存储清理策略和在途文件保护已建立 | 需要对象存储、备份保留策略、清理审计日志和容量告警 |

## 验证记录

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_auth_csrf.py tests/test_seo_metadata.py tests/test_image_optimization.py tests/test_storage_sweeper.py tests/test_db_helpers.py::test_lock_user_for_update_uses_postgres_row_lock tests/test_workspace_generation_flow.py::test_generate_locks_user_before_reserving_generation_task tests/test_workspace_generation_flow.py::test_generate_locks_user_before_transactional_reservation_checks tests/test_workspace_generation_flow.py::test_generate_marks_task_failed_when_enqueue_fails_after_commit tests/test_generation_queue_backend.py`：28 passed
- `.\.venv\Scripts\python.exe -m py_compile app.py huishi\storage.py huishi\config.py huishi\image_api.py huishi\db.py huishi\routes_workspace.py huishi\generation_queue.py`：通过
- `cd tools\claude-mcp; npm run build`：通过
- `npm run build:home`：通过
- `cd infinite-canvas\web; bun run typecheck`：通过
- `cd infinite-canvas\web; bun run build`：通过
- Lighthouse 当前代码：`http://127.0.0.1:8124/`
  - Performance `0.71`
  - Accessibility `1.00`
  - Best Practices `1.00`
  - SEO `1.00`
  - Console errors `0`
  - Total byte weight: about `3.3MB`
  - Total blocking time: `0ms`
- Claude review：无 BLOCKER；提出的 PG 行锁测试证据和 storage 在途文件保护已补齐

## 2026-07-11 production-readiness evidence

- Homepage assets: `home.compiled.js` 169,743 bytes, `home-tailwind.css` 15,329 bytes, active video 2,882,054 bytes. All enforced budgets pass.
- Canvas heavy surfaces (`CanvasAssistantPanel`, `AssetPickerModal`, and `PromptSelectDialog`) use named dynamic imports and mount only while open.
- Canvas Agent lifecycle and asset-to-node conversion are covered by pure reducer/conversion tests.
- Canvas bundle report command: `bun run report:bundle --json`.
- Production canvas baseline: 43 JavaScript chunks, 2,738,835 bytes total JavaScript, largest chunk 499,096 bytes.
- Staged canvas build: 52 JavaScript chunks, 2,735,289 bytes total JavaScript, largest chunk 287,724 bytes. The heavy surface split reduces the largest chunk by 211,372 bytes (42.4%).
- Frontend gate: 20 tests passed; TypeScript, Prettier, and Next.js production build passed.
- Backend gate: 304 tests passed and 41 skipped in the isolated SQLite test environment.
- The unreferenced legacy `static/media/shouyeshipin.mp4` remains present pending explicit deletion approval. It is not loaded by the homepage.

## 2026-07-12 final production evidence

- Canvas release `20260711T164405Z`, build `jAeO8_75Ux8h-Ma5R16-h`; homepage implementation release `20260711T171949Z`. Later audit-only releases used the same backed-up backend release workflow.
- Production canvas gate: 24 tests passed; `bun run typecheck`, `bun run format:check`, and the staged Next.js production build passed. Production typecheck no longer writes root-owned incremental metadata, and Prettier ignores retained `.next.previous-*` builds.
- Production backend gate: 290 tests passed and 41 skipped with `python -m pytest -q -p no:cacheprovider`.
- Canvas bundle: 52 JavaScript chunks, 2,735,289 JavaScript bytes, 93,133 CSS bytes, and a 287,724-byte largest chunk.
- Cached iframe reload regression fixed: the host loading overlay now clears even when the embedded canvas loads before the bottom script registers its listener.
- Responsive production browser checks passed at 1440, 1280, 768, and 390 CSS pixels with no horizontal overflow. Mobile navigation, canvas actions, and empty-state copy fit without overlap.
- Lighthouse mobile performance using the same production URL/config improved from score 69, LCP 4,620 ms, and 5,053,676 transferred bytes to score 93, LCP 2,723 ms, and 3,192,883 transferred bytes.
- The second-screen capabilities video now requires 15% viewport visibility, so it is absent from the initial Lighthouse network payload. Homepage fonts use one non-render-blocking stylesheet instead of three blocking/duplicate requests.
- All eight runtime services were active, no failed systemd units were reported, and the main/canvas HTTPS smoke checks returned HTTP 200.
- The backup timer is enabled and active. A fresh `huishi-20260711T172434Z.dump` completed with `Result=success`, and every PostgreSQL/code backup checksum present on the VM verified as `OK`.
- The latest PostgreSQL dump restored into the isolated `huishi_restore_rehearsal` database. `tools/db_smoke.py` passed all schema, transaction, provider/canvas, generation, storage-reference, and cascade checks with the production encryption key supplied ephemerally; the rehearsal database and temporary files were removed afterward.
- The complete isolated PostgreSQL profile passed `313` tests with `41` intentional skips. The schema was reset before every test, the configured database name was safety-checked, and the temporary database was dropped after the run.
