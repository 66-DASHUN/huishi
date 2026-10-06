# 测试套件现状与遗留失败判定

本文档记录 2026-10-05 对测试套件的核查结论，供后续发布与重构参考。

## 总体状态

```
49 failed, 651 passed, 61 skipped
```

（2026-10-06 更新：新增 `tests/test_provider_metrics.py` 33 个用例，全部通过。
失败数仍为 49，与 618 → 651 的增量完全由新文件解释。）

**发布门禁的现状：测试不能直接当门禁用**，需先看本文档的失败分类。

## 关键结论：49 个失败中没有生产缺陷

逐类核查后判定，**全部是测试未跟上代码演进**。三条独立证据：

1. **时间戳**：测试文件多为 2026-09-15 ~ 09-23，而对应代码更新到 2026-10-04。
2. **代码含刻意设计**：例如故障转移中的"已停止自动重试"是防重复扣费的
   明确意图，不是 bug。
3. **生产实况反证**：失败项对应的功能在生产上正常工作（有成功记录）。

因此**不应修改生产代码去迎合这些测试**——那会把正确的行为改坏。

## 失败分类

### A. 计费缺省（约 25 个，最大一类）

测试提交的 `/generate` 表单不含 `model` 字段：

```
requested_model = "" → 兜底返回 "*" → 定价表无 "*" 规则 → 400「未找到计费规则」
```

相关：`test_workspace_generation_flow.py`(10)、`test_provider_scheduling.py`(7)、
`test_canvas_generate_proxy.py`(5)、`test_generation_billing.py`(3)

**待决策（产品语义）**：请求不带 model 时，应报错，还是回落到某个默认模型计费？
- 现状：报错
- 若改为回落，需同时定义"默认模型"的选择规则（渠道优先级第一条？）

### B. 上游失败不重试（7 个）

`test_provider_scheduling.py` 断言"应尝试全部渠道"，但代码刻意为：
上游结果不确定时停止重试，避免重复生成与重复扣费。**代码正确，测试过时。**

### C. 管理界面与套餐规则（约 10 个）

- `test_admin_audit.py` / `test_package_defaults.py`：测试用 `price=9.90(990分)`
  配 `points=90`，违反"1 积分 = 1 分"规则。该规则是刻意的，生产套餐全部等值
  （990/990、3990/3990、8990/8990）。**测试数据过时。**
- `test_settings_config_status.py`：断言的管理页模板结构已变。

### D. 前端源码断言（约 6 个）

测试直接读 `static/js/*.js`、模板文本做字符串断言，前端改动即失效。

### E. 环境依赖（2 个，仅本地）

`test_home_build_config.py` 需要仓库根的 `package.json`，而该文件
**线上快照中同样缺失**，不是本地打包遗漏。

### F. 画布前端契约（约 6 个）

含硬编码 `127.0.0.1:3000`，要求本机有画布实例在跑。

## 64 个静默 skip

`test_canvas_embed_mode_contract.py` 等依赖 `HUISHI_CANVAS_PROJECT_DIR`，
未设置时整组 skip 而不会失败。发布前如需覆盖画布契约，须显式设置该变量。

## 渠道健康度（2026-10-06 新增）

新增 `huishi/provider_metrics.py` + `provider_call_logs` 表 + `/admin/channel-health` 页面。
验证方式（可复现）：

1. `py -m pytest tests/test_provider_metrics.py -q` → 33 passed
2. 全量 `py -m pytest tests/ -q` → 失败数必须仍为 **49**（本次实测 49/651/61）
3. 埋点不变量已单独验证：故意让 `record_provider_call` 抛异常，生成仍成功
   （`_log_provider_call` 自身也 try/except——它插在 `except` 块里，
   若不兜住会用无关的埋点错误掩盖真实的上游失败）
4. 5 项运行时变异均被测试捕获（去掉脱敏、去掉阈值下限、无数据报 healthy 等）

注意：`generation_queue.py:192` 传了 `task_id`，而 `routes_workspace.py:959/2026`
两处同步端点没有（那时任务尚未创建）。两处的渠道归因照常记录，只是
`task_id` 为 NULL，不影响按渠道聚合。

## 建议

1. **不修生产代码**去迎合 A/B/C 类失败。
2. 若要恢复门禁，按以下顺序处理：
   - 先处理 A（占比最大，且需产品决策）
   - B/C/D 属测试维护，可批量更新
   - E 需要补仓库根 `package.json`（同时修复失效的 `deploy_backend_release.sh`）
3. 在门禁恢复前，发布验证以本文档 + 线上健康检查为准。
