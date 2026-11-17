"""Deterministic, model-free image rendering locked to a design direction's palette.

Every pixel is a convex blend of up to three palette colours, so style lock is checkable (`match`). This is
a procedural renderer, not a generative model: a model-backed generator plugs in at Phase 13 behind
the same tools and is held to the same `match` check.
"""
import hashlib
import math
import re
import struct
import zlib

Color = tuple[int, int, int]


def oklch_to_srgb(l: float, c: float, h: float) -> Color:
    a, b = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
    l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (l - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
           -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)

    def enc(x: float) -> int:
        x = min(1.0, max(0.0, x))
        x = 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
        return round(x * 255)

    return enc(rgb[0]), enc(rgb[1]), enc(rgb[2])


_STR = re.compile(r"oklch\(\s*([\d.]+)%?\s+([\d.]+)\s+([\d.]+)")


def parse_palette(raw) -> dict[str, Color]:
    """design_directions.palette_oklch: {name: [l,c,h] | {l,c,h} | 'oklch(l c h)'} or a list of the same."""
    items = raw.items() if isinstance(raw, dict) else enumerate(raw)
    out: dict[str, Color] = {}
    for k, v in items:
        if isinstance(v, str):
            m = _STR.match(v)
            if not m:
                raise ValueError(f"palette entry {k!r} is not an oklch() value")
            l, c, h = (float(x) for x in m.groups())
            l = l / 100 if "%" in v.split(")")[0] and l > 1 else l
        elif isinstance(v, dict):
            l, c, h = float(v["l"]), float(v["c"]), float(v["h"])
        else:
            l, c, h = (float(x) for x in v)
        out[str(k)] = oklch_to_srgb(l, c, h)
    if len(out) < 2:
        raise ValueError("a style lock needs at least two palette colours")
    return out


def _mix(a: Color, b: Color, t: float) -> Color:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def render(palette: dict[str, Color], subject: str, width: int, height: int, kind: str, seed: int) -> bytes:
    cols = [palette[k] for k in sorted(palette)]
    h = hashlib.sha256(f"{subject}|{kind}|{seed}".encode()).digest()
    a, b = cols[h[0] % len(cols)], cols[h[1] % len(cols)]
    if a == b:
        b = cols[(h[1] + 1) % len(cols)]
    blobs = [(h[2 + i * 4] / 255 * width, h[3 + i * 4] / 255 * height, (0.15 + h[4 + i * 4] / 255 * 0.3) * min(width, height),
              cols[h[5 + i * 4] % len(cols)]) for i in range(3)]
    ang = (h[20] / 255) * math.pi
    ca, sa = math.cos(ang), math.sin(ang)
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            t = ((x / width - 0.5) * ca + (y / height - 0.5) * sa) + 0.5
            px = _mix(a, b, min(1.0, max(0.0, t)))
            best, bcol = 0.0, px
            for bx, by, r, bc in blobs:   # only the strongest blob applies: at most three colours per pixel
                d = math.hypot(x - bx, y - by) / r
                if d < 1 and 0.65 * (1 - d * d) > best:
                    best, bcol = 0.65 * (1 - d * d), bc
            if best:
                px = _mix(px, bcol, best)
            row += bytes(px)
        rows.append(bytes(row))
    return png(width, height, b"".join(rows))


def png(width: int, height: int, raw: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def decode(data: bytes) -> tuple[int, int, list[Color]]:
    """Decode only the PNGs this module writes (8-bit RGB, filter 0)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat = 8, b""
    w = h = 0
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            if (depth, ctype) != (8, 2):
                raise ValueError("unsupported PNG layout")
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    px: list[Color] = []
    stride = 1 + 3 * w
    for y in range(h):
        row = raw[y * stride:(y + 1) * stride]
        if row[0] != 0:
            raise ValueError("unsupported PNG filter")
        px += [(row[1 + i * 3], row[2 + i * 3], row[3 + i * 3]) for i in range(w)]
    return w, h, px


def match(pixels: list[Color], palette: dict[str, Color], tolerance: float = 8.0, steps: int = 24) -> float:
    """Share of sampled pixels within `tolerance` (RGB distance) of a blend of up to three palette colours."""
    cols = list(palette.values())
    blends = set(cols)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            blends.update(_mix(a, b, k / steps) for k in range(steps + 1))
    n = 20   # three-colour blends: the gradient is a blend of two colours, a blob adds a third
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            for k in range(j + 1, len(cols)):
                for u in range(n + 1):
                    for v in range(n + 1 - u):
                        w = n - u - v
                        blends.add(tuple(round((u * cols[i][c] + v * cols[j][c] + w * cols[k][c]) / n) for c in range(3)))
    blends = list(blends)
    step = max(1, len(pixels) // 1500)
    sample = pixels[::step]
    ok = sum(1 for p in sample if min(math.dist(p, q) for q in blends) <= tolerance)
    return ok / len(sample)
