"""提示词里的 @ 引用要翻成上游看得懂的编号说明。

背景：前端的 @ 插入的是一段**纯文本**（``@文件名``），它会随提示词原样
发到上游；而参考图是以"若干张图片"的形式附带的。上游拿到的是一句
"参考@abc.png" 加 N 张图，没有任何编号能把名字和图片对上——这个名字
对出图毫无作用。

这里钉住三件事：
1. 带 @ 且有参考图时，补一段编号说明；
2. 其它情况（没有 @、没有参考图）提示词一字不改，避免污染普通请求；
3. 编号取自**真实提交顺序**，不是提示词里 @ 的出现顺序——两者会不一致
   （提交顺序是"已有素材在前、新上传文件在后"）。
"""
from __future__ import annotations

from huishi.image_api import build_reference_preamble, reference_mention_labels


def test_preamble_is_added_when_prompt_references_images():
    text = build_reference_preamble("参考@产品图.png 换一个背景", ["产品图.png"])
    assert "参考图片共 1 张" in text
    assert "第1张=产品图.png" in text
    assert text.endswith("参考@产品图.png 换一个背景")


def test_preamble_lists_every_reference_in_submission_order():
    """列出全部参考图的位置——不只列被 @ 到的那些。

    落盘名会被 secure_filename 改写（中文名整段丢失），按名字反查位置不可靠；
    位置本身才是确定的。
    """
    names = ["甲.png", "乙.png", "丙.png"]
    text = build_reference_preamble("用@丙.png 的风格", names)
    assert "第1张=甲.png" in text
    assert "第2张=乙.png" in text
    assert "第3张=丙.png" in text


def test_prompt_without_mention_is_untouched():
    assert build_reference_preamble("一只猫", ["a.png"]) == "一只猫"


def test_references_without_names_do_not_inject_anything():
    """没有显示名时宁可不补，也不要编造编号。"""
    assert build_reference_preamble("参考@x.png", []) == "参考@x.png"
    assert build_reference_preamble("参考@x.png", None) == "参考@x.png"


def test_mention_extraction_deduplicates_and_keeps_order():
    labels = reference_mention_labels("@a.png 和 @b.png 还有 @a.png")
    assert labels == ["a.png", "b.png"]


def test_preamble_does_not_rewrite_the_original_prompt():
    """只加前缀，不改正文——正文是用户输入，存进记录也该是原样。"""
    original = "把@图1.png 里的人物换成红色衣服"
    text = build_reference_preamble(original, ["图1.png"])
    assert original in text
    assert text.index("参考图片共") < text.index(original)
