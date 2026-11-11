"""Local artwork and text-based video export; GPU image/video models are optional plugins."""
from html import escape
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import subprocess
import textwrap


def banner_svg(title: str, subtitle: str) -> bytes:
    title = escape(title, quote=True)
    subtitle = escape(subtitle, quote=True)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#08172a"/><path d="M810 0 L1200 0 L1200 630 L950 630 Z" fill="#117b70" opacity=".38"/><circle cx="960" cy="275" r="210" fill="none" stroke="#6ee7b7" stroke-width="18" opacity=".5"/><rect x="70" y="95" width="100" height="12" rx="6" fill="#3ecaa8"/><foreignObject x="70" y="135" width="900" height="300"><div xmlns="http://www.w3.org/1999/xhtml" style="font: bold 70px system-ui,sans-serif;color:white;overflow-wrap:anywhere;line-height:1.12">{title}</div></foreignObject><foreignObject x="75" y="430" width="850" height="100"><div xmlns="http://www.w3.org/1999/xhtml" style="font: 30px system-ui,sans-serif;color:#b7cbe0;overflow-wrap:anywhere">{subtitle}</div></foreignObject><text x="78" y="580" font-size="21" font-family="system-ui" fill="#8af1d2">CREATED WITH REVENUEOS</text></svg>'''.encode("utf-8")


def render_video(title: str, subtitle: str, destination: Path, seconds: int = 6) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    image_file = destination.with_suffix(".png")
    image = Image.new("RGB", (540, 960), "#08172a")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28, 28, 512, 932), radius=36, outline="#135f5d", width=4)
    draw.ellipse((270, 100, 650, 500), fill="#0a4947")
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    regular_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold = ImageFont.truetype(font_path, 47)
    regular = ImageFont.truetype(regular_path, 27)
    for idx, line in enumerate(textwrap.wrap(title, 18)[:5]):
        draw.text((56, 355 + 61 * idx), line, font=bold, fill="white")
    for idx, line in enumerate(textwrap.wrap(subtitle, 32)[:4]):
        draw.text((56, 690 + 39 * idx), line, font=regular, fill="#b3d6d2")
    draw.rounded_rectangle((55, 855, 315, 907), radius=18, fill="#12a78b")
    draw.text((80, 866), "LEARN MORE", font=regular, fill="#061b1b")
    image.save(image_file)
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1",
                        "-framerate", "24", "-i", str(image_file), "-t", str(seconds), "-r", "24",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)],
                       check=True, timeout=90, capture_output=True)
    finally:
        image_file.unlink(missing_ok=True)
