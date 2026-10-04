from __future__ import annotations

import json
from pathlib import Path


def test_home_build_uses_production_minification():
    package = json.loads(Path("package.json").read_text(encoding="utf-8"))
    command = package["scripts"]["build:home:js"]
    source = Path("tools/build_home_js.mjs").read_text(encoding="utf-8")

    assert command == "node tools/build_home_js.mjs"
    assert "minify: true" in source
    assert '"process.env.NODE_ENV"' in source
    assert "production" in source


def test_python_scripts_use_cross_platform_runner():
    package = json.loads(Path("package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["test"].startswith("node tools/run_python.mjs ")
    assert package["scripts"]["check:encoding"].startswith("node tools/run_python.mjs ")
    assert package["scripts"]["check:assets"].startswith("node tools/run_python.mjs ")

    source = Path("tools/run_python.mjs").read_text(encoding="utf-8")
    assert "process.env.HUISHI_PYTHON" in source
    assert ".venv/bin/python" in source
    assert ".venv/Scripts/python.exe" in source
    assert '"python3"' in source
    assert '"python"' in source
