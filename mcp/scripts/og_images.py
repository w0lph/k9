"""Open Graph preview images for the evidence site (1200x630 PNG), drawn with Pillow.

Images are generated only when missing so that a rebuild on another machine (different fonts)
does not churn the committed files; delete the PNG to regenerate it.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG, FG, MUTED, ACCENT, GREY = "#ffffff", "#1d1d1f", "#5d5d63", "#0b57d0", "#9aa0a6"
FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
]
BOLD_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for p in (BOLD_CANDIDATES if bold else FONT_CANDIDATES):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def default_image(path: Path, title: str, subtitle: str, footer: str) -> None:
    if path.exists():
        return
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=ACCENT)
    y = 110
    for line in _wrap(d, title, _font(68, bold=True), W - 160):
        d.text((80, y), line, fill=FG, font=_font(68, bold=True))
        y += 84
    y += 20
    for line in _wrap(d, subtitle, _font(34), W - 160)[:3]:
        d.text((80, y), line, fill=MUTED, font=_font(34))
        y += 46
    d.text((80, H - 70), footer, fill=GREY, font=_font(26))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)


def years_chart_image(path: Path, title: str, bars: list[tuple[str, float, str]], footer: str, max_years: float = 22.0) -> None:
    """bars: (label, years, note); the bar whose label starts with 'Dogs' is highlighted."""
    if path.exists():
        return
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=ACCENT)
    d.text((80, 60), title, fill=FG, font=_font(44, bold=True))
    left, right, top, row_h = 400, W - 80, 170, 95
    scale = (right - left - 400) / max_years
    lab_font, note_font = _font(30), _font(26)
    for i, (label, years, note) in enumerate(bars):
        y = top + i * row_h
        d.text((left - 24 - d.textlength(label, font=lab_font), y + 8), label, fill=FG, font=lab_font)
        bar_w = max(6, years * scale)
        fill = ACCENT if label.startswith("Dogs") else GREY
        d.rounded_rectangle([left, y, left + bar_w, y + 46], radius=8, fill=fill)
        d.text((left + bar_w + 16, y + 8), note, fill=MUTED, font=note_font)
    d.text((80, H - 70), footer, fill=GREY, font=_font(24))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
