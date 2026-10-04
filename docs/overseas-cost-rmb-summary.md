# AI 生图网站国外部署成本与并发汇总

评估口径：
- 生图 API：`0.05 元/张`
- 不计算提示词优化成本
- 域名已接 Cloudflare
- 价格统一换算成人民币
- 汇率按粗略口径：`1 USD ≈ 7.2 RMB`，`1 EUR ≈ 7.8 RMB`

## 1. 先说结论

你的项目不是自建模型推理，而是：

```text
用户 -> 网站服务器 -> 上游生图 API -> 保存图片 -> 用户查看/下载
```

所以真正的大头不是服务器，而是生图 API。

如果你想做早期商用，最稳的起步方式是：

```text
海外 4C8G 服务器
网站 + PostgreSQL 同机
图片放 Cloudflare R2
Cloudflare DNS / SSL / Turnstile
邮箱先用 Resend Free 或 Amazon SES
```

这个阶段，**PG 同机是合理的**。  
等到 DAU、数据库体积、故障隔离要求上来，再拆 PG 和 Redis。

## 2. 每项成本来源

### 2.1 服务器

| 规格 | 人民币/月 | 来源链接 |
|---|---:|---|
| 2 vCPU / 4GB | 约 43 元（Hetzner CX23，EUR 口径） | [Hetzner Cloud 价格调整](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/) |
| 2 vCPU / 4GB | 约 173 元（DigitalOcean） | [DigitalOcean Droplets](https://www.digitalocean.com/pricing/droplets) |
| 2 vCPU / 4GB | 约 288 元（AWS Lightsail） | [AWS Lightsail Pricing](https://aws.amazon.com/lightsail/pricing/) |
| 4 vCPU / 8GB | 约 66 元（Hetzner CX33，EUR 口径） | [Hetzner Cloud 价格调整](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/) |
| 4 vCPU / 8GB | 约 346 元（DigitalOcean） | [DigitalOcean Droplets](https://www.digitalocean.com/pricing/droplets) |
| 4 vCPU / 8GB | 约 576 元（AWS Lightsail） | [AWS Lightsail Pricing](https://aws.amazon.com/lightsail/pricing/) |

### 2.2 PostgreSQL

| 方案 | 人民币/月 | 来源链接 |
|---|---:|---|
| 自建，同机 | 0 元 | 你的当前架构 |
| Aiven Developer Tier | 约 36 元起 | [Aiven PostgreSQL](https://aiven.io/postgresql) |
| DigitalOcean 托管 PG 1GB | 约 108 元起 | [DigitalOcean Managed Databases](https://www.digitalocean.com/pricing/managed-databases) |
| Supabase Pro | 约 180 元起 | [Supabase Pricing](https://supabase.com/pricing) |

### 2.3 Redis / 队列

| 方案 | 人民币/月 | 来源链接 |
|---|---:|---|
| 不单独上 Redis | 0 元 | 早期可用本机线程池 |
| Upstash Free | 0 元 | [Upstash Redis](https://upstash.com/pricing/redis) |
| Upstash Pay as You Go | 约 1.44 元 / 10 万命令 | [Upstash Redis](https://upstash.com/pricing/redis) |
| DigitalOcean Valkey 1GB | 约 108 元 | [DO Valkey](https://www.digitalocean.com/products/managed-databases-valkey) |

### 2.4 图片存储与流量

| 方案 | 人民币/月 | 说明 | 来源链接 |
|---|---:|---|---|
| Cloudflare R2 | 0.108 元 / GB-月 | 10GB 免费；egress 免费 | [Cloudflare R2](https://developers.cloudflare.com/r2/pricing/) |
| Hetzner Object Storage | 约 39 元起 | 含 1TB 存储 + 1TB egress | [Hetzner Object Storage](https://www.hetzner.com/pressroom/object-storage/) |
| AWS S3 | 约 0.166 元 / GB-月 | 存储本身不贵，但外网流量更贵 | [AWS S3 Pricing](https://aws.amazon.com/s3/pricing/) |

### 2.5 DNS / 域名

| 方案 | 人民币/月 | 说明 | 来源链接 |
|---|---:|---|---|
| Cloudflare DNS | 0 元 | 免费 DNS | [Cloudflare Plans](https://www.cloudflare.com/plans/) |
| AWS Route 53 | 约 3.6 元 / zone / 月 | 仅 DNS 托管费 | [Route 53 Pricing](https://aws.amazon.com/route53/pricing/) |
| Cloudflare Registrar | 接近成本价 | 无额外加价 | [Cloudflare Registrar](https://www.cloudflare.com/products/registrar/) |
| Porkbun `.com` | 约 6.7 元 / 月 | `.com` 年费 $11.08 | [Porkbun Domains](https://porkbun.com/products/domains) |

### 2.6 邮箱

| 方案 | 人民币/月 | 说明 | 来源链接 |
|---|---:|---|---|
| Resend Free | 0 元 | 每月 3000 封 | [Resend Pricing](https://resend.com/pricing) |
| Resend Pro | 约 144 元 | 5 万封/月起 | [Resend Pricing](https://resend.com/pricing) |
| Amazon SES | 约 0.72 元 / 1000 封 | 只算发信，不含附件和额外流量 | [Amazon SES Pricing](https://aws.amazon.com/ses/pricing/) |

### 2.7 安全 / 防刷

| 方案 | 人民币/月 | 说明 | 来源链接 |
|---|---:|---|---|
| Cloudflare Free + Turnstile | 0 元 | Turnstile 免费 | [Turnstile](https://www.cloudflare.com/products/turnstile/) |
| Cloudflare Pro | 约 180 元 | 每域名每月 | [Cloudflare Plans](https://www.cloudflare.com/plans/) |

### 2.8 生图 API

| 口径 | 人民币/月 |
|---|---:|
| `0.05 元/张` | `日生成张数 × 30 × 0.05` |

## 3. 三档方案

### 方案一：低成本内测

适合：

```text
100-1000 DAU
日生成 300-1000 张
```

建议组合：

```text
2C4G 海外服务器
网站 + PostgreSQL 同机
Cloudflare Free
R2 存图
Resend Free / SES
```

固定成本大致：

| 项目 | 人民币/月 |
|---|---:|
| 服务器 | 43-288 |
| PG | 0 |
| Redis | 0-11 |
| 存储 | 0-20 |
| DNS / SSL / 防刷 | 0 |
| 邮箱 | 0-10 |
| 域名折算 | 6-8 |
| 备份 / 监控 | 0-20 |
| **固定成本合计** | **约 50-357** |

加上 API：

| 日生成 | API 成本 | 总成本 |
|---:|---:|---:|
| 300 | 450 | 约 500-807 |
| 1000 | 1500 | 约 1550-1857 |

### 方案二：推荐商用起步

适合：

```text
1000-5000 DAU
日生成 1000-5000 张
```

建议组合：

```text
4C8G 海外服务器
网站 + PostgreSQL 同机
可选同机 Redis
Cloudflare Free 或 Pro
R2 存图
Resend Free / Pro
```

固定成本大致：

| 项目 | 人民币/月 |
|---|---:|
| 服务器 | 66-576 |
| PG | 0 |
| Redis | 0-108 |
| 存储 | 6-63 |
| DNS / SSL / 防刷 | 0 或 180 |
| 邮箱 | 0-144 |
| 域名折算 | 6-8 |
| 备份 / 监控 | 10-50 |
| **固定成本合计** | **约 88-1,137** |

加上 API：

| 日生成 | API 成本 | 总成本 |
|---:|---:|---:|
| 1000 | 1500 | 约 1,588-2,637 |
| 3000 | 4500 | 约 4,588-5,637 |
| 5000 | 7500 | 约 7,588-8,637 |

### 方案三：增长稳定版

适合：

```text
5000-15000+ DAU
日生成 5000-30000 张
```

建议组合：

```text
Web 服务器 + Worker 服务器分离
托管 PostgreSQL
托管 Redis
Cloudflare Pro
R2
Resend Pro / SES
```

固定成本大致：

| 项目 | 人民币/月 |
|---|---:|
| Web + Worker | 132-1152 |
| 托管 PG | 36-180 |
| 托管 Redis | 0-108 |
| 存储 | 19-188 |
| DNS / SSL / 防刷 | 0 或 180 |
| 邮箱 | 0-144 |
| 域名折算 | 6-8 |
| 备份 / 监控 | 50-200 |
| **固定成本合计** | **约 243-2,160** |

加上 API：

| 日生成 | API 成本 | 总成本 |
|---:|---:|---:|
| 5000 | 7500 | 约 7,743-9,660 |
| 10000 | 15000 | 约 15,243-17,160 |
| 30000 | 45000 | 约 45,243-47,160 |

## 4. 一起生成的并发

这块最容易混。

### 4.1 公式

```text
总生成任务并发 = Gunicorn worker 数 × HUISHI_GENERATION_WORKERS
同时生成图片数 ≈ 总生成任务并发 × count
```

因为你的代码里每个 Gunicorn 进程都会创建自己的 `ThreadPoolExecutor`。

### 4.2 例子

如果你是：

```text
gunicorn -w 2
HUISHI_GENERATION_WORKERS=4
count=4
```

那么：

```text
总生成任务并发 = 2 × 4 = 8
同时生成图片数 ≈ 8 × 4 = 32
```

### 4.3 推荐并发

| 机器 | 推荐总任务并发 | 适合状态 |
|---|---:|---|
| 2C4G | 4-6 | 内测 / 小流量 |
| 4C8G | 8-12 | 早期商用 |
| 4C8G + 独立 Worker | 12-20 | 稳定增长 |

### 4.4 等待时间

假设单任务平均 60 秒：

| 总任务并发 | 前面 10 个任务 | 前面 50 个任务 |
|---|---:|---:|
| 4 | 约 3 分钟 | 约 11 分钟 |
| 8 | 约 2 分钟 | 约 6 分钟 |
| 12 | 约 1.5 分钟 | 约 4 分钟 |

## 5. 最后建议

如果你现在就要落地，优先选：

```text
海外 4C8G
网站 + PostgreSQL 同机
Cloudflare DNS / SSL / Turnstile
Cloudflare R2 存图
Resend Free 或 SES
```

这个方案的优点是：

- 成本不高
- PG 同机足够早期商用
- 图片流量几乎不成为大头
- 真正要控的是 API 成本、免费额度、并发和防刷

如果你愿意，我可以继续把这份总结压成一页更短的决策表。
