from __future__ import annotations

import logging
import re

from flask import current_app, has_app_context
from openai import OpenAI, OpenAIError

from huishi.network import openai_http_client
from huishi.secrets import redact_url


logger = logging.getLogger(__name__)

STYLE_GUIDES = {
    "通用增强": "保留用户原意，从主体、场景、构图、光影、色彩、质感、镜头语言和细节层次补强。",
    "写实摄影": "优化为写实摄影提示词，强调镜头焦段、自然光影、景深、材质细节、真实色彩和摄影质感。",
    "插画二次元": "优化为插画或二次元风格提示词，强调角色设计、线条、色彩、构图节奏、氛围光和画面层次。",
    "商业设计": "优化为商业视觉设计提示词，强调产品主体、版式构图、背景控制、材质质感、灯光和可用性。",
    "电影感": "优化为电影画面提示词，强调镜头语言、光影反差、场景调度、色彩分级、构图和情绪张力。",
    "极简产品图": "优化为极简产品图提示词，强调主体清晰、背景克制、柔和布光、材质表现、留白和高级感。",
}


def optimize_prompt(
    *,
    prompt: str,
    style: str,
    api_key: str,
    base_url: str,
    model: str,
    proxy_url: str = "",
) -> str:
    if not prompt.strip():
        raise ValueError("提示词不能为空")
    if not api_key or not base_url or not model:
        raise ValueError("暂未启用 Prompt 优化")

    guide = STYLE_GUIDES.get(style, STYLE_GUIDES["通用增强"])
    request_model = normalize_prompt_model_name(model)
    messages = build_prompt_messages(prompt=prompt, style=style, guide=guide)
    timeout = float(current_app.config.get("PROMPT_API_TIMEOUT", 20)) if has_app_context() else 20.0
    http_client = openai_http_client(proxy_url, timeout=timeout)
    client_kwargs = {"api_key": api_key, "base_url": base_url, "timeout": timeout, "max_retries": 1}
    if http_client is not None:
        client_kwargs["http_client"] = http_client
    client = OpenAI(**client_kwargs)
    try:
        logger.info(
            "prompt optimization request started model=%s base_url=%s timeout=%ss",
            request_model,
            redact_url(base_url),
            timeout,
        )
        try:
            response = client.chat.completions.create(
                model=request_model,
                messages=messages,
                temperature=0.7,
            )
            return validate_optimized_prompt(prompt, extract_response_content(response), allow_html_retry=hasattr(client, "responses"))
        except OpenAIError:
            if not hasattr(client, "responses"):
                raise
        except PromptResponseRetry:
            if not hasattr(client, "responses"):
                raise RuntimeError("Prompt 优化接口返回了网页内容，请检查 Base URL 是否指向文本接口")

        response = client.responses.create(
            model=request_model,
            input=messages,
            temperature=0.7,
        )
        return validate_optimized_prompt(prompt, extract_response_content(response))
    finally:
        if http_client is not None:
            http_client.close()


class PromptResponseRetry(RuntimeError):
    pass


def validate_optimized_prompt(prompt: str, content: str, *, allow_html_retry: bool = False) -> str:
    optimized = (content or "").strip()
    if not optimized:
        raise RuntimeError("Prompt 优化接口没有返回内容")
    if looks_like_html(optimized):
        if allow_html_retry:
            raise PromptResponseRetry("Prompt 优化 chat 接口返回网页内容，尝试 Responses 接口")
        raise RuntimeError("Prompt 优化接口返回了网页内容，请检查 Base URL 是否指向文本接口")
    if looks_like_invalid_prompt_response(optimized):
        raise RuntimeError("Prompt 优化返回内容异常，请检查 Prompt Base URL、模型名和上游服务返回内容")
    if loses_core_prompt_terms(prompt, optimized):
        raise RuntimeError("Prompt 优化结果偏离原提示词，请重试或调整模型配置")
    return optimized


def normalize_prompt_model_name(model: str) -> str:
    normalized = (model or "").strip()
    if re.fullmatch(r"gpt\d+(?:\.\d+)+(?:-[A-Za-z0-9_.-]+)?", normalized):
        return f"gpt-{normalized.removeprefix('gpt')}"
    return normalized


def build_prompt_messages(*, prompt: str, style: str, guide: str) -> list[dict[str, str]]:
    direction = prompt_style_direction(style)
    return [
        {
            "role": "system",
            "content": (
                "你是专业 AI 生图提示词优化师。只根据用户原始输入进行优化，不新增与原意冲突的主体。"
                "把抽象或简短描述扩展成具体画面，必须写出可见的主体特征、所处环境、动作状态、镜头距离、光线来源、色彩关系和关键细节。"
                "不要复述优化要求，不要输出泛化模板词，不要机械堆叠高级感、高清、细节丰富等空泛质量词，不要重复用户已有描述。"
                "输出一段中文生图提示词，不要解释，不要 Markdown，不要编号。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户输入：{prompt}\n创作方向：{direction}\n"
                "请基于用户输入写成一段自然、具体、可直接生图的提示词；如果原文很短，请合理补充视觉上下文，但不要改变主体身份。"
            ),
        },
    ]


def prompt_style_direction(style: str) -> str:
    directions = {
        "写实摄影": "真实人像/物体摄影，强调自然可信的镜头、景深、肤色或材质表现",
        "插画二次元": "插画化角色与场景设计，强调线条、色块、造型节奏和氛围",
        "商业设计": "商业主视觉，强调主体识别、版式秩序、干净背景和可用于投放的完成度",
        "电影感": "电影剧照式画面，强调场景调度、情绪、镜头距离、明暗关系和色彩分级",
        "极简产品图": "克制的产品展示，强调留白、背景控制、轮廓、反光和材质边缘",
    }
    return directions.get(style, "通用生图增强，重点把用户的简短描述扩写成具体可见的画面")


def extract_response_content(response) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        output_text = response.get("output_text")
        if isinstance(output_text, str):
            return output_text
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            return _content_to_text((choices[0].get("message") or {}).get("content") if isinstance(choices[0], dict) else "")
        output = response.get("output")
        if isinstance(output, list):
            return _content_to_text(output)

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text
    choices = getattr(response, "choices", None)
    if choices:
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        if message is None and isinstance(first_choice, dict):
            message = first_choice.get("message")
        content = _get_value(message, "content") if message is not None else ""
        return _content_to_text(content)

    output = getattr(response, "output", None)
    if output:
        return _content_to_text(output)
    return ""


def _get_value(value, key: str):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
        nested = content.get("content")
        if nested is not None:
            return _content_to_text(nested)
        return ""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                    continue
                if isinstance(item.get("content"), list):
                    nested_text = _content_to_text(item["content"])
                    if nested_text:
                        parts.append(nested_text)
                    continue
            item_text = _get_value(item, "text")
            if isinstance(item_text, str):
                parts.append(item_text)
                continue
            item_content = _get_value(item, "content")
            if item_content is not None:
                nested_text = _content_to_text(item_content)
                if nested_text:
                    parts.append(nested_text)
        return "\n".join(part for part in parts if part)
    return ""


def looks_like_html(content: str) -> bool:
    text = content.lstrip().lower()
    return text.startswith("<!doctype html") or text.startswith("<html") or "<body" in text or "<head" in text


def looks_like_invalid_prompt_response(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return True
    if len(text) > 2000:
        return True
    if _looks_like_question_mark_corruption(text):
        return True
    if _looks_like_base64_blob(text):
        return True
    if _looks_like_json_dump(text):
        return True
    if "\ufffd" in text:
        return True
    return False


def loses_core_prompt_terms(prompt: str, optimized: str) -> bool:
    if "问号" not in prompt and ("问号" in optimized or "????" in optimized):
        return True
    source_terms = _core_cjk_terms(prompt)
    if not source_terms:
        return False
    preserved = sum(1 for term in source_terms if term in optimized)
    return preserved == 0


def _core_cjk_terms(text: str) -> list[str]:
    stop_terms = {"一个", "一位", "一名", "一张", "一幅", "一组", "柔和", "光线", "高清", "画面", "风格"}
    terms: list[str] = []
    for raw_term in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        term = raw_term
        for stop_term in stop_terms:
            if term.startswith(stop_term):
                term = term[len(stop_term):]
            elif term == stop_term:
                term = ""
        if len(term) < 2:
            continue
        candidates = [term]
        if len(term) > 4:
            candidates.extend(term[index : index + 4] for index in range(0, len(term) - 3))
        if len(term) > 3:
            candidates.extend(term[index : index + 3] for index in range(0, len(term) - 2))
        candidates.extend(term[index : index + 2] for index in range(0, len(term) - 1))
        for candidate in candidates:
            if candidate not in stop_terms and candidate not in terms:
                terms.append(candidate)
    return terms[:10]


def _looks_like_question_mark_corruption(text: str) -> bool:
    if "??" in text:
        return True
    question_marks = text.count("?") + text.count("？")
    return question_marks >= 3 and question_marks / max(len(text), 1) > 0.08


def _looks_like_base64_blob(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 256 or len(compact) % 4 != 0:
        return False
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", compact):
        return False
    return True


def _looks_like_json_dump(text: str) -> bool:
    lowered = text.lower()
    if not (lowered.startswith("{") or lowered.startswith("[")):
        return False
    suspicious_keys = (
        '"api_key"',
        '"base_url"',
        '"site_subtitle"',
        '"home_content"',
        '"hide_css_import"',
        '"content_info"',
    )
    return any(key in lowered for key in suspicious_keys)
