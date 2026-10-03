"""Any other web page: articles, blog posts, recipe pages, documentation.

The main text comes from trafilatura, which drops navigation, ads, comments, and footers.
schema.org JSON-LD (Recipe, HowTo, Product, Article, ...) supplies the author when trafilatura
finds none, and recipe ingredients and steps when the page publishes them. Images inside the
main text are downloaded, up to ``[web] max_images`` in cost_policy.toml, and OCR'd; images
smaller than ``min_image_side`` (icons, thumbnails) are dropped. The og:image cover is only recorded.

Not handled here, and left to future sources: pages that need JavaScript or a login, PDFs and
other non-HTML links, and embedded videos (listed in caption.txt and metadata as unprocessed).

Output layout: ``output/web/<key>/``, where the key and the note ID are the first 24 hex digits
of the SHA-1 of the canonical URL (fragment and tracking parameters removed).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from .. import cost, media, net
from . import Job, Source

TRACKING_PARAMS = re.compile(r"^(utm_\w+|spm|fbclid|gclid|mc_cid|mc_eid|share_\w+|xsec_\w+|from|source)$", re.I)
RELEVANT_TYPES = {"Recipe", "HowTo", "Product", "Review", "Article", "NewsArticle", "BlogPosting", "VideoObject"}
VIDEO_HOSTS = ("youtube.com", "youtu.be", "bilibili.com", "vimeo.com", "ixigua.com", "douyin.com", "v.qq.com")
NO_SPEECH = "web pages are not transcribed"


@dataclass
class WebPage:
    url: str
    canonical_url: str
    title: str = ""
    author: str = ""
    published_at: str | None = None
    site_name: str = ""
    description: str = ""
    text: str = ""
    #: (absolute URL, alt text) of images in the main text, in reading order.
    images: list[tuple[str, str]] = field(default_factory=list)
    #: The page's og:image. Only recorded: it is usually a generated preview of the title, so
    #: OCR on it repeats the text at full OCR cost.
    cover_image: str = ""
    structured: list[dict] = field(default_factory=list)
    unprocessed_media: list[str] = field(default_factory=list)


def canonical_url(url: str) -> str:
    """The URL without its fragment and tracking parameters, with a lowercase host."""
    parsed = urlparse(url.strip())
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if not TRACKING_PARAMS.match(key)]
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", urlencode(query), ""))


def page_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:24]


def decode_html(body: bytes, content_type: str = "") -> str:
    """Decode with the charset from the header, then from <meta>, then UTF-8, then GB18030."""
    candidates = []
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        candidates.append(match.group(1))
    match = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
    if match:
        candidates.append(match.group(1).decode("ascii", errors="ignore"))
    candidates += ["utf-8", "gb18030"]
    for charset in candidates:
        charset = "gb18030" if charset.lower() in ("gb2312", "gbk") else charset
        try:
            return body.decode(charset)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def jsonld_objects(page_html: str) -> list[dict]:
    """Every JSON-LD object on the page, with @graph containers and lists flattened."""
    objects: list[dict] = []

    def collect(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                collect(item)
        elif isinstance(node, dict):
            if "@graph" in node:
                collect(node["@graph"])
            if "@type" in node:
                objects.append(node)

    for block in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", page_html, re.S | re.I):
        block = re.sub(r"^\s*(<!--|<!\[CDATA\[)|(-->|\]\]>)\s*$", "", block.strip())
        try:
            collect(json.loads(block))
        except json.JSONDecodeError:
            continue
    return objects


def types_of(node: dict) -> set[str]:
    value = node.get("@type")
    return set(value) if isinstance(value, list) else {value}


def person_name(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()
    if isinstance(value, list):
        return "、".join(name for name in (person_name(item) for item in value) if name)
    return ""


def _steps(instructions: object) -> list[str]:
    """Recipe/HowTo steps as text; handles strings, HowToStep, and HowToSection."""
    if isinstance(instructions, str):
        return [line.strip() for line in re.split(r"\n+", instructions) if line.strip()]
    steps: list[str] = []
    for item in instructions if isinstance(instructions, list) else [instructions]:
        if isinstance(item, str):
            steps.append(item.strip())
        elif isinstance(item, dict):
            if item.get("itemListElement"):
                steps += [f"{item.get('name', '').strip()}：{step}".lstrip("：") for step in _steps(item["itemListElement"])]
            elif item.get("text") or item.get("name"):
                steps.append(str(item.get("text") or item.get("name")).strip())
    return [step for step in steps if step]


def structured_summary(objects: list[dict]) -> str:
    """Readable text for the recipe, how-to, and product data a page publishes."""
    parts = []
    for node in objects:
        kinds = types_of(node)
        if "Recipe" in kinds:
            lines = [f"菜谱：{node.get('name', '')}".rstrip("：")]
            for key, label in (("recipeYield", "份量"), ("prepTime", "准备时间"), ("cookTime", "烹饪时间"), ("totalTime", "总时间")):
                if node.get(key):
                    value = node[key]
                    lines.append(f"{label}：{'、'.join(map(str, value)) if isinstance(value, list) else value}")
            ingredients = node.get("recipeIngredient") or node.get("ingredients") or []
            if ingredients:
                lines.append("配料：")
                lines += [f"- {item}" for item in ingredients]
            steps = _steps(node.get("recipeInstructions") or [])
            if steps:
                lines.append("做法：")
                lines += [f"{index}. {step}" for index, step in enumerate(steps, 1)]
            parts.append("\n".join(lines))
        elif "HowTo" in kinds:
            steps = _steps(node.get("step") or [])
            if steps:
                parts.append("\n".join([f"教程：{node.get('name', '')}"] + [f"{i}. {s}" for i, s in enumerate(steps, 1)]))
        elif "Product" in kinds:
            lines = [f"产品：{node.get('name', '')}"]
            brand = person_name(node.get("brand"))
            if brand:
                lines.append(f"品牌：{brand}")
            offers = node.get("offers")
            offer = offers[0] if isinstance(offers, list) and offers else offers
            if isinstance(offer, dict) and offer.get("price"):
                lines.append(f"价格：{offer.get('price')} {offer.get('priceCurrency', '')}".rstrip())
            parts.append("\n".join(lines))
    return "\n\n".join(parts)


def embedded_videos(page_html: str, base_url: str) -> list[str]:
    found = []
    for src in re.findall(r"<(?:iframe|video|source)[^>]+src=[\"']([^\"']+)", page_html, re.I):
        url = urljoin(base_url, src)
        host = (urlparse(url).hostname or "").lower()
        if url.lower().split("?")[0].endswith((".mp4", ".webm", ".m3u8")) or any(host.endswith(h) for h in VIDEO_HOSTS):
            if url not in found:
                found.append(url)
    return found


def page_from_html(final_url: str, page_html: str) -> WebPage:
    """Parse a fetched page. Kept separate from fetching so tests can use saved pages."""
    import trafilatura

    meta = trafilatura.extract_metadata(page_html, default_url=final_url)
    text = trafilatura.extract(
        page_html,
        url=final_url,
        output_format="markdown",
        include_images=True,
        include_tables=True,
        include_comments=False,
        favor_recall=True,
    ) or ""
    objects = [node for node in jsonld_objects(page_html) if types_of(node) & RELEVANT_TYPES]

    images: list[tuple[str, str]] = []
    for alt, src in re.findall(r"!\[([^\]]*)\]\(\s*([^)\s]+)", text):
        url = urljoin(final_url, src)
        if url.startswith("http") and not url.lower().split("?")[0].endswith(".svg") and url not in [u for u, _ in images]:
            images.append((url, alt.strip()))

    jsonld_author = next((person_name(node.get("author")) for node in objects if node.get("author")), "")
    meta_author = re.search(r"<meta[^>]+name=[\"']author[\"'][^>]+content=[\"']([^\"']+)", page_html, re.I)
    jsonld_date = next((str(node["datePublished"])[:10] for node in objects if node.get("datePublished")), None)
    jsonld_title = next((str(node.get("headline") or node.get("name")) for node in objects if node.get("headline") or node.get("name")), "")
    html_title = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.S | re.I)

    return WebPage(
        url=final_url,
        canonical_url=canonical_url((meta.url if meta is not None and meta.url else None) or final_url),
        title=((meta.title if meta is not None else "") or jsonld_title or (html_title.group(1).strip() if html_title else "")).strip(),
        author=((meta.author if meta is not None else "") or jsonld_author or (meta_author.group(1) if meta_author else "")).strip(),
        published_at=(meta.date if meta is not None and meta.date else None) or jsonld_date,
        site_name=((meta.sitename if meta is not None else "") or urlparse(final_url).hostname or "").strip(),
        description=((meta.description if meta is not None else "") or "").strip(),
        text=text.strip(),
        images=images,
        structured=objects,
        unprocessed_media=embedded_videos(page_html, final_url),
        cover_image=urljoin(final_url, meta.image) if meta is not None and meta.image else "",
    )


def fetch(url: str) -> tuple[str, str]:
    response = net.fetch(
        url,
        user_agent=net.DESKTOP_USER_AGENT,
        headers={"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    )
    content_type = response.content_type.lower()
    if content_type and "html" not in content_type and "xml" not in content_type:
        raise RuntimeError(
            f"The link is not a web page ({content_type.split(';')[0]}). "
            "Only HTML pages are supported; PDFs, images, and videos need their own source."
        )
    return response.url, decode_html(response.body, response.content_type)


def save_image(url: str, referer: str, work_dir: Path, destination: Path, min_side: int) -> str:
    """Download an image and save it as JPEG.

    Returns "saved", "small" (icons, avatars, thumbnails: not worth OCR), or "failed".
    """
    from PIL import Image

    raw = work_dir / (destination.stem + ".download")
    try:
        net.download(url, raw, referer)
        with Image.open(raw) as image:
            if min(image.size) < min_side:
                return "small"
            image.convert("RGB").save(destination, "JPEG", quality=92)
        return "saved"
    except Exception:
        return "failed"
    finally:
        raw.unlink(missing_ok=True)


def write_caption(page: WebPage, output_dir: Path, image_names: dict[str, str]) -> None:
    def image_marker(match: re.Match) -> str:
        alt, src = match.group(1).strip(), urljoin(page.url, match.group(2))
        name = image_names.get(src)
        return f"[图 {name}：{alt}]" if name else f"[图：{alt}]"

    body = re.sub(r"!\[([^\]]*)\]\(\s*([^)\s]+)[^)]*\)", image_marker, page.text)
    header = [
        f"标题：{page.title}" if page.title else "",
        f"作者：{page.author}" if page.author else "",
        f"网站：{page.site_name}" if page.site_name else "",
        f"发布时间：{page.published_at}" if page.published_at else "",
        f"摘要：{page.description}" if page.description else "",
    ]
    parts = ["\n".join(line for line in header if line), f"正文：\n{body}" if body else ""]
    summary = structured_summary(page.structured)
    if summary:
        parts.append(f"页面结构化数据（schema.org）：\n{summary}")
    if page.unprocessed_media:
        parts.append("页面中的视频（未处理，没有转写）：\n" + "\n".join(f"- {url}" for url in page.unprocessed_media))
    (output_dir / "caption.txt").write_text("\n\n".join(part for part in parts if part), encoding="utf-8")


class WebSource(Source):
    name = "web"
    output_subdir = "web"

    def matches(self, url: str) -> bool:
        return urlparse(url).scheme in ("http", "https")

    def output_key(self, url: str) -> str:
        return page_id(url)

    def extract(self, job: Job) -> None:
        settings = job.policy.get("web", {})
        with cost.stage("fetch"):
            final_url, page_html = fetch(job.url)
        with cost.stage("parse"):
            page = page_from_html(final_url, page_html)
        if not page.text and not page.images:
            raise RuntimeError(
                "No readable content was found. The page may need JavaScript or a login, or it may block automated access."
            )

        selected = page.images[: settings.get("max_images", 8)]
        job.metadata.update(
            {
                "resolved_url": final_url,
                "canonical_url": page.canonical_url,
                "note_id": page_id(page.canonical_url),
                "note_type": "article",
                "title": page.title,
                "published_at": page.published_at,
                "author": page.author or None,
                "site_name": page.site_name or None,
                "cover_image": page.cover_image or None,
                "parser": "trafilatura",
                "text_chars": len(page.text),
                "images_found": len(page.images),
                "images_skipped": len(page.images) - len(selected),
                "structured_types": sorted({kind for node in page.structured for kind in types_of(node) if kind}),
                "unprocessed_media": page.unprocessed_media,
            }
        )
        if len(page.text) < settings.get("thin_text_chars", 200):
            job.metadata["content_warning"] = (
                "very little text was found; the page may load its content with JavaScript or hide it behind a login"
            )

        media_dir = job.output_dir / "media"
        media_dir.mkdir(exist_ok=True)
        for stale in media_dir.glob("image-*.jpg"):
            stale.unlink()
        image_names: dict[str, str] = {}
        image_paths: list[Path] = []
        outcomes: list[str] = []
        with cost.stage("download"):
            for url, _ in selected:
                destination = media_dir / f"image-{len(image_paths) + 1:02d}.jpg"
                outcome = save_image(url, final_url, job.work_dir, destination, settings.get("min_image_side", 200))
                outcomes.append(outcome)
                if outcome == "saved":
                    image_names[url] = destination.stem
                    image_paths.append(destination)
        job.metadata["images_small"] = outcomes.count("small")
        job.metadata["images_failed"] = outcomes.count("failed")
        # Predict here, not before downloading: only now is it known which images are icons that
        # will not be OCR'd. Downloading is cheap; OCR is the cost being predicted.
        cost.predict(ocr_images=len(image_paths), policy=job.policy)

        write_caption(page, job.output_dir, image_names)
        if page.structured:
            (job.output_dir / "structured.json").write_text(
                json.dumps(page.structured, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        job.metadata.update(media.analyze_images(image_paths, job.output_dir, NO_SPEECH))
