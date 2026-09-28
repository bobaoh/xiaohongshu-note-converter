from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from urllib.error import HTTPError
from pathlib import Path


def fetch_page(url: str) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.geturl(), response.read().decode("utf-8", errors="replace")


def image_urls(page: str) -> list[str]:
    decoded = html.unescape(page).replace(r"\u002F", "/").replace(r"\/", "/")
    urls = re.findall(r"https?://[^\"'<>\s]+", decoded)
    selected = []
    seen = set()
    for url in urls:
        if "xhscdn.com" not in url or "avatar" in url.lower():
            continue
        if re.match(r"https?://[^/]+/?$", url):
            continue
        if not any(token in url.lower() for token in ("imageview", "jpg", "jpeg", "png", "webp")):
            continue
        if url not in seen:
            seen.add(url)
            selected.append(url)
    return selected


def download(url: str, path: Path, referer: str) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            "Referer": referer,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response, path.open("wb") as output:
            shutil.copyfileobj(response, output)
    except HTTPError:
        subprocess.run(
            [
                "curl.exe",
                "-sS",
                "-L",
                "--fail",
                "--retry",
                "2",
                "-A",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
                "-e",
                referer,
                "-o",
                str(path),
                url,
            ],
            check=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR images from a public Xiaohongshu image post.")
    parser.add_argument("url")
    parser.add_argument("--output", default="output")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    media = output / "media"
    output.mkdir(parents=True, exist_ok=True)
    media.mkdir(exist_ok=True)
    metadata = {"input_url": args.url, "status": "started"}

    try:
        resolved, page = fetch_page(args.url)
        urls = image_urls(page)
        if not urls:
            raise RuntimeError("No public post images were found.")
        metadata.update({"resolved_url": resolved, "image_count": len(urls)})

        from rapidocr_onnxruntime import RapidOCR
        import cv2

        engine = RapidOCR()
        rows = []
        seen = set()
        for index, url in enumerate(urls, 1):
            image_path = media / f"image-{index:02d}.jpg"
            download(url, image_path, resolved)
            image = cv2.imread(str(image_path))
            if image is None:
                continue
            result, _ = engine(image)
            if not result:
                continue
            for item in result:
                text = str(item[1]).strip()
                confidence = float(item[2])
                key = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", text)
                if confidence >= 0.45 and len(key) >= 2 and key not in seen:
                    seen.add(key)
                    rows.append(f"[image-{index:02d}|{confidence:.2f}] {text}")

        (output / "ocr.txt").write_text("\n".join(rows), encoding="utf-8")
        metadata.update({"status": "complete", "ocr_lines": len(rows)})
    except Exception as error:
        metadata.update({"status": "failed", "error": str(error)})
        (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        raise

    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Complete. Read {output / 'ocr.txt'} and inspect images in {media}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
