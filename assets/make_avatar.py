"""Draws the little HireAce character on the desktop while the panel is minimized
(bubble.ps1): a round, faceted purple gem with a friendly face. Frames: resting,
blinking, and two for knocking on the screen. Also the knock sound.
Run: python make_avatar.py

Drawn on a 300 x 300 grid at 4x, then scaled down for smooth edges.
"""

import math
import struct
import wave
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = Path(__file__).parent
S, K = 300, 4

# The gem's outline, and its facets from lightest (top left) to darkest (bottom right)
OUTLINE = [(138, 34), (196, 56), (232, 112), (224, 182), (176, 226), (106, 232), (56, 196), (40, 128), (72, 66)]
FACETS = [
    ((176, 138, 244), [(138, 34), (72, 66), (112, 92)]),
    ((160, 118, 236), [(138, 34), (196, 56), (160, 88), (112, 92)]),
    ((145, 98, 226), [(196, 56), (232, 112), (160, 88)]),
    ((166, 124, 240), [(72, 66), (40, 128), (72, 130), (112, 92)]),
    ((138, 92, 220), [(112, 92), (160, 88), (232, 112), (224, 182), (176, 226), (106, 232), (56, 196), (72, 130)]),
    ((150, 104, 230), [(40, 128), (56, 196), (72, 130)]),
    ((116, 72, 196), [(232, 112), (224, 182), (190, 150)]),
    ((104, 62, 184), [(224, 182), (176, 226), (190, 150)]),
    ((124, 80, 206), [(106, 232), (56, 196), (84, 178)]),
    ((112, 68, 192), [(176, 226), (106, 232), (140, 196)]),
]
HAND, HAND_SHADE = (150, 104, 230), (108, 66, 188)
INK, CHEEK, SMILE = (28, 20, 44), (255, 138, 170), (36, 26, 56)


def p(*xy):
    """Grid units to pixels."""
    return [v * K for v in xy]


def gem() -> Image.Image:
    """The body: facets clipped to the outline, with softly rounded corners."""
    size = (S * K, S * K)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(p(*[v for point in OUTLINE for v in point]), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(9 * K)).point(lambda v: 255 if v > 128 else 0)

    body = Image.new("RGBA", size, FACETS[4][0] + (255,))
    d = ImageDraw.Draw(body)
    for color, points in FACETS:
        d.polygon(p(*[v for point in points for v in point]), fill=color + (255,))
    body.putalpha(ImageChops.multiply(mask, body.getchannel("A")))
    return body


def frame(blink=False, knock=0):
    """knock: 0 resting, 1 hand raised, 2 knuckles on the screen."""
    im = Image.new("RGBA", (S * K, S * K), (0, 0, 0, 0))

    # Soft shadow under it
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(p(62, 232, 208, 262), fill=(0, 0, 0, 80))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6 * K)))
    im.alpha_composite(gem())
    d = ImageDraw.Draw(im)

    # Eyes: round and dark with a sparkle, or closed in a blink
    for x in (106, 170):
        if blink:
            d.arc(p(x - 13, 122, x + 13, 146), 20, 160, fill=INK, width=5 * K)
        else:
            d.ellipse(p(x - 13, 116, x + 13, 144), fill=INK)
            d.ellipse(p(x - 7, 120, x + 1, 129), fill=(255, 255, 255))
            d.ellipse(p(x + 3, 133, x + 7, 137), fill=(255, 255, 255))
    # Smile and cheeks
    d.arc(p(124, 134, 152, 162), 25, 155, fill=SMILE, width=5 * K)
    cheeks = Image.new("RGBA", im.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(cheeks)
    for x in (80, 196):
        cd.ellipse(p(x - 15, 150, x + 15, 168), fill=CHEEK + (235,))
    im.alpha_composite(cheeks.filter(ImageFilter.GaussianBlur(1.2 * K)))

    # Knocking: a small round hand comes up beside it, knuckles towards the screen
    if knock:
        d = ImageDraw.Draw(im)
        near = knock == 2
        fx, fy = (252, 104) if near else (262, 128)
        size = 27 if near else 20
        d.ellipse(p(fx - size, fy - size, fx + size, fy + size), fill=HAND, outline=HAND_SHADE, width=3 * K)
        for i in range(3):
            kx = fx - size * 0.55 + i * size * 0.55
            d.arc(p(kx - 6, fy - size * 0.5, kx + 6, fy + 3), 200, 340, fill=HAND_SHADE, width=2 * K)
        if near:  # the knock: little lines where the knuckles hit the glass
            for angle in (-125, -90, -55):
                a = math.radians(angle)
                x1, y1 = fx + math.cos(a) * (size + 5), fy + math.sin(a) * (size + 5)
                x2, y2 = fx + math.cos(a) * (size + 17), fy + math.sin(a) * (size + 17)
                d.line([*p(x1, y1), *p(x2, y2)], fill=(90, 70, 140), width=3 * K)
    return im.resize((S, S), Image.LANCZOS)


def knock_sound(path):
    """One soft knock on glass, a short and quickly fading thud (bubble.ps1 plays
    it on each tap of the animation: knock... knock)."""
    rate = 22050
    samples = []
    for i in range(int(0.09 * rate)):
        t = i / rate
        fade = math.exp(-t * 55)
        samples.append(fade * (0.7 * math.sin(2 * math.pi * 190 * t) + 0.3 * math.sin(2 * math.pi * 420 * t)))
    samples += [0.0] * int(0.05 * rate)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(b"".join(struct.pack("<h", int(s * 0.5 * 32767)) for s in samples))


if __name__ == "__main__":
    frame().save(OUT / "avatar.png")
    frame(blink=True).save(OUT / "avatar-blink.png")
    frame(knock=1).save(OUT / "avatar-knock1.png")
    frame(knock=2).save(OUT / "avatar-knock2.png")
    knock_sound(OUT / "knock.wav")
