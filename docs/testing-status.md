# 测试套件现状与发布门禁

本文档记录测试套件的当前状态。**2026-10-07 起，测试重新成为可用的发布门禁。**

## 总体状态

```
829 passed, 0 failed, 0 skipped
```

历史对照：

| 时间 | 结果 | 说明 |
|---|---|---|
| 2026-10-05 | `49 failed, 651 passed, 61 skipped` | 失败全部判定为"测试未跟上代码演进" |
| 2026-10-06 | `47 failed, 665 passed, 61 skipped` | 新增渠道健康度埋点后，2 个旧失败转绿 |
| 2026-10-07 | `758 passed, 0 failed, 0 skipped` | 清理全部遗留失败 + 消除静默跳过；E1 删掉 27 个已失效用例、E2 新增 4 个 |
| **2026-10-08** | **`829 passed, 0 failed, 0 skipped`** | 本轮新增 71 个用例（条目优先级选路、发布脚本守卫、@ 引用编号说明、UI 契约等） |

**发布门禁规则：全量必须是 `0 failed`。** 任何上升都说明引入了真回归。

### 前端行为测试（需要 node）

除 pytest 外，仓库内还有两个**用最小 DOM 桩执行真实前端函数**的检查：

| 文件 | 覆盖 |
|---|---|
| `tests/check_settings_models.cjs` | 渠道模型目录解析、模型合并 |
| `tests/check_workspace_mention.cjs` | @ 提及面板的开关、锚点选择、媒体类型适配 |

它们比"断言源码里含某段字符串"强得多——检查的是实参、分支与调用次数。

`npm test` 会先跑 pytest 再跑这两个（见 `check:js`）。**但发布门禁（容器内
`python -m pytest`）跑不到它们**：镜像里没有 node。所以它们属于本地/CI 侧
校验，发布时不要以为"门禁全绿"就覆盖了前端逻辑。

### 为什么 773 → 758

数字下降是**清理**，不是回归：

| 变更 | 用例数 |
|---|---|
| E1 删除 `tests/test_deploy_release_scripts.py`（15 个）、`tests/test_deployment_assets.py`（12 个） | −27 |
| E2 为 `pg_dump` 入口守卫、口令脱敏新增用例（`tests/test_backup.py`） | +4 |
| E2 把 1 个旧断言改为更细粒度的断言（失败报文由"只记异常类型名"改为"记录真实原因 + 已脱敏"） | ±0 |
| **合计** | **758** |

那 27 个用例断言的是 systemd 时代的发布脚本清单（`deploy/deploy_backend_release.sh`
等），而这批脚本本身已删除——脚本没了，断言其内容的测试也就失去对象。它们
承载的发布契约由 `deploy/release_template/` + `deploy/release_index.py` 承接。

**判据是 `0 failed` 且不存在"原本通过、现在变红"的用例，不是总数。**

## 本轮做了什么

### 1. 清理 47 个遗留失败

**原则：只改测试，不改生产代码**（除非发现真实缺陷）。逐类处置：

| 类 | 数量 | 处置 |
|---|---|---|
| A 计费缺省 | ~25 | 语义已由用户裁定（**不带 `model` → 报错**）。测试改为显式传 `model` 并配置对应渠道，从而测到原本想测的行为 |
| B 上游失败不重试 | 7 | 代码刻意如此（防重复扣费）。测试断言改为"立即停止、不切换渠道"，并重命名为能表达该意图的名字 |
| C 管理界面与套餐规则 | ~10 | 测试数据违反"1 积分 = 1 分"（如 `9.90 元 / 90 积分`）→ 改为等值 |
| D 前端源码断言 | ~6 | 前端结构已重构 → 断言改指向新契约（`mm-table`、`data-catalog`、`CanvasPromptLibrary` 等） |
| E 环境依赖 | 2 | 补齐仓库根 `package.json` 等 4 个文件后自然修复 |
| F 画布前端契约 | ~6 | 见下 |

**关键判据**：不算"为了变绿而改测试"——每条改动都先核实了**生产代码的真实行为**，
确认测试断言的旧前提已不成立，才改写。其中 3 处还发现并固定了**刻意设计**：
- 上游失败不重试（防重复扣费）
- 生图 POST 固定 `max_retries=0`（超时可能已计费）
- 单能力渠道的模型条目显式补 `media_type`

**发现并修复的真实缺陷**（非测试问题）：
- `save_provider` 启用渠道时未清除历史 `disabled_at`（线上 3 行脏数据）
- 上游返回 HTML/非 JSON 时抛 `AttributeError`，导致 failover 失效且埋点丢失

### 2. 消除 61 个静默跳过

`test_canvas_embed_mode_contract.py`(52) 与 `test_canvas_identity_phase1_external.py`(9)
依赖 `HUISHI_CANVAS_PROJECT_DIR`，未设置时**整组 skip 而不失败**。

静默跳过比失败更危险——"没覆盖"看起来和"通过"完全一样。本轮：

- `tests/conftest.py` 默认把该变量指向仓库内的 `infinite-canvas/`，
  这些契约**默认参与回归**（仍可用环境变量覆盖为外部路径）
- 开启后暴露 1 个过时断言并修复：提示词库入口**被刻意从画布隐藏**
  （画布自身契约 `canvas-surface-contract.test.ts` 的
  "canvas hides the prompt library entry" 已明确要求），
  该入口只在图片/视频页面提供

### 3. 同步更新的文档

- `docs/testing-status.md`（本文件）
- 仓库根补齐 4 个缺失文件（`.env.example`、`package.json`、`README.md`、`tailwind.home.config.js`）

## 发布前执行

```bash
# 在容器内跑（环境完整，是权威结果）
cd /opt/huishi
docker compose -f compose.prod.yml exec -T backend python -m pytest tests/ -q
```

等价的容器外跑法（不依赖运行中的服务）：

```bash
docker run --rm -e HUISHI_DATABASE=/tmp/t.sqlite3 -e HUISHI_ENV=test \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app -w /app --entrypoint python \
  huishi-backend:<release> -m pytest tests/ -q -p no:cacheprovider | tail -2
```

**注意**：测试套件默认用临时 SQLite，不会碰生产库。
`HUISHI_TEST_DATABASE_URL` 若被设置，`tests/conftest.py` 会强制要求库名含
`test`/`pytest`/`rehearsal`，否则拒绝启动——这是防误连生产的设计。

`deploy.sh` 本身**不跑测试**，发布前请手工执行。
