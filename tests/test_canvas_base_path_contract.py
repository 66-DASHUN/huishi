"""画布挂载到主站同域子路径的契约。

这组断言来自一次真实的部署风险排查：把画布从「独立域名+端口」改成
「主站同域子路径」时，有三个地方必须同时正确，任何一个漏改都是**静默**
出错——服务照常起来、页面照常返回 200，只是功能悄悄坏掉：

1. **构建参数**：Next 的 basePath 是编译期概念。构建时不传，运行期改不了，
   于是资源路径不带前缀，Nginx 转发后全部 404。
2. **健康探针**：加了前缀后根路径是 404。探针若仍探 `/`，容器会被判为
   unhealthy，而服务其实完全正常——这是最难查的一类「误报故障」。
3. **应用内绝对路径**：Next 只自动给 `_next/*` 和 `<Link>` 加前缀，
   `router.push("/canvas/1")`、`fetch("/webdav-proxy")` 这类手写路径不会。
   漏了就会跳到主站根路径去。
"""
from pathlib import Path

BASE_PATH = "/canvas-app"


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_canvas_build_arg_and_mount_prefix_agree():
    """compose 传入的前缀、Dockerfile 声明的参数、探针路径必须一致。

    探针与前缀脱钩是这里最值钱的一条：它不会让服务挂掉，只会让编排系统
    永远认为它没起来。
    """
    compose = read("compose.prod.yml")
    dockerfile = read("infinite-canvas/Dockerfile.huishi")

    assert f"CANVAS_BASE_PATH: {BASE_PATH}" in compose, "compose 未传入挂载前缀"
    assert "ARG CANVAS_BASE_PATH=" in dockerfile, "Dockerfile 未声明构建参数"
    assert "ENV CANVAS_BASE_PATH=${CANVAS_BASE_PATH}" in dockerfile, "构建参数未生效"
    # 探针必须探带前缀的路径
    assert f"3000{BASE_PATH}/" in compose, "healthcheck 未跟着前缀改，会误报 unhealthy"
    assert "fetch('http://127.0.0.1:3000/')" not in compose, "healthcheck 仍探根路径"


def test_canvas_base_path_helper_guards_foreign_urls():
    """前缀工具只处理应用内绝对路径，别把外链改坏。

    这段逻辑在客户端 bundle 里跑，改错了会影响所有导航与外链。用真实构建
    出的 chunk 验证不现实（需要 Next 构建），所以这里用等价的边界清单约束
    源码行为意图，真正的执行验证见 tests/check_canvas_base_path.cjs。
    """
    source = read("infinite-canvas/web/src/lib/app-path.ts")

    # 空配置必须退化为恒等，否则独立域名部署会被加上莫名前缀
    assert 'const RAW_BASE_PATH = process.env.NEXT_PUBLIC_CANVAS_BASE_PATH || "";' in source
    assert "if (!APP_BASE_PATH) return path;" in source
    # 外链、协议相对地址不处理
    assert 'if (!path.startsWith("/") || path.startsWith("//")) return path;' in source
    # 幂等：已经带前缀的不重复添加
    assert "if (path.startsWith(`${APP_BASE_PATH}/`)) return path;" in source


def test_canvas_internal_paths_go_through_the_helper():
    """应用内绝对路径必须走 helper，而不是裸字符串。

    Next 自动加前缀的范围仅限 `_next/*` 静态资源与 `<Link>`/router 的
    导航目标；`router.push` 的目标、`fetch` 的地址、原生 `<img src>` 都要自己带。
    """
    root = Path("infinite-canvas/web/src")

    offenders: list[str] = []
    for path in root.rglob("*.ts*"):
        if path.suffix == ".test.ts" or ".test." in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            # router.push/replace 的裸绝对路径
            for call in ("router.push(", "router.replace("):
                if call in line and "withBasePath" not in line:
                    if call + '"/' in line or call + "`/" in line:
                        offenders.append(f"{path}:{line_no} {stripped[:90]}")
            # fetch 的裸绝对路径
            if 'fetch("/' in line and "withBasePath" not in line:
                offenders.append(f"{path}:{line_no} {stripped[:90]}")

    assert not offenders, "以下路径未加挂载前缀，子路径部署下会失效：\n" + "\n".join(offenders)
