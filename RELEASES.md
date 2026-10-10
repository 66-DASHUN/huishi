# 绘世（Huishi）发布索引

本文件是**发布版本清单**——记录每个 release 的用途、状态与回滚目标。
发布机制详见 `DEPLOY.md`。

> **为什么需要这份清单**：发布产物本身不入库（`.gitignore` 忽略
> `releases/`），历史版本的"哪个版本在跑、回滚到哪个 tag"此前只能靠
> `docker image ls` 的创建时间和目录 mtime 反推。本清单把它固化下来。

## 当前状态（2026-10-10）

| 服务 | 运行镜像 |
|---|---|
| `backend` | `huishi-backend:billing-hardening-20261010` |
| `worker` | `huishi-backend:billing-hardening-20261010`（4 副本，与 backend 共用镜像，仅 command 不同） |
| `canvas` | `huishi-canvas:canvas-subpath-20261010` |
| `canvas-agent` | `huishi-canvas-agent:latest` |
| `postgres` | `postgres:16-alpine` |
| `redis` | `redis:7-alpine` |

**当前回滚目标**：`huishi-backend:rollback-billing-hardening-20261010`

**画布回滚目标**：`huishi-canvas:rollback-canvas-subpath-20261010`（⚠️ 见下：回滚画布镜像需同时回退 nginx）

## 版本类型约定

清单里每个 release 标注 `kind`：

| kind | 含义 | 目录完备度要求 |
|---|---|---|
| `正式` | 面向生产的功能/修复发布 | 必须自包含：`Dockerfile.*` + `compose.release.yml` + `compose.rollback.yml` + `prepare.sh` + `deploy.sh` + `payload/` |
| `测试` | 灰度/预演，通过隔离库验证后再转正式 | 额外含 `smoke.sh` 或 `rehearse` 脚本 |
| `回退` | 仅回滚用，不用于前进 | 至少含 `compose.rollback.yml` |

**命名约定**：`kebab-case-描述-YYYYMMDD[-HHMM]`。同一发布若含多个服务，
用统一的日期后缀（例：`token-fragment-20261005`）。

## Release 清单

按时间倒序。`文件数` 指 release 目录内的条目数——**数字越小说明目录越不完整**。

| release | 日期 | 文件数 | 目标镜像 | kind | 状态 | 备注 |
|---|---|---|---|---|---|---|
| `billing-hardening-20261010` | 2026-10-10 | 10 | `huishi-backend:billing-hardening-20261010` | 正式 | **在跑** | 针对「提交后没收到结果却产生扣费」的三条独立成因，外加并发与规模问题。**①顺序颠倒（主因）**：`_finalize_generation`（建记录+扣费）跑在取图之前，而 `_canvas_record_data_url` 在文件缺失时**静默返回空串**被跳过，于是返回 `{ok:true, images:[], balance:已扣}`，而画布前端 `host-image.ts:143` 对空 images 抛「主站生图代理失败」——用户看到失败、积分已扣。生产实测该路径**尚未触发**（17 条扣费记录文件全部存在），属潜在缺陷，不能当作已发生故障。改为**先读图、读不到就整单失败**（500，不扣费不建记录）。**②无锁预检 + 长期同步上游**：画布是唯一没有 `immediate_transaction + lock_user_for_update` 的写路径（工作台/音频/视频都有），并发请求会一起穿过预检、上游成本已发生而扣费可能回滚失败，差额由管理员 Key 承担。改为持锁后再校验并扣费。**③缺并发额度**：画布此前完全不调 `require_active_generation_task_slot`，现补两处（上游前廉价预检 + 锁内权威校验）。另补 4 个索引（`records`/`generation_tasks`/`point_ledger` 的 user_id 索引数此前为 **0**，而余额预留、作品列表、流水全部按 user_id 过滤；生产实测索引 37→41，`EXPLAIN` 已从 Seq Scan 变 Bitmap Index Scan），并修后台首页无 LIMIT 拉全表 `records`+`point_ledger` 只为显示 8 行的问题（新增 `limit` 取数上限）。**验证**：全量 840 passed（改动前 0 failed；注意 `HUISHI_OUTPUT_DIR` 未设时 `/app/static/uploads` 不可写会误报 203 errors）；**真实 Postgres 并发探针**：100 分/单次 30/并发 6 → 修复后 3 成功 3 拒绝、余额 10；反向对照（去锁去事务）6 全部成功、余额仍 100、流水 0，即缺陷复现。⚠️ 回滚：`huishi-backend:rollback-billing-hardening-20261010` |
| `canvas-subpath-backend-20261010` | 2026-10-10 | 8 | `huishi-backend:canvas-subpath-backend-20261010` | 正式 | **在跑** | 画布改挂主站同域子路径的后端侧：①首页「画布」卡片改指 `/canvas`，不再整页跳到画布应用地址（那会把用户带离绘世，观感像外挂），随之删除 `__HUISHI_CANVAS_URL__` 注入与 `auth.py`/`app.py` 里为它传值的死代码；②**同源后浏览器不再发 `Origin` 头**，而 `is_allowed_canvas_origin` 原先把缺失 Origin 一律判为不可信，实测线上所有画布数据操作 403（`untrusted_origin`）。改为空 Origin 时要求请求目标主机与画布同源一致——跨站伪造仍被拦，跨源 Origin 校验路径不受影响 |
| `canvas-subpath-20261010` | 2026-10-10 | 3 | `huishi-canvas:canvas-subpath-20261010` | 正式 | **在跑**(canvas) | 画布镜像按 `basePath=/canvas-app` 重建。Next 只自动给 `_next/*` 与 `<Link>`/router 导航加前缀，手写路径不会（读 Next 源码 `addBasePath` 调用点确认），因此逐个修正 `router.push/replace`、`fetch`、原生 `<img src>` 共 11 处，并修 `app-top-nav` 按路径判断的 `hideHeader`（加前缀后正则失配会错误显示画布顶栏）。⚠️ **回滚需同时回退 nginx**：旧镜像服务根路径、不能走子路径；本次改动前的配置在 `/root/paintiworld.conf.bak-20261010`。同时移除了 8443 的 server 块（全站已无引用，且该端口返回 404） |
| `canvas-perf-20261008` | 2026-10-08 | 3 | `huishi-canvas:canvas-perf-20261008` | 正式 | 已被取代 | 画布镜像重建，落地移除 pro-components 的改动。⚠️ **目录不完整**：只有两个 compose + manifest，无 Dockerfile/脚本——画布不走上层分层的后端发布路径，而是由 `compose.prod.yml` 的 `context: infinite-canvas` + `Dockerfile.huishi` 就地构建，故沿用 `token-fragment-20261005` 的形态。回滚 tag 为 `huishi-canvas:rollback-canvas-perf-20261008`。附带的锁文件修正还清掉了只被 pro-components 依赖的 270 行孤立条目（@dnd-kit/*、rc-field-form、lodash-es 等） |
| `font-mime-20261008` | 2026-10-08 | 8 | `huishi-backend:font-mime-20261008` | 正式 | 已被取代 | 给 .woff2/.woff 注册正确的 Content-Type。python:3.12-slim 里没有 /etc/mime.types，mimetypes 不认识 woff2，Flask 把字体当 `application/octet-stream` 送出——这是随「字体搬到站内」一起进来的，此前字体由 Cloudflare 边缘提供、类型天然正确。风险边界如实说：主流浏览器不会因此拒绝加载（nosniff 的 MIME 强制针对脚本与样式表），所以不是线上故障，而是响应头说了谎。测试用**子进程**验证，因为 `mimetypes.add_type` 改的是模块级全局表，在测试进程里调一次就永久生效——我最初那版测试去掉修复后依然全绿，等于没测；改为子进程并做过反证后才可信 |
| `fonts-canvas-perf-20261008` | 2026-10-08 | 8 | `huishi-backend:fonts-canvas-perf-20261008` | 正式 | 已被取代 | 字体自托管，消掉 Cloudflare 往每个 HTML 里内联的 46 万字节。实测注入是 505 条 @font-face、461,774 字节（raw），`/workspace` 因此从 464,938 掉到 **3,214 字节**，每次导航的传输量从 36,475 降到 **1,387**（br）。做法：202 个 woff2 子集放 `static/fonts/`，权重写成范围形式（这批是可变字体，一个文件覆盖整条 wght 轴，写成单值会静默退回单字重），保留 unicode-range 让浏览器只下命中的 3-8 片。另含画布移除仅为 `dark` 一个布尔引入的 pro-components（首屏 gzip −31,258，−5.9%）。**注意**：字体进 git 共 10,531,532 字节 |
| `mention-preamble-20261008` | 2026-10-08 | 8 | `huishi-backend:mention-preamble-20261008` | 正式 | 已被取代 | 图片模式的 @ 引用**真正生效**：此前 `@文件名` 只是原样送上游的一段纯文本，上游既不知道它指向第几张图、也没有位置对应关系，等于装饰。现在在唯一的出图咽喉点（队列/工作台/作品重生成/测试连接四条路径共用）插入编号前言：「参考图片共 N 张，按提交顺序编号 …… 第1张=产品主图.png」，顺带把 `secure_filename` 吃掉中文名（`天鹤司命分镜42.png`→`42.png`）导致按名反查位置不可靠的问题一并绕开——编号依据是**真实提交顺序**而非 @ 的出现顺序。已用补丁 OpenAI 客户端的方式抓到真实上游 kwargs，确认前言随请求发出 |
| `image-mode-mention-20261008` | 2026-10-08 | 8 | `huishi-backend:image-mode-mention-20261008` | 正式 | 已被取代 | 图片模式也支持 @ 引用参考图：此前 @ 只在视频模式可用（函数开头就按媒体类型早退），而参考图恰是图片模式最常用的输入。改动含候选入口与媒体解耦、锚点按模式回落、点击不误写视频状态、措辞分模式、切换类型重新同步。附 `tests/check_workspace_mention.cjs`（node，8 组）用 DOM 桩执行真实分支 |
| `subject-create-row-20261008` | 2026-10-08 | 8 | `huishi-backend:subject-create-row-20261008` | 正式 | 已被取代 | 用户页 UI：①「创建主体」改为常驻行，此前它藏在空状态里、一旦有主体就被隐藏，想再加一个时入口反而消失；②拖拽参考素材同时携带友好名（结果图用提示词、素材卡用显示名），修掉界面出现 `huishi_xxx.png` / `canvas_xxx.png` 这类存储名的问题 |
| `entry-priority-20261007` | 2026-10-07 | 8 | `huishi-backend:entry-priority-20261007` | 正式 | 已被取代 | 模型条目的优先级真正生效：`priority` 此前不在字段白名单里，保存后**任何一次读取都会丢弃**，导致「模型可单独设置优先级」完全空转。补齐白名单 + 候选按（条目优先、缺失回落渠道）排序。现有条目值均为 100 与渠道级相同，故行为不变、零迁移 |
| `runtime-groups-20261007` | 2026-10-07 | 8 | `huishi-backend:runtime-groups-20261007` | 正式 | 已被取代 | 运行配置按分组折叠（需求 ③）：组标题行做成开关，默认收起；深链自动展开、窄屏不失效、脚本失败时内容仍可见 |
| `log-handler-20261007` | 2026-10-07 | 8 | `huishi-backend:log-handler-20261007` | 正式 | 已被取代 | 日志 handler 不再随 create_app 堆积（消除日志重复与文件流泄漏）；兜底失败留下可诊断的异常类型 |
| `unify-wording-20261007` | 2026-10-07 | 8 | `huishi-backend:unify-wording-20261007` | 正式 | 已被取代 | 统一三个视频适配器「不支持此模型」的措辞并带上模型名（需求 ②） |
| `format-marker-20261007` | 2026-10-07 | 8 | `huishi-backend:format-marker-20261007` | 正式 | 已被取代 | 参考目录降级不再依赖错误文案（需求 ②）：改用异常标记判断，消除「改一句提示语就静默断开降级」的隐患 |
| `unify-adapter-http-20261007` | 2026-10-07 | 8 | `huishi-backend:unify-adapter-http-20261007` | 正式 | 已被取代 | jiasuapi 复用统一 HTTP 层（需求 ②）：删除自建的 `_url`/`_headers`/`_request`，补上此前缺失的 `allow_redirects=False`，错误文案统一为 `HTTP <code>: <message>` |
| `paused-tasks-20261007` | 2026-10-07 | 8 | `huishi-backend:paused-tasks-20261007` | 正式 | 已被取代 | 待核对视频任务在运行总览可见（需求 ⑥）：新增健康探针 + 首页链接直达待核对表格；抽出共用查询消除首页与列表的数字漂移 |
| `reference-hint-20261007` | 2026-10-07 | 8 | `huishi-backend:reference-hint-20261007` | 正式 | 已被取代 | 参考素材提示接入真实能力数据（需求 ④）：接活死元素 `data-video-hint`、消除测试面板硬编码的 H3 规格、按能力隐藏永不点亮的参考类型按钮 |
| `capability-balance-20261007` | 2026-10-07 | 9 | `huishi-backend:capability-balance-20261007` | 正式 | 已被取代 | 余额按需查询接线 + 三处能力声明缺陷修复 + pg_dump 可读错误/脱敏 + systemd 遗留清理。**首个三者齐全的 release**（Dockerfile×2 + prepare/deploy + manifest.sha256 + payload） |
| `channel-health-20261006` | 2026-10-06 | 7 | `huishi-backend:channel-health-20261006` | 正式 | 已被取代 | 渠道健康度 + 队列生图修复 + gemini 回退。含 Dockerfile×2、prepare/deploy、payload |
| `payloads-20261005` | 2026-10-05 | 2 | `huishi-backend:payloads-20261005` | 正式 | 已被取代 | ⚠️ **目录不完整**：只有两个 compose，无 Dockerfile/脚本 |
| `sanitize-secrets-20261005` | 2026-10-05 | 2 | `huishi-backend:sanitize-secrets-20261005` | 正式 | 已被取代 | ⚠️ 同上 |
| `extract-image-sizes-20261005` | 2026-10-05 | 2 | `huishi-backend:extract-image-sizes-20261005` | 正式 | 已被取代 | ⚠️ 同上 |
| `token-fragment-20261005` | 2026-10-05 | 2 | `huishi-backend/worker/canvas:token-fragment-20261005` | 正式 | 已被取代 | ⚠️ 同上 |
| `canvas-token-fragment-20261005` | 2026-10-05 | 2 | `huishi-canvas:token-fragment-20261005` | 正式 | 与上条重复 | ⚠️ 同一批发布拆成了两个目录 |
| `subject-reference-20261004` | 2026-10-04 | 7 | `huishi-worker:subject-reference-20261004` | 正式 | 已被取代 | 含 Dockerfile.worker、prepare/deploy、payload |
| `video-pricing-fix-20261002` | 2026-10-02 | 9 | `huishi-backend/worker:video-pricing-fix-20261002` | 正式 | 已被取代 | ✅ **脚本与 Dockerfile 最齐全**，可作模板（含 payload-worker、tests）；**缺 manifest** |
| `duration-range-20260923-1916` | 2026-09-23 | 12 | `huishi-backend/worker/canvas:duration-range-20260923-1916` | 正式 | 已被取代 | 文件数最多，含 `manifest.sha256`/`smoke.sh`/`verify_*.py`，但**缺 prepare.sh 与 deploy.sh** |
| `task-status-20260923-050336` | 2026-09-23 | 5 | `huishi-backend:task-status-20260923-050336` | 正式 | 已被取代 | ⚠️ compose 里的 worker 指向 `huishi-worker:asset-upload-20260923-013600`（与自身名字不符） |
| `task-status-20260923-045510` | 2026-09-23 | 5 | `huishi-backend:task-status-20260923-045510` | 正式 | 已被取代 | ⚠️ 同上 |
| `subject-chip-20260923-041855` | 2026-09-23 | 7 | `huishi-backend/worker:subject-chip-20260923-041855` | 正式 | 已被取代 | 含 before.tgz 与 containers.before.txt |
| `asset-upload-20260923-013600` | 2026-09-23 | 9 | `huishi-backend/worker:asset-upload-20260923-013600` | 正式 | 已被取代 | 含 migrate/rollback SQL 与 verify 脚本 |
| `seedance-direct-20260923-001229` | 2026-09-23 | 10 | `huishi-backend/worker:seedance-direct-20260923-001229` | 正式 | 已被取代 | 含数据库迁移与回滚 |
| `subject-picker-20260922-180727` | 2026-09-22 | 4 | （无 image tag） | 正式 | 已被取代 | ⚠️ 无 compose.release.yml 的镜像声明 |
| `task-repair-20260922-164347` | 2026-09-22 | 5 | `huishi-backend/worker:task-repair-20260922-164347` | 正式 | 已被取代 | 含 manifest.json 与 before.tgz |
| `task-repair-20260922-163651` | 2026-09-22 | 5 | 同上形式 | 正式 | 已被取代 | |
| `task-repair-20260922-154826` | 2026-09-22 | 5 | 同上形式 | 正式 | 已被取代 | |
| `task-repair-20260922-135605` | 2026-09-22 | 5 | 同上形式 | 正式 | 已被取代 | |
| `task-repair-20260922-135146` | 2026-09-22 | 5 | 同上形式 | 正式 | 已被取代 | 该系列最早一个 |

## 目录完备度实况（由 `releases/_index.py` 生成）

`/opt/huishi/releases/index.json` 会逐项报告每个 release 是否具备
`Dockerfile`、`prepare.sh`+`deploy.sh`、`manifest`。**当前 28 个 release 中，
只有 9 个同时具备三者**（2026-10-07 的 `capability-balance-20261007` 起才有标准骨架）：

| 能力 | 具备的 release 数 |
|---|---|
| 有 Dockerfile | 23 / 28 |
| 有 prepare.sh + deploy.sh | 11 / 28（`runtime-groups-20261007`、`log-handler-20261007`、`unify-wording-20261007`、`format-marker-20261007`、`unify-adapter-http-20261007`、`paused-tasks-20261007`、`reference-hint-20261007`、`capability-balance-20261007`、`channel-health-20261006`、`subject-reference-20261004`、`video-pricing-fix-20261002`） |
| 有 manifest | 21 / 28 |
| **三者齐全** | **9 / 28**（`runtime-groups-20261007`、`log-handler-20261007`、`unify-wording-20261007`、`format-marker-20261007`、`unify-adapter-http-20261007`、`paused-tasks-20261007`、`reference-hint-20261007`、`capability-balance-20261007`、`subject-reference-20261004`） |

`capability-balance-20261007`（2026-10-07）是**首个按标准骨架产出**的 release，`reference-hint-20261007`、`paused-tasks-20261007`、`unify-adapter-http-20261007`、`format-marker-20261007`、`unify-wording-20261007`、`log-handler-20261007`、`runtime-groups-20261007` 沿用同一骨架：
Dockerfile×2 + prepare.sh + deploy.sh + compose.release/rollback + manifest.sha256 + payload。

> 注：`subject-reference-20261004` 也判定为齐全，但它缺 `payload-worker` 与验证脚本，
> 是"形式齐全"。`capability-balance-20261007` 的缺陷是 layer 语义——
> 分层构建只覆盖不删除，所以它在 Dockerfile 里显式删掉了上一版残留的已删文件。

> 生成方式：`python3 /opt/huishi/releases/_index.py` —— 每次发布后跑一次，
> 它会重写 `index.json` 并列出不完整的 release。该脚本随本清单一起纳入版本控制
> （位于 `deploy/release_index.py`）。

## 已知问题（待收敛）

1. **2026-10-05 起连续 5 个 release 目录退化**：只剩 `compose.release.yml` +
   `compose.rollback.yml`，缺 Dockerfile 与 prepare/deploy 脚本——那几次发布
   靠手工命令完成，**不可复现、无自动回滚保护**。
2. **`task-status-*` 两个 release 的 worker 镜像指向别的发布**
   （`asset-upload-20260923-013600`），回滚时可能取到非预期镜像。
3. **`subject-picker-20260922-180727` 没有镜像声明**，无法仅凭目录完成回滚。
4. **回滚 tag 命名不统一**：有 `rollback-<name>`、`rollback-<date>-<name>`
   两种形态（例：`rollback-20261005-token-fragment` 与
   `rollback-channel-health-20261006`）。
5. **`huishi-canvas-agent` 用 `:latest`**，没有版本化——画布 Agent 的变更
   无法从镜像 tag 追溯。

## 新增发布的流程要求

每个新 release 目录**必须自包含**（对齐 `video-pricing-fix-20261002`
的形态）：

```
releases/<kebab-name-YYYYMMDD[-HHMM]>/
├── Dockerfile.backend      # FROM <基线镜像> + COPY payload/ /app/
├── Dockerfile.worker       # 同 backend（共用镜像，仅 command 不同）
├── compose.release.yml     # 本版镜像 tag
├── compose.rollback.yml    # 回滚镜像 tag
├── manifest.json           # 基线镜像 + 逐文件 sha256
├── prepare.sh              # 打回滚 tag + 备份待覆盖源码
├── deploy.sh               # 构建 + 只重启目标服务（含 ERR trap 自动回滚）
└── payload/                # 本版改动的文件（保持相对路径）
```

发布完成后**回到本文件补一行**，记录 `kind` 与状态。这是让清单不腐化的唯一办法。
