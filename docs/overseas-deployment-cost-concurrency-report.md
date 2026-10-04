# AI 生图网站国外部署成本与并发评估报告

生成日期：2026-06-18  
项目路径：`D:\AI\huishiv2`  
评估口径：国外服务器、域名挂 Cloudflare、生图 API 按 `0.05 元/张`，不计算提示词优化成本，不自建 GPU。

## 1. 结论摘要

你的项目当前不是自建 SDXL/Flux/GPU 推理站，而是一个 Flask Web 应用调用上游 OpenAI 兼容生图 API。服务器主要承担用户登录、积分扣费、任务排队、状态轮询、图片保存和后台调用上游 API，不需要购买 GPU 服务器。

最推荐的商用起步架构是：

```text
海外 4C8G 服务器
Nginx + Gunicorn + Flask
PostgreSQL 同机自建
可选同机 Redis
Cloudflare DNS / SSL / Turnstile
Cloudflare R2 保存生成图片
每日 PostgreSQL 备份到 R2
```

这套架构的固定成本约 `390-706 元/月`；如果开启 Cloudflare Pro 和付费邮件服务，固定成本约 `570-886 元/月`。

按生图 API `0.05 元/张` 估算：

| 日生成图片 | 月 API 成本 | 推荐商用起步版总成本 |
|---:|---:|---:|
| 1,000 张/天 | 1,500 元/月 | 约 1,890-2,386 元/月 |
| 3,000 张/天 | 4,500 元/月 | 约 4,890-5,386 元/月 |
| 5,000 张/天 | 7,500 元/月 | 约 7,890-8,386 元/月 |

服务器不是主要成本，生图 API 才是主要成本。后期运营重点应放在免费额度、防刷、失败重试、单用户并发、单次生成张数和图片生命周期管理上。

## 2. 当前项目依据

本报告基于当前代码形态，而不是通用 AI 生图站假设。

项目证据：

- `huishi/image_api.py`：默认模型参数为 `gpt-image-2`，通过 OpenAI SDK 调用上游兼容接口，并使用 `response_format="b64_json"` 返回图片。
- `huishi/generation_queue.py`：当前后台任务使用 `ThreadPoolExecutor`，并发由 `HUISHI_GENERATION_WORKERS` 控制。
- `huishi/config.py`：默认数据库是 `data/huishi.sqlite3`，默认图片目录是 `static/uploads`。
- `huishi/db.py`：当前使用 `sqlite3.connect(...)`。
- `routes_workspace.py`：一个生图任务可以通过 `count` 生成多张图片，`MAX_GENERATION_COUNT` 控制单次最大数量。

因此：

```text
Gunicorn worker 进程 != 一张图
一个用户 != 一张图
一个后台任务 != 一张图
一个后台任务可以 count=1-4 张图，甚至更多，取决于配置
```

并发评估应按“任务数”计算，而不是按“人数”或“图片数”简单等同。

## 3. 成本来源与估算依据

汇率暂按：

```text
1 USD = 7.2 元人民币
```

实际成本会受地区、活动价、税费、汇率和服务商调整影响，正式采购前应以服务商购买页为准。

| 成本项 | 本报告采用值 | 来源 / 依据 |
|---|---:|---|
| 生图 API | `0.05 元/张` | 用户指定口径 |
| 2C4G 服务器 | DigitalOcean 2 vCPU / 4GB：`$24/月`，约 `173 元/月` | DigitalOcean Droplets 官方价，2 vCPU / 4GB / 4TB transfer |
| 4C8G 服务器 | DigitalOcean 4 vCPU / 8GB：`$48/月`，约 `346 元/月` | DigitalOcean Droplets 官方价，4 vCPU / 8GB / 5TB transfer |
| 托管 PostgreSQL 2GB | `$30.45/月`，约 `219 元/月` | DigitalOcean Managed Databases 官方价 |
| 托管 PostgreSQL 4GB | `$60.90/月`，约 `438 元/月` | DigitalOcean Managed Databases 官方价 |
| Redis / Valkey 1GB | `$15/月`，约 `108 元/月` | DigitalOcean Managed Caching for Valkey 官方价 |
| Cloudflare R2 存储 | `$0.015/GB/月`，前 10GB 免费 | Cloudflare R2 官方价 |
| Cloudflare R2 流出流量 | `0 元` | Cloudflare R2 egress 免费 |
| Cloudflare R2 操作 | Class A 前 100 万次/月免费；Class B 前 1000 万次/月免费 | Cloudflare R2 官方免费额度 |
| Cloudflare DNS / SSL | 免费可用 | Cloudflare Free 方案 |
| Cloudflare Pro | `$25/月`，约 `180 元/月`，可选 | Cloudflare 官方套餐 |
| 邮箱服务 | Resend 免费 3000 封/月；Pro `$20/月`；Amazon SES `$0.10/1000 封` | Resend / Amazon SES 官方价 |
| 域名 | 约 `5-15 元/月` 折算 | 取决于 TLD 和注册商；Cloudflare Registrar 按成本价原则 |
| 备份 / 监控 | 约 `20-500 元/月` | PG dump 到 R2、云商快照、Uptime 监控、日志保留等 |

主要参考页面：

- DigitalOcean Droplets Pricing: https://www.digitalocean.com/pricing/droplets
- DigitalOcean Managed Databases Pricing: https://www.digitalocean.com/pricing/managed-databases
- Cloudflare R2 Pricing: https://developers.cloudflare.com/r2/pricing/
- Cloudflare Plans: https://www.cloudflare.com/plans/
- Resend Pricing: https://resend.com/pricing
- Amazon SES Pricing: https://aws.amazon.com/ses/pricing/

## 4. 生图 API 成本

公式：

```text
月 API 成本 = 日生成图片数 * 30 * 0.05 元
```

| 日生成图片 | 月生成图片 | API 成本/月 |
|---:|---:|---:|
| 300 | 9,000 | 450 元 |
| 1,000 | 30,000 | 1,500 元 |
| 3,000 | 90,000 | 4,500 元 |
| 5,000 | 150,000 | 7,500 元 |
| 10,000 | 300,000 | 15,000 元 |
| 30,000 | 900,000 | 45,000 元 |

这部分是最大成本项。服务器从 2C4G 升到 4C8G 通常只是每月增加一两百元，但日生成从 1,000 张增长到 5,000 张，会增加 `6,000 元/月` 的 API 成本。

## 5. 图片存储与流量成本

假设：

```text
平均每张图 2MB
每张图平均被查看 / 下载 5 次
图片存 Cloudflare R2
```

| 日生成图片 | 月新增图片 | 月新增存储 | 图片访问流量 |
|---:|---:|---:|---:|
| 1,000 | 30,000 | 约 59GB | 约 293GB |
| 3,000 | 90,000 | 约 176GB | 约 879GB |
| 5,000 | 150,000 | 约 293GB | 约 1.46TB |
| 10,000 | 300,000 | 约 586GB | 约 2.9TB |

Cloudflare R2 对公网流出流量不收费，因此图片访问流量不会像传统对象存储 + CDN 那样成为主要成本。

如果图片保留 3 个月，R2 存储费大致如下：

| 日生成图片 | 3 个月累计存储 | R2 存储费/月 |
|---:|---:|---:|
| 1,000 | 约 176GB | 约 18 元 |
| 3,000 | 约 527GB | 约 56 元 |
| 5,000 | 约 879GB | 约 94 元 |
| 10,000 | 约 1.76TB | 约 188 元 |

R2 的 Class A / Class B 操作在早期大概率也在免费额度内：

- Class A：上传、复制、删除、列目录等写类/管理类操作，前 100 万次/月免费。
- Class B：读取图片、下载图片、获取对象等读类操作，前 1000 万次/月免费。

示例：日生成 3,000 张，月 90,000 张，每张看 5 次：

```text
Class A 上传约 90,000 次/月
Class B 读取约 450,000 次/月
```

都低于 R2 免费额度。

## 6. 三套部署方案

### 方案一：低成本内测版

适合：

```text
100-1000 DAU
日生成 300-1000 张
验证产品、测试付费转化、控制预算
```

架构：

```text
2C4G 海外服务器
Nginx + Gunicorn + Flask
PostgreSQL 同机自建
不单独上 Redis，沿用本机任务线程池
Cloudflare DNS / SSL / Turnstile
Cloudflare R2 存图
Resend Free 或 Amazon SES 发验证码
每日 PG dump 备份到 R2
```

固定成本：

| 项目 | 配置 | 月成本 |
|---|---|---:|
| 服务器 | 2C4G 海外 VPS | 约 173 元 |
| PostgreSQL | 同机自建 | 0 |
| Redis | 暂不上 | 0 |
| R2 存储 | 低量图片 | 0-20 元 |
| DNS / SSL / 基础防护 | Cloudflare Free | 0 |
| 邮箱 | Resend Free / SES | 0-10 元 |
| 域名 | 月折算 | 5-15 元 |
| 备份 | PG dump 到 R2 | 0-20 元 |
| **固定成本合计** |  | **约 180-240 元/月** |

加 API 后：

| 日生成图片 | API 成本 | 总成本/月 |
|---:|---:|---:|
| 300 | 450 元 | 约 630-690 元 |
| 1,000 | 1,500 元 | 约 1,680-1,740 元 |

并发能力：

| 指标 | 估算 |
|---|---:|
| DAU | 100-1000 |
| 同时在线 | 20-100 |
| running 生图任务 | 4-6 |
| 排队任务 | 50-150 |
| 推荐 `HUISHI_GENERATION_WORKERS` | 2-3 |

注意：该方案很省钱，但网站和数据库同机，必须做好自动备份。

### 方案二：推荐商用起步版

适合：

```text
1000-5000 DAU
日生成 1000-5000 张
开始收费或准备正式运营
```

架构：

```text
4C8G 海外服务器
Nginx + Gunicorn + Flask
PostgreSQL 同机自建
可选同机 Redis
Cloudflare DNS / SSL / Turnstile
Cloudflare R2 存图
Resend Free / SES，量大再升付费邮箱
每日 PG dump 到 R2
可选 Cloudflare Pro
```

4C8G 阶段 PostgreSQL 同机是合理的。拆 PG 是后期稳定性方案，不是早期必须项。

固定成本：

| 项目 | 配置 | 月成本 |
|---|---|---:|
| 服务器 | 4C8G 海外 VPS | 约 346 元 |
| PostgreSQL | 同机自建 | 0 |
| Redis | 同机自建或暂不上 | 0 |
| R2 存储 | 保留 1-3 个月图片 | 20-100 元 |
| DNS / SSL | Cloudflare Free | 0 |
| 邮箱 | Resend Free / SES / Resend Pro | 0-145 元 |
| 域名 | 月折算 | 5-15 元 |
| 备份 / 监控 | PG dump、快照、Uptime | 20-100 元 |
| Cloudflare Pro | 可选 | 0 或 180 元 |
| **固定成本合计，不开 Pro** |  | **约 390-706 元/月** |
| **固定成本合计，开 Pro** |  | **约 570-886 元/月** |

加 API 后：

| 日生成图片 | API 成本 | 不开 Pro 总成本 | 开 Pro 总成本 |
|---:|---:|---:|---:|
| 1,000 | 1,500 元 | 约 1,890-2,206 元 | 约 2,070-2,386 元 |
| 3,000 | 4,500 元 | 约 4,890-5,206 元 | 约 5,070-5,386 元 |
| 5,000 | 7,500 元 | 约 7,890-8,206 元 | 约 8,070-8,386 元 |

并发能力：

| 指标 | 估算 |
|---|---:|
| DAU | 1000-5000 |
| 同时在线 | 100-500 |
| running 生图任务 | 8-15 |
| 排队任务 | 300-800 |
| 推荐 `HUISHI_GENERATION_WORKERS` | 4-5 起步，稳定后再增 |

该方案是当前最推荐路线：成本低、性能足够、PG 同机省钱，复杂度不高。

### 方案三：增长稳定版

适合：

```text
5000-15000+ DAU
日生成 5000-30000 张
已验证付费，开始关注可用性、队列稳定和故障隔离
```

架构：

```text
Web 服务器 4C8G
Worker 服务器 4C8G
托管 PostgreSQL 4GB
托管 Redis / Valkey
Cloudflare R2
Cloudflare Pro
Resend Pro / Amazon SES
监控、备份、日志
```

固定成本：

| 项目 | 配置 | 月成本 |
|---|---|---:|
| Web 服务器 | 4C8G | 约 346 元 |
| Worker 服务器 | 4C8G | 约 346 元 |
| 托管 PostgreSQL | 4GB | 约 438 元 |
| 托管 Redis / Valkey | 1GB-4GB | 108-432 元 |
| R2 存储 | 1-5TB 累计图片 | 100-500 元 |
| Cloudflare Pro | 建议开启 | 180 元 |
| 邮箱 | Resend Pro / SES | 145-300 元 |
| 域名 | 月折算 | 5-15 元 |
| 备份 / 监控 / 日志 | 快照、日志、监控 | 100-500 元 |
| **固定成本合计** |  | **约 1,768-3,057 元/月** |

加 API 后：

| 日生成图片 | API 成本 | 总成本/月 |
|---:|---:|---:|
| 5,000 | 7,500 元 | 约 9,268-10,557 元 |
| 10,000 | 15,000 元 | 约 16,768-18,057 元 |
| 30,000 | 45,000 元 | 约 46,768-48,057 元 |

并发能力：

| 指标 | 估算 |
|---|---:|
| DAU | 5000-15000+ |
| 同时在线 | 500-2000 |
| running 生图任务 | 20-50 |
| 排队任务 | 1000-3000+ |
| 队列形态 | Redis / Celery / RQ |

该阶段开始，固定成本已经不是主要矛盾，API 成本和滥用控制才是主要矛盾。

## 7. 并发与等待时间模型

关键公式：

```text
预计完成时间 = ceil((前面排队任务数 + 1) / running 生图任务并发) * 单任务平均耗时
```

如果单任务平均 60 秒：

| running 任务并发 | 前面 10 个任务 | 前面 50 个任务 | 前面 200 个任务 |
|---:|---:|---:|---:|
| 5 | 约 3 分钟 | 约 11 分钟 | 约 41 分钟 |
| 10 | 约 2 分钟 | 约 6 分钟 | 约 21 分钟 |
| 20 | 约 1 分钟 | 约 3 分钟 | 约 11 分钟 |
| 50 | 约 1 分钟 | 约 2 分钟 | 约 5 分钟 |

注意：

```text
running 生图任务是任务数，不是图片数。
如果 10 个任务同时运行，且每个任务 count=4，最多可能同时向上游请求 40 张图片。
```

建议限制：

| 阶段 | `MAX_ACTIVE_GENERATION_TASKS_PER_USER` | `MAX_GENERATION_COUNT` |
|---|---:|---:|
| 内测 | 1-2 | 2-4 |
| 商用起步 | 1-2 | 2-4 |
| 增长期 | 按会员等级区分 | 普通 2-4，VIP 可更高 |

## 8. PostgreSQL 是否同机

结论：

```text
4C8G 阶段，PostgreSQL 同机是合理的，性价比高。
```

建议：

| 阶段 | PG 部署建议 |
|---|---|
| 2C2G | 不建议同机 PG，内存太紧 |
| 2C4G | 可以同机 PG，适合内测 |
| 4C8G | 推荐同机 PG，适合商用起步 |
| DAU 5000+、数据库几十 GB、不能接受单机故障 | 拆 PG 或用托管 PG |

4C8G 同机大致内存分配：

| 服务 | 内存预算 |
|---|---:|
| 系统 + Nginx | 0.5-1GB |
| Gunicorn / Flask | 0.5-1.5GB |
| 后台任务 Worker | 1-2GB |
| PostgreSQL | 1.5-3GB |
| Redis，可选 | 0.2-0.5GB |
| 系统缓存 / 预留 | 1-2GB |

拆分触发点：

- 内存长期超过 75%。
- PG CPU / IO 明显抢应用资源。
- 数据库超过 20-50GB 且增长快。
- 付费流水变多，不能接受单机故障。
- DAU 超过 5000-10000。
- 需要高可用、自动备份、时间点恢复。

## 9. 服务器地区与服务商建议

如果主要用户在中国大陆，但不想备案：

```text
优先香港，其次新加坡 / 日本，再其次美国西海岸。
```

如果主要用户在海外：

```text
Cloudflare + R2 + 海外服务器很划算。
```

国外服务器可选：

| 服务商 | 适合情况 |
|---|---|
| Hetzner | 极致省钱，欧洲/美国便宜，但大陆访问一般 |
| Vultr | 日本、新加坡、美国节点多，适合亚洲用户 |
| DigitalOcean | 稳定，托管 PG / Redis 方便，价格清楚 |
| AWS Lightsail | 稳定，价格清晰，生态强 |
| 阿里云国际 / 美国 | 熟悉阿里生态时可选，但大陆访问延迟偏高 |

应用、PG、Redis 应尽量放在同地区，最好同服务商。同机或同内网都可以。不要把应用放美国、PG 放欧洲、Redis 放香港，这会导致任务轮询、积分扣费和资产查询变慢。

## 10. 风险与优化建议

### 必做

1. 生产环境使用 Nginx + Gunicorn，不使用 Flask dev server。
2. 限制单用户同时活跃任务数，避免一个用户塞满队列。
3. 控制 `HUISHI_GENERATION_WORKERS`，从较低并发逐步上调。
4. 图片尽快迁移到 Cloudflare R2，不建议长期放 `static/uploads`。
5. 每日自动备份 PostgreSQL 到 R2。
6. 注册、登录、生图提交接入 Turnstile 或应用层限流。
7. 记录每次上游 API 成功率、耗时、失败原因和重试成本。

### 建议配置

内测 / 2C4G：

```env
HUISHI_GENERATION_WORKERS=2
HUISHI_MAX_ACTIVE_GENERATION_TASKS_PER_USER=1
HUISHI_MAX_GENERATION_COUNT=2
HUISHI_MAX_REFERENCE_IMAGE_BYTES=5M
```

商用起步 / 4C8G：

```env
HUISHI_GENERATION_WORKERS=4
HUISHI_MAX_ACTIVE_GENERATION_TASKS_PER_USER=1
HUISHI_MAX_GENERATION_COUNT=2 或 4
HUISHI_MAX_REFERENCE_IMAGE_BYTES=5M
```

稳定后再逐步调高并发。不要一次性把并发拉满。

## 11. 最终推荐路线

第一阶段，直接上推荐商用起步版：

```text
海外 4C8G
网站 + PostgreSQL 同机
图片放 Cloudflare R2
Cloudflare DNS / SSL / Turnstile
邮箱先用 Resend Free 或 Amazon SES
每日 PG 备份到 R2
```

预算：

```text
固定成本：约 390-706 元/月
开 Cloudflare Pro / 付费邮箱后：约 570-886 元/月
```

含 API 后：

```text
日 1,000 图：约 1,900-2,400 元/月
日 3,000 图：约 4,900-5,400 元/月
日 5,000 图：约 7,900-8,400 元/月
```

第二阶段，达到以下任一条件再拆分：

- DAU 超过 5000。
- 日生成超过 5000 张且排队明显。
- PG 数据超过 20-50GB。
- 单机故障会造成明显收入损失。
- 需要高可用 / 时间点恢复。

拆分目标：

```text
Web 服务器
Worker 服务器
托管 PostgreSQL
托管 Redis
Cloudflare R2
Cloudflare Pro / WAF
```

总体判断：

```text
早期不要过度购买服务器。
4C8G + 同机 PG + R2 已经足够支撑早期商用。
真正需要精细控制的是 API 成本、队列并发、防刷和失败重试。
```
