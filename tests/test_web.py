"""Parsing ordinary web pages (notekit.sources.web), using synthetic pages."""

from __future__ import annotations

import json

import pytest

from notekit import net
from notekit.sources import web

URL = "https://food.example.com/recipes/fanqie?utm_source=share&id=7#comments"

RECIPE_JSONLD = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebSite", "name": "美食网"},
        {
            "@type": "Recipe",
            "name": "家常番茄炒蛋",
            "author": {"@type": "Person", "name": "厨房小王"},
            "datePublished": "2026-08-01T10:00:00+08:00",
            "recipeYield": "2 人份",
            "totalTime": "PT10M",
            "recipeIngredient": ["番茄 2 个", "鸡蛋 3 个", "盐 2g"],
            "recipeInstructions": [
                {"@type": "HowToSection", "name": "准备", "itemListElement": [{"@type": "HowToStep", "text": "番茄切块"}]},
                {"@type": "HowToStep", "text": "鸡蛋炒熟盛出"},
            ],
        },
    ],
}


def article_page(jsonld: object = RECIPE_JSONLD, head_extra: str = "", body_extra: str = "") -> str:
    script = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>番茄炒蛋的做法 - 美食网</title>
<meta property="og:title" content="家常番茄炒蛋">
<meta property="og:site_name" content="美食网">
<meta property="og:image" content="https://cdn.example.com/cover.jpg">
{script}{head_extra}</head><body>
<nav><a href="/">首页</a> <a href="/hot">热门菜谱</a> <a href="/login">登录</a></nav>
<article><h1>家常番茄炒蛋</h1>
<p>番茄炒蛋是最家常的一道菜，十分钟就能做好。下面是详细做法，按照步骤做，新手也能成功。</p>
<img src="/img/step1.jpg" width="800" height="600" alt="切好的番茄">
<h2>配料</h2><ul><li>番茄 2 个</li><li>鸡蛋 3 个</li><li>盐 2g</li></ul>
<h2>做法</h2><ol><li>番茄切块，鸡蛋打散。</li><li>热锅下油，鸡蛋炒熟盛出。</li><li>番茄炒出汁后倒回鸡蛋，加盐出锅。</li></ol>
<img src="https://cdn.example.com/step2.jpg" width="800" height="600" alt="出锅">
<img src="/icons/logo.svg" alt="logo">
<p>小贴士：番茄选熟透的，出汁更多，味道更浓。做好以后趁热吃，口感最好。</p>
{body_extra}
</article>
<aside><h3>猜你喜欢</h3><ul><li><a href="/r/1">红烧肉</a></li><li><a href="/r/2">可乐鸡翅</a></li></ul></aside>
<footer>© 2026 美食网 京ICP备00000000号 联系我们 隐私政策</footer>
</body></html>"""


def test_main_text_keeps_the_article_and_drops_navigation_and_footer():
    page = web.page_from_html(URL, article_page())
    assert "番茄炒出汁后倒回鸡蛋" in page.text
    assert "小贴士" in page.text
    for noise in ("猜你喜欢", "红烧肉", "ICP", "登录", "热门菜谱"):
        assert noise not in page.text, noise


def test_metadata_with_author_from_jsonld():
    page = web.page_from_html(URL, article_page())
    assert page.title == "家常番茄炒蛋"
    assert page.author == "厨房小王", "trafilatura finds no author here; JSON-LD supplies it"
    assert page.published_at == "2026-08-01"
    assert page.site_name == "美食网"


def test_author_from_meta_tag_when_there_is_no_jsonld():
    page = web.page_from_html(URL, article_page(jsonld=None, head_extra='<meta name="author" content="张三">'))
    assert page.author == "张三"


def test_content_images_are_absolute_ordered_and_skip_svg():
    page = web.page_from_html(URL, article_page())
    assert [url for url, _ in page.images] == [
        "https://food.example.com/img/step1.jpg",
        "https://cdn.example.com/step2.jpg",
    ]
    assert page.images[0][1] == "切好的番茄"


def test_cover_image_is_recorded_but_not_downloaded():
    """og:image is usually a generated preview of the title; OCR on it would repeat the text at full cost."""
    html = "<html><head><title>短文</title><meta property='og:image' content='/cover.png'></head><body><article><p>" + "正文内容。" * 60 + "</p></article></body></html>"
    page = web.page_from_html("https://a.example.com/post/1", html)
    assert page.images == []
    assert page.cover_image == "https://a.example.com/cover.png"


def test_structured_recipe_summary_lists_ingredients_and_steps():
    page = web.page_from_html(URL, article_page())
    summary = web.structured_summary(page.structured)
    assert "菜谱：家常番茄炒蛋" in summary
    assert "份量：2 人份" in summary
    assert "- 鸡蛋 3 个" in summary
    assert "1. 准备：番茄切块" in summary
    assert "2. 鸡蛋炒熟盛出" in summary
    assert "WebSite" not in {kind for node in page.structured for kind in web.types_of(node)}, "only relevant types are kept"


def test_jsonld_parsing_tolerates_wrappers_lists_and_broken_blocks():
    html = (
        '<script type="application/ld+json"><!-- {"@type": "Product", "name": "锅", "brand": {"name": "某牌"},'
        ' "offers": [{"price": "99", "priceCurrency": "CNY"}]} --></script>'
        '<script type="application/ld+json">[{"@type": "HowTo", "name": "叠衣服", "step": ["对折", "再对折"]}]</script>'
        '<script type="application/ld+json">{not json}</script>'
    )
    objects = web.jsonld_objects(html)
    assert [web.types_of(node) for node in objects] == [{"Product"}, {"HowTo"}]
    summary = web.structured_summary(objects)
    assert "价格：99 CNY" in summary and "品牌：某牌" in summary
    assert "1. 对折" in summary


def test_embedded_videos_are_listed():
    body = (
        '<iframe src="https://www.youtube.com/embed/abc"></iframe>'
        '<video src="/media/clip.mp4"></video>'
        '<iframe src="https://ads.example.com/banner.html"></iframe>'
    )
    page = web.page_from_html(URL, article_page(body_extra=body))
    assert page.unprocessed_media == ["https://www.youtube.com/embed/abc", "https://food.example.com/media/clip.mp4"]


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("https://x.com/a?utm_source=1&id=2#top", "https://X.com/a?id=2", True),
        ("https://x.com/a?id=2&spm=abc", "https://x.com/a?id=2", True),
        ("https://x.com/a?id=2", "https://x.com/a?id=3", False),
        ("https://x.com/a", "https://x.com/b", False),
    ],
)
def test_page_id_ignores_fragments_and_tracking_parameters(a, b, same):
    assert (web.page_id(a) == web.page_id(b)) is same
    assert len(web.page_id(a)) == 24 and int(web.page_id(a), 16) >= 0


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        ('<meta charset="gb2312"><p>番茄炒蛋</p>'.encode("gbk"), "text/html"),
        ("<p>番茄炒蛋</p>".encode("gbk"), "text/html; charset=GBK"),
        ("<p>番茄炒蛋</p>".encode("utf-8"), "text/html"),
        ("<p>番茄炒蛋</p>".encode("gb18030"), ""),  # no declared charset, not UTF-8
    ],
)
def test_decode_html_handles_chinese_encodings(body, content_type):
    assert "番茄炒蛋" in web.decode_html(body, content_type)


def test_non_html_links_are_rejected_clearly(monkeypatch):
    monkeypatch.setattr(net, "fetch", lambda *a, **k: net.Response("https://x.com/a.pdf", "application/pdf", b"%PDF"))
    with pytest.raises(RuntimeError, match="not a web page"):
        web.fetch("https://x.com/a.pdf")


def test_canonical_link_from_the_page_sets_the_note_id():
    head = '<link rel="canonical" href="https://food.example.com/recipes/fanqie">'
    page = web.page_from_html(URL, article_page(head_extra=head))
    assert page.canonical_url == "https://food.example.com/recipes/fanqie"
