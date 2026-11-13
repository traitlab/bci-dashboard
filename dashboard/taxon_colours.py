"""Tree Colors (Tennekes & de Jonge, IEEE TVCG 2014) for the clade > order > family hierarchy.

Each clade owns a slice of the hue wheel, children split their parent's slice, and lightness rises
with depth, so an order or family reads as a shade of its clade on every page.
"""

import csv
import math
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "input"
FRACTION = 0.75  # share of a parent's hue slice its children use, leaving gaps between siblings
CANOPY = (95, 165)  # hues that vanish against green canopy imagery, skipped on the wheel
LEVELS = [(62, 60), (70, 50), (77, 40)]  # (lightness, chroma) for clade, order, family
TONES = [0, -14, 9, -7, 15, -20]  # family lightness steps: deep siblings get hue slices too thin to tell apart


def hcl_hex(hue, chroma, lightness):
    """Polar CIELUV (D65) to sRGB hex, clamped to gamut."""
    u, v = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    y = ((lightness + 16) / 116) ** 3 if lightness > 8 else lightness / 903.3
    up, vp = u / (13 * lightness) + 0.19784, v / (13 * lightness) + 0.46834
    x, z = y * 9 * up / (4 * vp), y * (12 - 3 * up - 20 * vp) / (4 * vp)
    linear = (3.2406 * x - 1.5372 * y - 0.4986 * z, -0.9689 * x + 1.8758 * y + 0.0415 * z, 0.0557 * x - 0.2040 * y + 1.0570 * z)
    gamma = [12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in linear]
    return "#" + "".join(f"{round(min(1, max(0, c)) * 255):02x}" for c in gamma)


def _skip_canopy(hue):
    """Map 0-360 onto the wheel minus the canopy band."""
    hue = hue % 360 * (360 - (CANOPY[1] - CANOPY[0])) / 360
    return hue + (CANOPY[1] - CANOPY[0]) * (hue >= CANOPY[0])


def interleave(names):
    """Spread neighbours apart on the wheel: 0, k/2, 1, k/2+1, ..."""
    half = (len(names) + 1) // 2
    return [n for pair in zip(names[:half], names[half:] + [None]) for n in pair if n is not None]


def _rows(name):
    with open(INPUT / name, newline="") as handle:
        return list(csv.DictReader(handle))


def tree_colours():
    """{clade, order or family name: '#rrggbb'}."""
    clades = [row["clade"] for row in _rows("clade_common.csv")]
    children = {}
    for row in _rows("order_clade.csv"):
        children.setdefault(row["clade"], []).append(row["order"])
    for row in _rows("family_order.csv"):
        if row["order"]:
            children.setdefault(row["order"], []).append(row["family"])
    colours = {}

    def paint(names, start, width, depth):
        if depth == len(LEVELS) or not names:
            return
        step = width / len(names)
        for i, name in enumerate(interleave(sorted(names) if depth else names)):
            lo = start + i * step + step * (1 - FRACTION) / 2
            lightness, chroma = LEVELS[depth]
            lightness += TONES[i % len(TONES)] * (depth == len(LEVELS) - 1)
            colours[name] = hcl_hex(_skip_canopy(lo + step * FRACTION / 2), chroma, lightness)
            paint(children.get(name, []), lo, step * FRACTION, depth + 1)

    paint(clades, 0, 360, 0)
    return colours
