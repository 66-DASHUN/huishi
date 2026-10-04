# AI 生图网站部署成本、带宽与并发采购规划

生成日期：2026-06-19  
项目路径：`D:\AI\huishiv2`  
预算币种：人民币，粗略汇率按 `1 USD ≈ 7.2 元`、`1 EUR ≈ 7.8 元`  
业务口径：上游 API 生图 `0.05 元/张`，不计算提示词优化成本  
用户口径：中国大陆用户为主，不备案，服务器优先日本，其次美国西海岸  
图片口径：上游返回图片 URL，单张图片按 `7MB`，单任务平均 `90 秒`  

## 1. 采购结论

你的项目不是自建 GPU 推理站，而是 Flask 网站调用上游生图 API。当前更合理的链路是：

```text
用户 -> Cloudflare -> Nginx/Gunicorn/Flask -> 上游生图 API -> 返回图片 URL
```

图片存储分两套：

| 模式 | 链路 | 成本特点 | 推荐阶段 |
|---|---|---|---|
| 保存上游 URL | 服务器只保存 URL，用户直接访问上游图 | 服务器不搬运 7MB 图片，成本最低 | 当前测试 / 早期商用 |
| Worker 转存 R2 | 服务器提交 URL 给 Worker，Worker 拉图写 R2 | 图片资产可控，增加 Worker/R2 成本 | 商用稳定后 |
| 服务器本地下载 | 用户从你的服务器下载图片 | 7MB 大图容易打满带宽 | 不推荐 |

推荐采购路线：

| 阶段 | 推荐配置 | 并发目标 | 月成本估算 |
|---|---|---:|---:|
| 当前测试 | 现有 `2C2G 200M`，保存上游 URL | running 2-4 个任务，4 分钟内前面最多排队 3-7 个任务 | API 450-1500 元 + 现有服务器费用 |
| 推荐商用 | 日本 `4C8G` VPS，PG 同机，保存 URL，R2 可选 | running 8-12 个任务，4 分钟内前面最多排队 15-23 个任务 | 约 1800-8500 元 |
| 中型流量 | Web + Worker 拆分，PG 独立/托管，Redis 队列 | running 20-50 个任务 | 约 8200-50000 元 |

最建议先落地：

```text
日本 4C8G VPS
Nginx + Gunicorn + Flask
PostgreSQL 同机自建
Cloudflare DNS / SSL / Turnstile
默认保存上游图片 URL
商用后用 Cloudflare Worker 异步转存 R2
Resend Free 或 Amazon SES 发邮件
```

## 2. 成本来源总表

这些链接优先选官方价格页、购买页或计费说明页，点进去可以核价或进一步购买。

| 成本项 | 可选产品 | 价格/购买链接 | 备注 |
|---|---|---|---|
| 日本/美国 VPS | Vultr Cloud Compute | [Vultr Pricing](https://www.vultr.com/pricing/) | 日本、美国节点较全，适合优先看日本 |
| 美国 VPS | DigitalOcean Droplets | [Droplets Pricing](https://www.digitalocean.com/pricing/droplets)、[Bandwidth Billing](https://docs.digitalocean.com/platform/billing/bandwidth/) | 价格透明，美国节点成熟 |
| VPS | Akamai / Linode | [Akamai Cloud Pricing](https://www.akamai.com/cloud/pricing) | 常见套餐含 transfer，适合横向比价 |
| VPS / 轻量云 | AWS Lightsail | [Lightsail Pricing](https://aws.amazon.com/lightsail/pricing/)、[Data transfer allowance](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-faq-data-transfer-allowance.html) | 日本/美国可选，transfer 规则需看说明 |
| 国内云海外 ECS | 阿里云国际 ECS | [ECS Pricing](https://www.alibabacloud.com/en/product/ecs/pricing)、[ECS 价格列表](https://www.alibabacloud.com/zh/product/ecs-pricing-list/en) | 需选日本/美国地域、实例、云盘、带宽 |
| 国内云海外流量 | 阿里云 CDT / 公网带宽 | [Internet Data Transfers](https://www.alibabacloud.com/help/en/cdt/internet-data-transfers/)、[ECS Public Bandwidth](https://www.alibabacloud.com/help/en/ecs/public-bandwidth) | 国内云海外常把公网流量单独计费 |
| 国内云海外 CVM | 腾讯云国际 CVM | [CVM Pricing](https://buy.tencentcloud.com/pricing/cvm?lang=en) | 需在购买页选择日本/美国地域 |
| 腾讯云公网 | 公网计费 / 带宽包 | [Public Network Billing](https://www.tencentcloud.com/document/product/213/10578)、[Bandwidth Package](https://intl.cloud.tencent.com/product/bwp) | 可按带宽、流量或带宽包 |
| 国内云海外 ECS | 华为云国际 ECS | [ECS Product](https://www.huaweicloud.com/intl/en-us/product/ecs.html)、[Pricing Calculator](https://www.huaweicloud.com/intl/en-us/pricing/calculator.html) | 需要计算器选地域核价 |
| 国内云海外 | UCloud Global | [UCloud Global Pricing](https://www.ucloud-global.com/price)、[UCloud 官网](https://www.ucloud.cn/) | 需确认日本/美国节点和活动价 |
| 对象存储 | Cloudflare R2 | [R2 Pricing](https://developers.cloudflare.com/r2/pricing/)、[R2 Calculator](https://r2-calculator.cloudflare.com/) | R2 egress 免费，适合大图访问 |
| Worker 转存 | Cloudflare Workers | [Workers Pricing](https://developers.cloudflare.com/workers/platform/pricing/)、[Workers Product Pricing](https://www.cloudflare.com/products/workers/) | 用 Worker 拉上游 URL 写 R2，省服务器带宽 |
| Worker + R2 文档 | Cloudflare R2 Workers API | [Use R2 from Workers](https://developers.cloudflare.com/r2/api/workers/workers-api-usage/) | 实现异步转存时用 |
| 传统对象存储 | AWS S3 | [S3 Pricing](https://aws.amazon.com/s3/pricing/) | 存储便宜但公网 egress 通常贵 |
| 轻量对象存储 | Lightsail Object Storage | [Lightsail Pricing](https://aws.amazon.com/lightsail/pricing/) | 含一定 transfer，超额另算 |
| PostgreSQL | DigitalOcean Managed Databases | [DO Managed Databases](https://www.digitalocean.com/pricing/managed-databases) | 拆 PG 后可选 |
| PostgreSQL | Supabase | [Supabase Pricing](https://supabase.com/pricing) | 托管 PG + 后台生态 |
| PostgreSQL | Aiven | [Aiven Pricing](https://aiven.io/pricing) | 有低价开发档，适合对比 |
| Redis / 队列 | Upstash Redis | [Upstash Redis Pricing](https://upstash.com/pricing/redis) | 轻量队列/限流可选 |
| Redis / Valkey | DigitalOcean Managed Caching | [DO Managed Databases](https://www.digitalocean.com/pricing/managed-databases) | 中型后可托管 |
| 邮箱 | Resend | [Resend Pricing](https://resend.com/pricing) | 免费额度适合早期验证码 |
| 邮箱 | Amazon SES | [SES Pricing](https://aws.amazon.com/ses/pricing/) | 单价低，配置稍复杂 |
| DNS / SSL / WAF | Cloudflare Plans | [Cloudflare Plans](https://www.cloudflare.com/plans/) | DNS/SSL Free 可用，Pro 可选 |
| 防机器人 | Cloudflare Turnstile | [Turnstile](https://www.cloudflare.com/products/turnstile/) | 注册、登录、生图提交建议接入 |
| 域名注册 | Cloudflare Registrar | [Cloudflare Registrar](https://www.cloudflare.com/products/registrar/) | 成本价注册域名 |
| 域名注册 | Porkbun | [Porkbun Domain Pricing](https://porkbun.com/products/domains) | `.com` 年费可直接查看 |
| DNS 备选 | AWS Route 53 | [Route 53 Pricing](https://aws.amazon.com/route53/pricing/) | 若不用 Cloudflare DNS 时参考 |

## 3. 并发与计费口径

代码依据：

| 文件 | 当前情况 |
|---|---|
| `huishi/generation_queue.py` | 使用 `ThreadPoolExecutor` 跑后台生图任务 |
| `huishi/config.py` | `HUISHI_GENERATION_WORKERS` 默认 `3` |
| `huishi/image_api.py` | 可解析 `b64_json`，也可直接保存上游返回的 `url` |
| systemd | `gunicorn -w 2`，即 2 个 Gunicorn worker |

并发公式：

```text
running 任务并发 = Gunicorn worker 数 × HUISHI_GENERATION_WORKERS
running 图片并发 = running 任务并发 × 单任务 count
日生成图片数 = 日生成任务数 × 平均 count
月 API 成本 = 日生成图片数 × 30 × 0.05 元
```

成本按图片数算，排队体验按任务数算。

| running 任务并发 | count | 同时生成图片 | 单轮 API 成本 |
|---:|---:|---:|---:|
| 4 | 1 | 4 张 | 0.20 元 |
| 4 | 2 | 8 张 | 0.40 元 |
| 8 | 2 | 16 张 | 0.80 元 |
| 12 | 2 | 24 张 | 1.20 元 |
| 12 | 4 | 48 张 | 2.40 元 |

4 分钟体验线，按单任务平均 `90 秒`：

| running 任务并发 | 4 分钟内最多完成任务 | 前面最多排队任务 |
|---:|---:|---:|
| 2 | 4 | 3 |
| 4 | 8 | 7 |
| 8 | 16 | 15 |
| 12 | 24 | 23 |
| 20 | 40 | 39 |
| 50 | 100 | 99 |

推荐限制：

| 阶段 | running 任务并发 | 单任务 count | 4 分钟体验线 |
|---|---:|---:|---:|
| 当前 2C2G | 2-4 | 免费用户 1，普通最多 2 | 前面排队 3-7 个任务 |
| 商用 4C8G | 8-12 | 默认 1，会员 2/4 | 前面排队 15-23 个任务 |
| Web + Worker | 20-50 | 按会员等级 | 前面排队 39-99 个任务 |

## 4. 图片、带宽与 R2 成本

### 4.1 三种图片链路

| 模式 | 链路 | 服务器图片流量 | 适合场景 |
|---|---|---:|---|
| 保存上游 URL | 上游返回 URL，服务器只存 URL，用户访问上游 URL | 约 0 | 当前测试、最低成本 |
| Worker 转存 R2 | 服务器把 URL/object key 发给 Worker，Worker 拉图写 R2 | 约 0 | 商用后历史作品可控 |
| 服务器本地搬运 | 服务器下载上游图，再上传 R2 或返回用户 | 高 | 不推荐 |

Worker 转存推荐链路：

```text
你的服务器 -> Worker：提交 URL 和 object key
Worker -> 上游 URL：拉图
Worker -> R2：写入
用户 -> R2 / Cloudflare：查看图片
```

### 4.2 7MB 图片体量

假设每张图 `7MB`，每张平均查看/下载 `5 次`：

| 日生成图片 | 月新增图片体积 | 月图片访问流量 |
|---:|---:|---:|
| 300 | 约 62GB | 约 307GB |
| 1000 | 约 205GB | 约 1.02TB |
| 3000 | 约 615GB | 约 3.07TB |
| 5000 | 约 1.03TB | 约 5.13TB |
| 10000 | 约 2.05TB | 约 10.25TB |

R2 存储按约 `0.108 元/GB-month` 粗算：

| 日生成图片 | 保留 1 个月 | 保留 3 个月 |
|---:|---:|---:|
| 1000 | 约 22 元/月 | 约 66 元/月 |
| 3000 | 约 66 元/月 | 约 199 元/月 |
| 5000 | 约 111 元/月 | 约 332 元/月 |
| 10000 | 约 221 元/月 | 约 664 元/月 |

如果图片直接从你的服务器下载，峰值带宽大致为：

```text
所需带宽 Mbps = 峰值每秒下载图片数 × 7MB × 8
```

| 峰值下载 | 需要带宽 |
|---|---:|
| 同时 1 人下载 | 约 56 Mbps |
| 同时 5 人下载 | 约 280 Mbps |
| 同时 10 人下载 | 约 560 Mbps |
| 同时 20 人下载 | 约 1120 Mbps |

结论：`200M` 带宽不能承载多人同时下载 7MB 大图。保存上游 URL 或 Worker 转存 R2 后，应用服务器主要跑动态接口，带宽压力会小很多。

## 5. 方案 A：当前测试，现有 2C2G 200M

| 项目 | 配置 / 成本 | 链接 | 备注 |
|---|---:|---|---|
| 服务器 | 现有 `2C2G 200M` | 现有账单 | 不新增采购 |
| 图片模式 | 保存上游 URL | 上游 API 控制台 | 服务器不搬运 7MB 图片 |
| R2 | 可选，0-22 元/月 | [R2 Pricing](https://developers.cloudflare.com/r2/pricing/)、[R2 Calculator](https://r2-calculator.cloudflare.com/) | 日 1000 图、保留 1 个月约 22 元 |
| API | 日 300-1000 图，450-1500 元/月 | 用户指定 `0.05 元/张` | 最大成本项 |
| 邮箱 | 0-10 元/月 | [Resend Pricing](https://resend.com/pricing)、[SES Pricing](https://aws.amazon.com/ses/pricing/) | 验证码/通知 |
| DNS/SSL/防护 | 0 元起 | [Cloudflare Plans](https://www.cloudflare.com/plans/)、[Turnstile](https://www.cloudflare.com/products/turnstile/) | 域名已接 CF |

并发：

```text
Gunicorn workers = 2
HUISHI_GENERATION_WORKERS = 1-2
running 任务并发 = 2-4
4 分钟内前面最多排队 3-7 个任务
```

成本区间：

```text
保存上游 URL：约 450-1500 元/月 + 现有服务器费用
可选 R2：再加约 7-66 元/月，取决于图片量和保留周期
```

## 6. 方案 B：推荐商用，日本 4C8G

| 项目 | 配置 / 成本 | 链接 | 备注 |
|---|---:|---|---|
| VPS | 日本 4C8G，约 288-605 元/月 | [Vultr Pricing](https://www.vultr.com/pricing/)、[Akamai Cloud Pricing](https://www.akamai.com/cloud/pricing)、[Lightsail Pricing](https://aws.amazon.com/lightsail/pricing/) | 优先日本，其次美国西海岸 |
| 美国备选 | 4C8G，约 346 元/月起 | [DigitalOcean Droplets](https://www.digitalocean.com/pricing/droplets)、[Bandwidth Billing](https://docs.digitalocean.com/platform/billing/bandwidth/) | 美国西海岸可作备选 |
| PostgreSQL | 同机自建，0 元增量 | PostgreSQL 开源软件 | 4C8G 阶段不用急着拆 |
| Redis | 暂不上或同机轻量，0 元 | [Upstash Redis Pricing](https://upstash.com/pricing/redis) | 队列增长后再上 |
| 图片模式 | 默认保存上游 URL | 上游 API 控制台 | 成本最低 |
| Worker 转存 | 可选，Worker + R2 | [Workers Pricing](https://developers.cloudflare.com/workers/platform/pricing/)、[Use R2 from Workers](https://developers.cloudflare.com/r2/api/workers/workers-api-usage/) | 商用后建议异步转存 |
| R2 存储 | 日 1000-5000 图，保留 3 个月约 66-332 元/月 | [R2 Pricing](https://developers.cloudflare.com/r2/pricing/)、[R2 Calculator](https://r2-calculator.cloudflare.com/) | 只保存 URL 时为 0 |
| API | 日 1000-5000 图，1500-7500 元/月 | 用户指定 `0.05 元/张` | 最大成本项 |
| 邮箱 | 0-144 元/月 | [Resend Pricing](https://resend.com/pricing)、[SES Pricing](https://aws.amazon.com/ses/pricing/) | 量大可用 SES |
| DNS/SSL/安全 | 0 或 180 元/月 | [Cloudflare Plans](https://www.cloudflare.com/plans/)、[Turnstile](https://www.cloudflare.com/products/turnstile/) | Pro 可选 |
| 域名 | 约 6-15 元/月折算 | [Cloudflare Registrar](https://www.cloudflare.com/products/registrar/)、[Porkbun](https://porkbun.com/products/domains) | 按年付 |

并发：

```text
Gunicorn workers = 2
HUISHI_GENERATION_WORKERS = 4-6
running 任务并发 = 8-12
count=2 时图片并发 = 16-24 张
count=4 时图片并发 = 32-48 张
4 分钟内前面最多排队 15-23 个任务
```

成本区间：

| 日生成图片 | API 成本 | 保存 URL 总成本 | Worker 转存 R2 总成本 |
|---:|---:|---:|---:|
| 1000 | 1500 元 | 约 1800-2300 元 | 约 1900-2400 元 |
| 3000 | 4500 元 | 约 4800-5300 元 | 约 5000-5500 元 |
| 5000 | 7500 元 | 约 7800-8300 元 | 约 8150-8650 元 |

## 7. 方案 C：国内云厂商海外地域

适合需要中文支持、国内主体、发票或熟悉控制台的情况。日本优先，美国西海岸次选。

| 成本项 | 配置 / 成本 | 链接 | 备注 |
|---|---:|---|---|
| 阿里云国际 ECS | 4C8G 约 300-1000 元/月，需计算器核价 | [ECS Pricing](https://www.alibabacloud.com/en/product/ecs/pricing)、[ECS 价格列表](https://www.alibabacloud.com/zh/product/ecs-pricing-list/en) | 选择日本/美国地域 |
| 阿里云公网 | 按带宽/CDT/流量包 | [Internet Data Transfers](https://www.alibabacloud.com/help/en/cdt/internet-data-transfers/)、[ECS Public Bandwidth](https://www.alibabacloud.com/help/en/ecs/public-bandwidth) | 重点核算公网 |
| 腾讯云国际 CVM | 4C8G 需购买页核价 | [CVM Pricing](https://buy.tencentcloud.com/pricing/cvm?lang=en) | 选择日本/美国地域 |
| 腾讯云公网 | 按带宽、流量或带宽包 | [Public Network Billing](https://www.tencentcloud.com/document/product/213/10578)、[Bandwidth Package](https://intl.cloud.tencent.com/product/bwp) | 高流量建议带宽包 |
| 华为云国际 ECS | 需计算器核价 | [ECS Product](https://www.huaweicloud.com/intl/en-us/product/ecs.html)、[Pricing Calculator](https://www.huaweicloud.com/intl/en-us/pricing/calculator.html) | 企业采购友好 |
| UCloud Global | 需官网/控制台核价 | [UCloud Global Pricing](https://www.ucloud-global.com/price)、[UCloud 官网](https://www.ucloud.cn/) | 确认日本/美国可用区 |
| Worker 转存 R2 | 可选 | [Workers Pricing](https://developers.cloudflare.com/workers/platform/pricing/)、[R2 Pricing](https://developers.cloudflare.com/r2/pricing/) | 可避免服务器搬运图片 |

成本口径：

```text
只保存上游 URL：服务器公网流量较低，主要按实例 + 基础带宽算。
Worker 转存 R2：服务器仍不搬运 7MB 图片，成本转到 Worker/R2。
服务器本地转存：日 5000 图会产生约 1.03TB/月服务器图片出站，不建议。
```

估算：

| 日生成图片 | API 成本 | 保存 URL 总成本 | Worker 转存 R2 总成本 |
|---:|---:|---:|---:|
| 1000 | 1500 元 | 约 2000-3000 元 | 约 2100-3200 元 |
| 3000 | 4500 元 | 约 5000-6200 元 | 约 5200-6500 元 |
| 5000 | 7500 元 | 约 8000-9500+ 元 | 约 8400-10000+ 元 |

## 8. 方案 D：中型流量，Web + Worker 拆分

| 成本项 | 配置 / 成本 | 链接 | 备注 |
|---|---:|---|---|
| Web 服务器 | 4C8G | [Vultr Pricing](https://www.vultr.com/pricing/)、[DigitalOcean Droplets](https://www.digitalocean.com/pricing/droplets)、[Akamai Cloud Pricing](https://www.akamai.com/cloud/pricing) | 页面、登录、状态查询 |
| Worker 服务器 | 4C8G，或 Cloudflare Worker 转存 | [Workers Pricing](https://developers.cloudflare.com/workers/platform/pricing/) | 任务队列/图片转存 |
| PostgreSQL | 托管 PG 或独立 PG | [DO Managed Databases](https://www.digitalocean.com/pricing/managed-databases)、[Supabase Pricing](https://supabase.com/pricing)、[Aiven Pricing](https://aiven.io/pricing) | DAU 5000+ 后再拆 |
| Redis / 队列 | Upstash 或 DO Valkey | [Upstash Redis Pricing](https://upstash.com/pricing/redis)、[DO Managed Databases](https://www.digitalocean.com/pricing/managed-databases) | Celery/RQ/限流 |
| R2 | 1-6TB 级存储 | [R2 Pricing](https://developers.cloudflare.com/r2/pricing/)、[R2 Calculator](https://r2-calculator.cloudflare.com/) | 历史作品保留 |
| 邮箱 | SES / Resend | [SES Pricing](https://aws.amazon.com/ses/pricing/)、[Resend Pricing](https://resend.com/pricing) | 量大优先 SES |
| Cloudflare Pro/WAF | 可选 | [Cloudflare Plans](https://www.cloudflare.com/plans/) | 投放/被刷后再开 |

并发：

```text
running 任务并发 = 20-50
count=2 时图片并发 = 40-100 张
count=4 时图片并发 = 80-200 张
4 分钟内前面最多排队 39-99 个任务
```

成本区间：

| 日生成图片 | API 成本 | 保存 URL 总成本 | Worker 转存 R2 总成本 |
|---:|---:|---:|---:|
| 5000 | 7500 元 | 约 8200-12000 元 | 约 8600-12500 元 |
| 10000 | 15000 元 | 约 15700-20000 元 | 约 16500-21000 元 |
| 30000 | 45000 元 | 约 46000-50000+ 元 | 约 48000-53000+ 元 |

## 9. PostgreSQL 与拆分时机

4C8G 阶段 PostgreSQL 同机最合适：

| 阶段 | PG 建议 | 成本 |
|---|---|---:|
| 2C2G 测试 | 当前 SQLite 可测试，准备迁 PG | 0 |
| 4C8G 商用 | PostgreSQL 同机自建 | 0 元增量 |
| DAU 5000+ | 托管 PG 或独立 PG | 约 100-500+ 元/月 |

拆分触发点：

- 内存长期超过 75%。
- PG 查询、写入、锁等待影响应用。
- 数据库超过 20-50GB 且增长快。
- DAU 超过 5000-10000。
- 付费订单多，不能接受单机故障。

## 10. 最终执行清单

当前 2C2G：

```env
Gunicorn workers = 2
HUISHI_GENERATION_WORKERS=1 或 2
running 任务并发=2-4
MAX_GENERATION_COUNT=1 或 2
单用户同时 active 任务=1
```

商用 4C8G：

```env
Gunicorn workers = 2
HUISHI_GENERATION_WORKERS=4 到 6
running 任务并发=8-12
MAX_GENERATION_COUNT=1 起步，会员开放 2/4
单用户同时 active 任务=1
```

采购顺序：

1. 先继续用现有 `2C2G 200M`，保存上游 URL，限制任务并发。
2. 商用前买日本 `4C8G`，PG 同机，图片仍默认保存上游 URL。
3. 上 Turnstile、单用户任务限制、每日图片额度。
4. 商用稳定后用 Cloudflare Worker 异步转存 R2。
5. DAU 5000+ 或日生成 5000+ 后，拆 Web/Worker/PG/Redis。

最终判断：

```text
服务器不是主要成本，API 图片张数才是主要成本。
你现在不用买 GPU，也不用急着拆 PG。
大陆用户不备案：日本服务器优先，美国西海岸次选。
上游返回 URL 时，早期保存 URL 最省；商用后 Worker 转存 R2 更稳。
```
