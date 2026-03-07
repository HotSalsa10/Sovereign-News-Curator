"""
One-time script to generate home screen icons for Sovereign News Curator.
Run once locally, commit the generated PNGs.
"""

import math
from PIL import Image, ImageDraw, ImageFilter

def shield_pts(cx, cy, w, h):
    """Pentagon shield: flat top, pointed bottom."""
    hw, hh = w / 2, h / 2
    notch = hh * 0.62
    return [
        (cx - hw, cy - hh),
        (cx + hw, cy - hh),
        (cx + hw, cy - hh + notch),
        (cx,      cy + hh),
        (cx - hw, cy - hh + notch),
    ]

def star_pts(cx, cy, r_out, r_in, points=5):
    """5-pointed star."""
    pts = []
    for i in range(points * 2):
        angle = math.radians(-90 + i * (180 / points))
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return pts

def create_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Rounded-square background ──
    pad = 0
    r = size // 5
    draw.rounded_rectangle([pad, pad, size - pad - 1, size - pad - 1],
                            radius=r, fill=(13, 17, 38, 255))

    cx = size // 2
    cy = int(size * 0.50)

    sw = int(size * 0.60)  # shield width
    sh = int(size * 0.68)  # shield height

    # ── Soft glow behind shield ──
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.polygon(shield_pts(cx, cy, sw + 18, sh + 18), fill=(59, 130, 246, 55))
    glow = glow.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # ── Outer shield (deep blue) ──
    draw.polygon(shield_pts(cx, cy, sw, sh), fill=(24, 56, 160, 255))

    # ── Inner shield (electric blue) ──
    iw, ih = int(sw * 0.80), int(sh * 0.80)
    draw.polygon(shield_pts(cx, cy - int(size * 0.015), iw, ih),
                 fill=(59, 130, 246, 255))

    # ── Top-left shimmer highlight ──
    hw2, hh2 = int(iw * 0.52), int(ih * 0.42)
    draw.polygon(shield_pts(cx - int(size * 0.06),
                            cy - int(size * 0.09),
                            hw2, hh2),
                 fill=(147, 197, 253, 200))

    # ── White star ──
    sr_out = int(size * 0.115)
    sr_in  = int(size * 0.048)
    star_cy = cy - int(size * 0.018)
    draw.polygon(star_pts(cx, star_cy, sr_out, sr_in), fill=(255, 255, 255, 255))

    return img


if __name__ == "__main__":
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for size in [180, 512]:
        icon = create_icon(size)
        # Flatten RGBA onto black for PNG (iOS expects opaque)
        bg = Image.new("RGB", icon.size, (13, 17, 38))
        bg.paste(icon, mask=icon.split()[3])
        out = os.path.join(root, f"icon-{size}.png")
        bg.save(out, "PNG")
        print(f"Saved: icon-{size}.png")

    print("Done. Commit the icon-*.png files to your repo.")
