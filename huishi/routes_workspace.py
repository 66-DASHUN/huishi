from __future__ import annotations

import logging
import mimetypes
import re
import secrets
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from openai import APIError as OpenAIError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from huishi.auth import login_required
from huishi.billing import adjust_points, calculate_cost, require_balance
from huishi.db import get_db
from huishi.image_api import SIZE_MATRIX, generate_image, supports_size
from huishi.prompt_api import optimize_prompt
from huishi.records import (
    create_dialogue,
    create_record,
    dialogue_title_from_prompt,
    ensure_legacy_dialogue_for_user,
    get_dialogue_for_user,
    get_record_for_user,
    list_dialogues_for_user,
    list_records_for_dialogue,
    list_records_for_user,
    record_generation_seed,
)
from huishi.validation import (
    ValidationError,
    sanitize_filename,
    validate_generation_count,
    validate_http_url,
)

logger = logging.getLogger(__name__)

bp = Blueprint("workspace", __name__)
ALLOWED_MODES = {"text", "reference"}
ALLOWED_QUALITIES = {"auto", "high", "medium", "low"}
ALLOWED_OUTPUT_FORMATS = {"png", "jpeg", "webp"}


def _mask_key(key: str) -> str:
    visible = int(current_app.config.get("MASK_KEY_VISIBLE_CHARS", 4))
    if not key or len(key) < visible * 2:
        return ""
    return f"{key[:visible]}****{key[-visible:]}"


def _derive_resolution_labels():
    labels = set()
    for ratio_sizes in SIZE_MATRIX.values():
        labels.update(ratio_sizes.keys())
    return {k: k for k in sorted(labels)}


def _resolution_for_billing(resolution: str) -> str:
    """Map a WxH resolution string to a known preset label for pricing lookup.
    Returns the original string if no match found (admin should add a pricing rule)."""
    if not re.match(r"^\d+x\d+$", resolution):
        return resolution
    for ratio_sizes in SIZE_MATRIX.values():
        for label, size in ratio_sizes.items():
            if size == resolution:
                return label
    return resolution


@bp.get("/workspace")
@login_required
def workspace():
    ensure_legacy_dialogue_for_user(g.user["id"])
    get_db().commit()
    dialogues = list_dialogues_for_user(g.user["id"])
    is_new_creation = request.args.get("new") == "1"
    active_dialogue = None
    records = []
    raw_dialogue_id = request.args.get("dialogue", "").strip()
    if raw_dialogue_id and not is_new_creation:
        try:
            dialogue_id = int(raw_dialogue_id)
        except ValueError:
            abort(404)
        active_dialogue = get_dialogue_for_user(dialogue_id, g.user["id"])
        if active_dialogue is None:
            abort(404)
    elif dialogues and not is_new_creation:
        active_dialogue = dialogues[0]
    if active_dialogue is not None:
        records = list_records_for_dialogue(g.user["id"], active_dialogue["id"])
    current_record = None if is_new_creation else (records[0] if records else None)
    edit_seed = None
    raw_edit_record = request.args.get("edit_record", "").strip()
    if raw_edit_record:
        is_new_creation = False
        try:
            edit_record_id = int(raw_edit_record)
        except ValueError:
            abort(404)
        edit_record = get_record_for_user(edit_record_id, g.user["id"])
        if edit_record is None:
            abort(404)
        if edit_record.get("dialogue_id"):
            active_dialogue = get_dialogue_for_user(int(edit_record["dialogue_id"]), g.user["id"])
            records = list_records_for_dialogue(g.user["id"], int(edit_record["dialogue_id"]))
            current_record = records[0] if records else edit_record
        edit_seed = record_generation_seed(edit_record)
    return render_template(
        "workspace.html",
        records=records,
        dialogues=dialogues,
        active_dialogue=active_dialogue,
        current_record=current_record,
        edit_seed=edit_seed,
        is_new_creation=is_new_creation,
        size_matrix=SIZE_MATRIX,
        resolution_labels=_derive_resolution_labels(),
    )


@bp.get("/assets")
@login_required
def assets():
    records = list_records_for_user(g.user["id"])
    return render_template("assets.html", records=records)


@bp.route("/settings", methods=("GET", "POST"))
@login_required
def settings():
    if g.user["role"] != "admin":
        abort(403)
    db = get_db()
    settings_values = get_app_settings()
    if request.method == "POST":
        base_url = request.form.get("base_url", "").strip()
        if base_url:
            try:
                validate_http_url(base_url)
            except ValidationError as exc:
                return str(exc), 400
        posted_api_key = request.form.get("api_key", "").strip()
        api_key = posted_api_key or settings_values.get("image_api_key", "")
        prompt_base_url = request.form.get("prompt_base_url", "").strip()
        if prompt_base_url:
            try:
                validate_http_url(prompt_base_url)
            except ValidationError as exc:
                return str(exc), 400
        posted_prompt_api_key = request.form.get("prompt_api_key", "").strip()
        prompt_api_key = posted_prompt_api_key or settings_values.get("prompt_api_key", "")
        prompt_model = request.form.get("prompt_model", "").strip()
        save_app_setting("image_base_url", base_url)
        save_app_setting("image_api_key", api_key)
        save_app_setting("prompt_base_url", prompt_base_url)
        save_app_setting("prompt_api_key", prompt_api_key)
        save_app_setting("prompt_model", prompt_model)
        db.commit()
        flash("设置已保存")
        return redirect(url_for("workspace.settings"))
    settings_row = {
        "base_url": settings_values.get("image_base_url", ""),
        "api_key": settings_values.get("image_api_key", ""),
    }
    return render_template(
        "settings.html",
        settings=settings_row,
        app_settings=settings_values,
        default_base_url=current_app.config.get("DEFAULT_BASE_URL", ""),
        has_api_key=bool(settings_row["api_key"]),
        has_prompt_api_key=bool(settings_values.get("prompt_api_key", "")),
        masked_api_key=_mask_key(settings_row["api_key"]),
        masked_prompt_api_key=_mask_key(settings_values.get("prompt_api_key", "")),
    )


@bp.get("/api/estimate")
@login_required
def estimate():
    mode = request.args.get("mode", "text")
    width = request.args.get("width", "").strip()
    height = request.args.get("height", "").strip()
    if width and height:
        resolution = f"{width}x{height}"
        billing_resolution = _resolution_for_billing(resolution)
    else:
        resolution = request.args.get("resolution", "2560x1440")
        billing_resolution = _resolution_for_billing(resolution)
    try:
        count = parse_generation_count(request.args.get("count", "1"))
        cost = calculate_cost(mode, billing_resolution, count)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "cost": cost, "balance": g.user["points"]})


@bp.post("/api/prompt/optimize")
@login_required
def prompt_optimize():
    payload = request.get_json(silent=True) or {}
    prompt = str(payload.get("prompt", "")).strip()
    style = str(payload.get("style", "闁氨鏁ゆ晶鐐插繁")).strip() or "闁氨鏁ゆ晶鐐插繁"
    app_settings = get_app_settings()
    try:
        optimized = optimize_prompt(
            prompt=prompt,
            style=style,
            api_key=app_settings.get("prompt_api_key", ""),
            base_url=app_settings.get("prompt_base_url", ""),
            model=app_settings.get("prompt_model", ""),
        )
    except (ValueError, RuntimeError, OpenAIError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "optimized_prompt": optimized})


@bp.get("/assets/<int:record_id>")
@login_required
def asset_detail(record_id: int):
    record = get_record_for_user(record_id, g.user["id"], is_admin=g.user["role"] == "admin")
    if record is None:
        abort(404)
    next_url = request.args.get("next", "").strip()
    if next_url and not next_url.startswith("/"):
        next_url = ""
    source = request.args.get("from", "").strip()
    if next_url:
        if next_url.startswith("/workspace"):
            source = "workspace"
        elif next_url.startswith("/assets"):
            source = "assets"
    if source not in {"workspace", "assets"}:
        referrer = request.referrer or ""
        if "/workspace" in referrer:
            source = "workspace"
        elif "/assets" in referrer:
            source = "assets"
        else:
            source = "assets"
    return_url = next_url or (url_for("workspace.workspace") if source == "workspace" else url_for("workspace.assets"))
    return_label = "返回工作区" if source == "workspace" else "返回资产库"
    return render_template(
        "asset_detail.html",
        record=record,
        source=source,
        return_url=return_url,
        return_label=return_label,
        next_url=return_url,
    )


@bp.post("/assets/<int:record_id>/regenerate")
@login_required
def regenerate_asset(record_id: int):
    record = get_record_for_user(record_id, g.user["id"], is_admin=g.user["role"] == "admin")
    if record is None:
        abort(404)
    seed = record_generation_seed(record)
    reference_paths = seed["reference_paths"]
    reference_images = []
    if seed["mode"] == "reference" and not reference_paths:
        return generation_error("旧参考图作品需要回到工作台重新上传参考图后再生成", 400)

    if seed["mode"] == "reference":
        reference_images = load_reference_images(reference_paths)
        if not reference_images:
            return generation_error("参考图源文件不存在，请回到工作台重新上传后再生成", 400)

    try:
        count = int(seed["count"])
        billing_resolution = _resolution_for_billing(str(seed["resolution"]))
        cost = calculate_cost(str(seed["mode"]), billing_resolution, count)
        require_balance(g.user["id"], cost)
    except ValueError as exc:
        return generation_error(str(exc), 400)

    image_settings = get_app_settings("image_base_url", "image_api_key")
    try:
        result = generate_image(
            prompt=str(seed["prompt"]),
            mode=str(seed["mode"]),
            ratio=str(seed["ratio"]),
            resolution=str(seed["resolution"]),
            count=count,
            api_key=image_settings.get("image_api_key", ""),
            base_url=image_settings.get("image_base_url", ""),
            quality=str(seed["quality"]),
            output_format=str(seed["output_format"]),
            reference_images=reference_images,
        )
    except (ValueError, RuntimeError, OpenAIError) as exc:
        return generation_error(f"生成失败：{exc}", 502)

    new_record_id = _finalize_generation(
        user_id=g.user["id"],
        prompt=str(seed["prompt"]),
        mode=str(seed["mode"]),
        ratio=str(seed["ratio"]),
        resolution=str(seed["resolution"]),
        count=count,
        quality=str(seed["quality"]),
        output_format=str(seed["output_format"]),
        cost=cost,
        result=result,
        reference_paths=list(reference_paths),
    )
    new_record = get_record_for_user(new_record_id, g.user["id"])
    return jsonify({"ok": True, "record": serialize_record(new_record), "balance": g.user["points"] - cost})


@bp.post("/generate")
@login_required
def generate():
    if requires_email_verification():
        return generation_error("鐠囧嘲鍘涚€瑰本鍨氶柇顔绢唸妤犲矁鐦夐崥搴″晙閻㈢喐鍨氶崶鍓у", 403)
    prompt = request.form.get("prompt", "").strip()
    ratio = request.form.get("ratio", "16:9")
    quality = request.form.get("quality", "auto")
    output_format = request.form.get("output_format", "png")
    width_str = request.form.get("width", "").strip()
    height_str = request.form.get("height", "").strip()
    if width_str and height_str:
        try:
            width_val = int(width_str)
            height_val = int(height_str)
        except ValueError:
            return generation_error("Width and height must be valid numbers", 400)
        resolution = f"{width_val}x{height_val}"
    else:
        resolution = request.form.get("resolution", "2560x1440")
    billing_resolution = _resolution_for_billing(resolution)
    dialogue_id = parse_optional_int(request.form.get("dialogue_id"))
    uploaded_reference_images = [item for item in request.files.getlist("reference_images") if item and item.filename]
    existing_reference_paths = parse_reference_path_form_values()
    existing_reference_images = load_reference_images(existing_reference_paths)
    reference_images = [*existing_reference_images, *uploaded_reference_images]
    mode = "reference" if reference_images else "text"
    image_settings = get_app_settings("image_base_url", "image_api_key")
    api_key = image_settings.get("image_api_key", "")
    base_url = image_settings.get("image_base_url", "")
    try:
        count = parse_generation_count(request.form.get("count", "1"))
    except ValueError as exc:
        return generation_error(str(exc), 400)
    if not prompt:
        return generation_error("提示词不能为空", 400)
    if quality not in ALLOWED_QUALITIES:
        return generation_error("质量参数无效", 400)
    if output_format not in ALLOWED_OUTPUT_FORMATS:
        return generation_error("输出格式无效", 400)
    if not supports_size(ratio, resolution):
        return generation_error(f"{ratio} 不支持 {resolution}，请切换比例或清晰度", 400)
    max_ref = int(current_app.config.get("MAX_REFERENCE_IMAGES", 16))
    if len(reference_images) > max_ref:
        return generation_error(f"参考图最多支持 {max_ref} 张", 400)
    invalid_reference = next((item for item in uploaded_reference_images if not is_allowed_reference_image(item)), None)
    if invalid_reference is not None:
        return generation_error("閸欏倽鈧啫娴樻禒鍛暜閹?PNG閵嗕福PEG 閹?WEBP", 400)

    try:
        cost = calculate_cost(mode, billing_resolution, count)
        require_balance(g.user["id"], cost)
    except ValueError as exc:
        return generation_error(str(exc), 400)
    reference_paths = (
        [*existing_reference_paths, *save_reference_images(uploaded_reference_images)] if mode == "reference" else []
    )
    try:
        result = generate_image(
            prompt=prompt,
            mode=mode,
            ratio=ratio,
            resolution=resolution,
            count=count,
            api_key=api_key,
            base_url=base_url,
            quality=quality,
            output_format=output_format,
            reference_images=reference_images,
        )
    except (ValueError, RuntimeError, OpenAIError) as exc:
        return generation_error(f"生成失败：{exc}", 502)
    if dialogue_id is not None and get_dialogue_for_user(dialogue_id, g.user["id"]) is None:
        return generation_error("对话不存在，请新建对话后再生成", 404)
    if dialogue_id is None:
        dialogue_id = create_dialogue(user_id=g.user["id"], title=dialogue_title_from_prompt(prompt))
    record_id = _finalize_generation(
        user_id=g.user["id"],
        prompt=prompt,
        mode=mode,
        ratio=ratio,
        resolution=resolution,
        count=count,
        quality=quality,
        output_format=output_format,
        cost=cost,
        result=result,
        reference_paths=reference_paths,
        dialogue_id=dialogue_id,
    )
    record = get_record_for_user(record_id, g.user["id"])
    if wants_json():
        return jsonify({"ok": True, "record": serialize_record(record), "balance": g.user["points"] - cost})
    return redirect(url_for("workspace.workspace"))


def _finalize_generation(
    *,
    user_id: int,
    prompt: str,
    mode: str,
    ratio: str,
    resolution: str,
    count: int,
    quality: str,
    output_format: str,
    cost: int,
    result: dict,
    reference_paths: list,
    dialogue_id: int | None = None,
) -> int:
    """Create record, charge points, and commit. Returns new record_id."""
    record_id = create_record(
        user_id=user_id,
        dialogue_id=dialogue_id,
        prompt=prompt,
        image_path=str(result["image_path"]),
        mode=mode,
        ratio=ratio,
        resolution=resolution,
        actual_size=str(result["actual_size"]),
        quality=quality,
        output_format=output_format,
        count=count,
        model_source=str(result["model_source"]),
        elapsed_seconds=float(result["elapsed_seconds"]),
        points_charged=cost,
        reference_paths=reference_paths,
        image_paths=list(result.get("image_paths") or [result["image_path"]]),
    )
    adjust_points(user_id, -cost, "generation", record_id=record_id)
    get_db().commit()
    return record_id


def parse_generation_count(raw_count: str | None) -> int:
    max_gen = int(current_app.config.get("MAX_GENERATION_COUNT", 8))
    return validate_generation_count(raw_count, max_count=max_gen)


def parse_optional_int(raw_value: str | None) -> int | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_reference_path_form_values() -> list[str]:
    raw_values = request.form.getlist("reference_paths")
    paths = []
    for raw_value in raw_values:
        for item in str(raw_value or "").split(","):
            path = item.strip()
            if path and path.startswith("/static/uploads/") and path not in paths:
                paths.append(path)
    return paths


def get_app_settings(*keys: str) -> dict[str, str]:
    if not keys:
        rows = get_db().execute("SELECT key, value FROM app_settings").fetchall()
        return {row["key"]: row["value"] for row in rows}
    placeholders = ",".join("?" for _ in keys)
    rows = get_db().execute(f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})", keys).fetchall()
    return {row["key"]: row["value"] for row in rows}


def save_app_setting(key: str, value: str) -> None:
    get_db().execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
          value = excluded.value,
          updated_at = excluded.updated_at
        """,
        (key, value),
    )


def is_allowed_reference_image(file_storage: FileStorage) -> bool:
    """Check if file is an allowed reference image type."""
    try:
        from huishi.validation import validate_reference_image_file

        validate_reference_image_file(file_storage)
        return True
    except ValidationError:
        return False


def save_reference_images(reference_images: list[FileStorage]) -> list[str]:
    """Save validated reference images to disk.
    
    Args:
        reference_images: List of FileStorage objects
        
    Returns:
        List of saved image paths
        
    Raises:
        ValidationError: If any file fails validation
    """
    from huishi.validation import validate_reference_image_file
    
    output_dir: Path = current_app.config["OUTPUT_DIR"]
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[str] = []
    
    for file_storage in reference_images:
        # Validate before saving
        try:
            validate_reference_image_file(file_storage)
        except ValidationError as exc:
            logger.warning(f"Reference image validation failed: {exc}")
            raise ValueError(str(exc)) from exc
        
        # Sanitize filename
        original_name = sanitize_filename(file_storage.filename or "reference.png")
        original_path = Path(original_name)
        suffix = original_path.suffix.lower() or Path(file_storage.filename or "").suffix.lower()
        stem = original_path.stem or "reference"
        candidate = output_dir / f"ref_{stem}_{secrets.token_urlsafe(8)}{suffix}"
        
        while candidate.exists():
            candidate = output_dir / f"ref_{stem}_{secrets.token_urlsafe(8)}{suffix}"
        
        file_storage.stream.seek(0)
        file_storage.save(candidate)
        file_storage.stream.seek(0)
        
        logger.debug(f"Reference image saved: {candidate.name}")
        saved_paths.append(f"/static/uploads/{candidate.name}")
    
    return saved_paths


def load_reference_images(reference_paths) -> list[FileStorage]:
    output_dir = Path(current_app.config["OUTPUT_DIR"]).resolve()
    loaded: list[FileStorage] = []
    prefix = "/static/uploads/"
    for reference_path in reference_paths:
        if not isinstance(reference_path, str) or not reference_path.startswith(prefix):
            continue
        filename = Path(reference_path.removeprefix(prefix)).name
        if not filename:
            continue
        local_path = (output_dir / filename).resolve()
        if output_dir not in local_path.parents or not local_path.is_file():
            continue
        mimetype = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        loaded.append(
            FileStorage(
                stream=BytesIO(local_path.read_bytes()),
                filename=local_path.name,
                content_type=mimetype,
            )
        )
    return loaded


def wants_json() -> bool:
    return request.headers.get("X-Requested-With") == "fetch" or "application/json" in request.accept_mimetypes


def requires_email_verification() -> bool:
    return bool(g.user["email"]) and g.user["role"] != "admin" and int(g.user["email_verified"]) != 1


def generation_error(message: str, status_code: int):
    if wants_json():
        return jsonify({"ok": False, "error": message}), status_code
    return message, status_code


def serialize_record(record) -> dict[str, object]:
    return {
        "id": record["id"],
        "dialogue_id": record.get("dialogue_id"),
        "prompt": record["prompt"],
        "image_path": record["image_path"],
        "images": record["image_paths"],
        "mode": record["mode"],
        "ratio": record["ratio"],
        "resolution": record["resolution"],
        "actual_size": record["actual_size"],
        "quality": record["quality"],
        "output_format": record["output_format"],
        "count": record["count"],
        "model_source": record["model_source"],
        "elapsed_seconds": record["elapsed_seconds"],
        "points_charged": record["points_charged"],
        "reference_paths": record["reference_paths"],
        "favorite": record["favorite"],
        "created_at": record["created_at"],
    }


def parse_asset_ids() -> list[int]:
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("ids", [])
    ids: list[int] = []
    for raw_id in raw_ids:
        try:
            ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    return sorted(set(ids))


@bp.post("/assets/bulk/favorite")
@login_required
def bulk_favorite_assets():
    ids = parse_asset_ids()
    payload = request.get_json(silent=True) or {}
    favorite = 1 if payload.get("favorite") else 0
    if not ids:
        return jsonify({"ok": False, "error": "鐠囩兘鈧瀚ㄧ挧鍕獓"}), 400
    placeholders = ",".join("?" for _ in ids)
    cursor = get_db().execute(
        f"UPDATE records SET favorite = ? WHERE id IN ({placeholders}) AND user_id = ?",
        [favorite, *ids, g.user["id"]],
    )
    get_db().commit()
    return jsonify({"ok": True, "updated": cursor.rowcount})


@bp.post("/assets/bulk/delete")
@login_required
def bulk_delete_assets():
    ids = parse_asset_ids()
    if not ids:
        return jsonify({"ok": False, "error": "鐠囩兘鈧瀚ㄧ挧鍕獓"}), 400
    placeholders = ",".join("?" for _ in ids)
    cursor = get_db().execute(
        f"UPDATE records SET hidden = 1 WHERE id IN ({placeholders}) AND user_id = ?",
        [*ids, g.user["id"]],
    )
    get_db().commit()
    return jsonify({"ok": True, "deleted": cursor.rowcount})


@bp.post("/assets/bulk/download")
@login_required
def bulk_download_assets():
    ids = parse_asset_ids()
    if not ids:
        return jsonify({"ok": False, "error": "鐠囩兘鈧瀚ㄧ挧鍕獓"}), 400
    placeholders = ",".join("?" for _ in ids)
    records = get_db().execute(
        f"SELECT * FROM records WHERE id IN ({placeholders}) AND user_id = ? ORDER BY id",
        [*ids, g.user["id"]],
    ).fetchall()

    output_dir = Path(current_app.config["OUTPUT_DIR"]).resolve()
    memory = BytesIO()
    with ZipFile(memory, "w", ZIP_DEFLATED) as archive:
        for record in records:
            image_path = str(record["image_path"])
            if not image_path.startswith("/static/uploads/"):
                continue
            local_name = Path(image_path.removeprefix("/static/uploads/")).name
            if not local_name:
                continue
            local_path = (output_dir / local_name).resolve()
            if output_dir in local_path.parents and local_path.exists():
                archive.write(local_path, arcname=local_name)
    memory.seek(0)
    return send_file(
        memory,
        mimetype="application/zip",
        as_attachment=True,
        download_name="huishi-assets.zip",
    )


@bp.post("/assets/<int:record_id>/favorite")
@login_required
def toggle_favorite(record_id: int):
    record = get_record_for_user(record_id, g.user["id"], is_admin=g.user["role"] == "admin")
    if record is None:
        abort(404)
    next_value = 0 if record["favorite"] else 1
    get_db().execute("UPDATE records SET favorite = ? WHERE id = ?", (next_value, record_id))
    get_db().commit()
    if wants_json():
        return jsonify({"ok": True, "favorite": next_value})
    next_url = request.form.get("next", "").strip()
    if next_url and next_url.startswith("/"):
        return redirect(url_for("workspace.asset_detail", record_id=record_id, next=next_url))
    source = request.form.get("from", "").strip()
    if source in {"workspace", "assets"}:
        return redirect(url_for("workspace.asset_detail", record_id=record_id, **{"from": source}))
    return redirect(url_for("workspace.asset_detail", record_id=record_id))


@bp.post("/assets/<int:record_id>/delete")
@login_required
def delete_record(record_id: int):
    record = get_record_for_user(record_id, g.user["id"], is_admin=g.user["role"] == "admin")
    if record is None:
        abort(404)
    get_db().execute("UPDATE records SET hidden = 1 WHERE id = ?", (record_id,))
    get_db().commit()
    if wants_json():
        return jsonify({"ok": True})
    next_url = request.form.get("next", "").strip()
    if next_url and next_url.startswith(("/workspace", "/assets")):
        return redirect(next_url)
    source = request.form.get("from", "").strip()
    if source == "workspace":
        return redirect(url_for("workspace.workspace"))
    return redirect(url_for("workspace.assets"))


def delete_local_upload(image_path: str) -> None:
    prefix = "/static/uploads/"
    if not image_path.startswith(prefix):
        return
    filename = Path(image_path.removeprefix(prefix)).name
    if not filename:
        return
    output_dir = Path(current_app.config["OUTPUT_DIR"]).resolve()
    target = (output_dir / filename).resolve()
    if output_dir not in target.parents or not target.is_file():
        return
    target.unlink()


