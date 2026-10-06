# 绘世

绘世是一个面向真实用户的 AI 图像创作网站，包含首页、生成工作台、参考素材栈、资产库、图片详情、用户积分和管理员计费配置。

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm install
python app.py
```

默认地址：http://127.0.0.1:8000

首次启动会自动初始化数据库。本地开发默认管理员用户名为 `admin`，默认密码为 `1qaz@WSX`；这个默认密码只用于本地调试，部署或共享环境必须在首次启动前设置 `HUISHI_ADMIN_PASSWORD` 覆盖。

## 必要环境变量

- `HUISHI_SECRET_KEY`：生产环境必须设置的 Flask 密钥。
- `HUISHI_ADMIN_PASSWORD`：初始管理员密码；不设置时仅本地开发使用默认密码，上线前必须设置为强密码。
- `API_KEY`：图片生成接口 Key。
- `BASE_URL`：OpenAI 兼容图片接口地址。
- `HUISHI_CANVAS_APP_URL`：画布应用地址，默认 `http://127.0.0.1:3000`。
- `HUISHI_DATABASE`：数据库路径，默认 `data/huishi.sqlite3`。
- `HUISHI_OUTPUT_DIR`：上传与生成图片目录，默认 `static/uploads`。
- `FLASK_DEBUG`：仅本地调试时设为 `1`，默认关闭。

## 邮件验证码 SMTP 配置

注册和忘记密码验证码通过 SMTP 发送。支持 `587 + STARTTLS` 和 `465 + SMTP_SSL`；未设置 `SMTP_SSL` 时，如果 `SMTP_PORT=465` 会自动使用 SSL。推荐管理员登录后在 `/settings` 的“邮件验证码”区域配置，配置会保存到数据库 `app_settings` 表；环境变量可作为备用默认值。

QQ 邮箱示例：

```powershell
$env:SMTP_HOST="smtp.qq.com"
$env:SMTP_PORT="465"
$env:SMTP_USER="1124346217@qq.com"
$env:SMTP_PASSWORD="QQ 邮箱授权码"
$env:SMTP_FROM="1124346217@qq.com"
$env:SMTP_SSL="1"
$env:SMTP_TLS="0"
```

`SMTP_PASSWORD` 请使用邮箱授权码，不要使用网页登录密码，也不要提交到仓库。

## 上线部署

上线前请至少完成：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run verify:home
Set-Location infinite-canvas\web
bun test
bun run typecheck
bun run build
```

`npm run verify:home` 会检查仓库 UTF-8 编码、重新生成压缩后的首页 JS/CSS，并验证首页资源预算与旧视频引用。Linux/VM 环境使用相同的 npm 命令即可。

## 编码约定

仓库文本文件统一使用 UTF-8。浏览器入口已经声明 UTF-8，Flask 静态资源和模板响应也应返回 `charset=utf-8`。

Windows PowerShell 下如遇中文输出或临时目录锁问题，建议使用：

```powershell
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp-full-serial
```

如果终端里的 `Get-Content` 或 `rg` 输出看起来像乱码，先运行 `npm run check:encoding` 或用浏览器响应头确认，不要直接把文件再次转码。

生产环境不要使用 Flask debug 模式；请通过 WSGI/反向代理或你的托管平台运行 `create_app()`。确保 `HUISHI_SECRET_KEY`、`API_KEY`、`BASE_URL` 和持久化数据库/上传目录已配置。
