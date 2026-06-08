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

首次启动会自动初始化数据库。如果没有设置 `HUISHI_ADMIN_PASSWORD`，系统会在控制台生成管理员密码，请妥善保存。

## 必要环境变量

- `HUISHI_SECRET_KEY`：生产环境必须设置的 Flask 密钥。
- `HUISHI_ADMIN_PASSWORD`：初始管理员密码，建议上线前设置。
- `API_KEY`：图片生成接口 Key。
- `BASE_URL`：OpenAI 兼容图片接口地址。
- `HUISHI_DATABASE`：数据库路径，默认 `data/huishi.sqlite3`。
- `HUISHI_OUTPUT_DIR`：上传与生成图片目录，默认 `static/uploads`。
- `FLASK_DEBUG`：仅本地调试时设为 `1`，默认关闭。

## 上线部署

上线前请至少完成：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test -- --run
npm run build
git diff --check
```

生产环境不要使用 Flask debug 模式；请通过 WSGI/反向代理或你的托管平台运行 `create_app()`。确保 `HUISHI_SECRET_KEY`、`API_KEY`、`BASE_URL` 和持久化数据库/上传目录已配置。
