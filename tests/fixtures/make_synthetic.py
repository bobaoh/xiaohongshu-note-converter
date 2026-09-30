"""Regenerate the synthetic test media in tests/fixtures/synthetic/.

The generated files are committed, so this only needs to run when the fixtures change.
It requires Windows (for the Microsoft Huihui zh-CN speech voice), the Microsoft YaHei
font, FFmpeg with libx264, and Pillow. Everything is original content, so the files
can live in a public repository.

    python tests/fixtures/make_synthetic.py
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "synthetic"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")

SPEECH_TEXT = "今天做焙茶团子。糯米粉三十二克，牛奶七十克。放进微波炉，高火加热两分钟。"
SPEECH_SUBTITLES = ["糯米粉 32g 牛奶 70g", "微波炉高火 2 分钟"]
MUSIC_SUBTITLES = ["茉莉抹茶蛋糕", "低筋面粉 65g"]
SILENT_SUBTITLES = ["Live Photo 测试"]
CARDS = {
    "card-01.jpg": ["焙茶奶酪馅", "奶油奶酪 135g", "焙茶粉 4g", "糖 3g"],
    "card-02.jpg": ["组装步骤", "1 面皮铺进模具", "2 放入无花果"],
}


def draw_lines(lines: list[str], size: tuple[int, int], path: Path, font_size: int, background: str) -> None:
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT), font_size)
    line_height = int(font_size * 1.6)
    top = (size[1] - line_height * len(lines)) // 2
    for index, line in enumerate(lines):
        width = draw.textlength(line, font=font)
        draw.text(((size[0] - width) / 2, top + index * line_height), line, font=font, fill="black")
    image.save(path, quality=90)


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def speak(text: str, wav_path: Path) -> None:
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$s.SelectVoice('Microsoft Huihui Desktop');"
        f"$s.SetOutputToWaveFile('{wav_path}');"
        f"$s.Speak('{text}');"
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def slideshow(subtitles: list[str], seconds_each: float, work: Path, name: str) -> Path:
    """Write subtitle frames and an FFmpeg concat list; return the list path."""
    lines = []
    for index, subtitle in enumerate(subtitles):
        frame = work / f"{name}-{index}.png"
        draw_lines([subtitle], (720, 1280), frame, 64, "#f4efe6")
        lines += [f"file '{frame.as_posix()}'", f"duration {seconds_each}"]
    lines.append(f"file '{(work / f'{name}-{len(subtitles) - 1}.png').as_posix()}'")
    concat = work / f"{name}.txt"
    concat.write_text("\n".join(lines), encoding="utf-8")
    return concat


VIDEO_ARGS = ["-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "32"]
AUDIO_ARGS = ["-c:a", "aac", "-b:a", "48k", "-shortest"]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="xhs-fixtures-"))
    try:
        speech_wav = work / "speech.wav"
        speak(SPEECH_TEXT, speech_wav)
        concat = slideshow(SPEECH_SUBTITLES, 6, work, "speech")
        ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(speech_wav), *VIDEO_ARGS, *AUDIO_ARGS, str(OUT / "speech.mp4"))

        # Two alternating tones stand in for background music: audible, but no speech.
        melody = "0.25*sin(2*PI*(392+131*gt(mod(t,1),0.5))*t)+0.1*sin(2*PI*784*t)"
        concat = slideshow(MUSIC_SUBTITLES, 4, work, "music")
        ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-f", "lavfi", "-i", f"aevalsrc='{melody}':s=44100:d=8",
               *VIDEO_ARGS, *AUDIO_ARGS, str(OUT / "music_only.mp4"))

        concat = slideshow(SILENT_SUBTITLES, 3, work, "silent")
        ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), *VIDEO_ARGS, "-an", str(OUT / "silent.mp4"))

        for name, lines in CARDS.items():
            draw_lines(lines, (1080, 1440), OUT / name, 72, "white")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for path in sorted(OUT.iterdir()):
        print(f"{path.name}: {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
