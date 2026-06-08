from __future__ import annotations

from openai import OpenAI


STYLE_GUIDES = {
    "通用增强": "保留原意，补充主体、环境、构图、光线、质感和风格细节。",
    "写实摄影": "优化为写实摄影提示词，强调镜头、光线、景深、材质和真实感。",
    "插画二次元": "优化为插画或二次元风格提示词，强调角色、线条、色彩和画面氛围。",
    "商业设计": "优化为商业视觉设计提示词，强调产品、版式、背景、质感和可用性。",
    "电影感": "优化为电影画面提示词，强调镜头语言、光影、场景调度和情绪。",
    "极简产品图": "优化为极简产品图提示词，强调主体清晰、背景克制、材质和留白。",
}


def optimize_prompt(
    *,
    prompt: str,
    style: str,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    if not prompt.strip():
        raise ValueError("提示词不能为空")
    if not api_key or not base_url or not model:
        raise ValueError("暂未启用 Prompt 优化")

    guide = STYLE_GUIDES.get(style, STYLE_GUIDES["通用增强"])
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你是 AI 生图提示词优化助手。只输出优化后的提示词，不解释。",
            },
            {
                "role": "user",
                "content": f"优化风格：{style}\n优化要求：{guide}\n原提示词：{prompt}",
            },
        ],
        temperature=0.7,
    )
    content = extract_response_content(response)
    optimized = (content or "").strip()
    if not optimized:
        raise RuntimeError("Prompt 优化接口没有返回内容")
    return optimized


def extract_response_content(response) -> str:
    if isinstance(response, str):
        return response
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    content = getattr(message, "content", "") if message is not None else ""
    return content or ""
