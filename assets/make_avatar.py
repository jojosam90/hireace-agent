"""Draws the HireAce assistant that stands on the desktop while the panel is
minimized (bubble.ps1): a friendly office assistant with a dark bob, big brown
eyes and a blue dress, standing. Frames: standing, blinking, and two for knocking
on the screen. Also the knock sound. Run: python make_avatar.py

Drawn on a 300 x 500 grid at 4x, then scaled down for smooth edges.
"""

import math
import struct
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).parent
W, H, K = 300, 500, 4

SKIN, SKIN_SHADE = (252, 222, 204), (240, 196, 172)
HAIR, HAIR_SHINE = (38, 34, 40), (78, 72, 84)
DRESS, DRESS_SHADE = (66, 133, 244), (43, 104, 214)
WHITE, OUTLINE = (255, 255, 255), (60, 50, 50)
IRIS, PUPIL = (122, 74, 40), (40, 22, 12)
EARRING = (56, 168, 222)
BLUSH = (255, 150, 160, 110)
LIPS = (214, 96, 110)
SHOE, SHOE_LINE = (250, 250, 252), (190, 190, 200)
BRAND_BLUE = (47, 107, 255)


def p(*xy):
    """Grid units to pixels."""
    return [v * K for v in xy]


def bezier(points, steps=24):
    """A smooth curve through control points (quadratic segments)."""
    out = []
    for i in range(0, len(points) - 2, 2):
        (x0, y0), (x1, y1), (x2, y2) = points[i : i + 3]
        for s in range(steps + 1):
            t = s / steps
            out.append(
                (
                    (1 - t) ** 2 * x0 + 2 * (1 - t) * t * x1 + t**2 * x2,
                    (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t**2 * y2,
                )
            )
    return [(x * K, y * K) for x, y in out]


def limb(d, a, b, width, color):
    d.line([*p(*a), *p(*b)], fill=color, width=width * K)
    for x, y in (a, b):
        r = width / 2
        d.ellipse(p(x - r, y - r, x + r, y + r), fill=color)


def frame(blink=False, knock=0):
    """knock: 0 standing, 1 hand raised, 2 knuckles on the screen."""
    im = Image.new("RGBA", (W * K, H * K), (0, 0, 0, 0))

    # Soft shadow at her feet, so she stands on the desktop
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(p(88, 468, 212, 494), fill=(0, 0, 0, 90))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(5 * K)))
    d = ImageDraw.Draw(im)

    # Legs and shoes
    for x in (137, 163):
        d.rounded_rectangle(p(x - 9, 372, x + 9, 456), radius=8 * K, fill=SKIN)
    for x in (134, 166):
        d.rounded_rectangle(p(x - 17, 448, x + 17, 472), radius=11 * K, fill=SHOE, outline=SHOE_LINE, width=2 * K)

    # Dress: fitted top, flared skirt, short sleeves, white collar, name badge
    d.polygon(p(114, 236, 186, 236, 198, 300, 214, 392, 86, 392, 102, 300), fill=DRESS)
    d.polygon(p(150, 300, 198, 300, 214, 392, 172, 392), fill=DRESS_SHADE)
    d.rounded_rectangle(p(86, 380, 214, 396), radius=6 * K, fill=DRESS_SHADE)
    # Her right arm (our left), always down; her left arm down unless knocking
    # (then it is drawn in front of her face, below)
    limb(d, (112, 252), (98, 352), 17, SKIN)
    d.ellipse(p(88, 342, 108, 362), fill=SKIN)
    if knock == 0:
        limb(d, (188, 252), (202, 352), 17, SKIN)
        d.ellipse(p(192, 342, 212, 362), fill=SKIN)
    d.ellipse(p(98, 232, 130, 270), fill=DRESS)  # sleeves over the shoulders
    d.ellipse(p(170, 232, 202, 270), fill=DRESS)
    d.rectangle(p(141, 212, 159, 238), fill=SKIN_SHADE)  # neck
    d.polygon(p(128, 234, 150, 238, 150, 262), fill=WHITE)  # collar
    d.polygon(p(172, 234, 150, 238, 150, 262), fill=WHITE)
    d.rounded_rectangle(p(160, 276, 184, 290), radius=3 * K, fill=WHITE)  # badge
    d.ellipse(p(163, 279, 171, 287), fill=BRAND_BLUE)
    d.line(p(173, 283, 181, 283), fill=(150, 160, 180), width=2 * K)

    # Hair behind the head: a bob down to the chin
    d.rounded_rectangle(p(70, 66, 230, 214), radius=62 * K, fill=HAIR)
    # Face
    d.ellipse(p(88, 74, 212, 212), fill=SKIN)
    # Earrings below the hair
    for x in (84, 216):
        d.ellipse(p(x - 6, 196, x + 6, 208), fill=EARRING)
    # Bangs: swept from a side part over the forehead
    bangs = bezier([(74, 150), (70, 60), (150, 50), (212, 52), (228, 130),
                    (205, 108), (176, 100), (140, 104), (100, 118), (86, 140), (74, 150)])
    d.polygon(bangs, fill=HAIR)
    d.arc(p(110, 56, 190, 104), 200, 300, fill=HAIR_SHINE, width=4 * K)

    # Knocking: her left arm (our right) raised beside her face, in front of it,
    # knuckles towards the screen
    if knock:
        near = knock == 2
        fist = (246, 150) if near else (252, 168)
        size = 20 if near else 15
        limb(d, (188, 254), (238, 232), 17, SKIN)  # upper arm out to the elbow
        d.ellipse(p(170, 232, 202, 270), fill=DRESS)  # sleeve over it
        limb(d, (238, 232), fist, 16, SKIN)  # forearm up
        fx, fy = fist
        d.ellipse(p(fx - size, fy - size, fx + size, fy + size), fill=SKIN, outline=SKIN_SHADE, width=2 * K)
        for i in range(3):  # knuckles, towards the screen
            kx = fx - size * 0.55 + i * size * 0.55
            d.arc(p(kx - 5, fy - size * 0.5, kx + 5, fy + 2), 200, 340, fill=SKIN_SHADE, width=2 * K)
        if near:  # the knock: little lines where the knuckles hit the glass
            for angle in (-50, -15, 20):
                a = math.radians(angle)
                x1, y1 = fx + math.cos(a) * (size + 8), fy + math.sin(a) * (size + 8)
                x2, y2 = fx + math.cos(a) * (size + 20), fy + math.sin(a) * (size + 20)
                d.line([*p(x1, y1), *p(x2, y2)], fill=(90, 110, 140), width=3 * K)

    # Eyebrows
    for x, tilt in ((122, -1), (178, 1)):
        d.arc(p(x - 15, 116 + tilt, x + 15, 134 + tilt), 200, 340, fill=HAIR, width=3 * K)
    # Eyes: big and brown with sparkles, or closed in a blink
    for x in (122, 178):
        if blink:
            d.arc(p(x - 14, 136, x + 14, 156), 20, 160, fill=OUTLINE, width=4 * K)
        else:
            d.ellipse(p(x - 13, 132, x + 13, 166), fill=WHITE)
            d.ellipse(p(x - 11, 135, x + 11, 165), fill=IRIS)
            d.ellipse(p(x - 6, 142, x + 6, 158), fill=PUPIL)
            d.ellipse(p(x - 7, 138, x - 1, 145), fill=WHITE)
            d.ellipse(p(x + 3, 154, x + 6, 157), fill=WHITE)
            d.arc(p(x - 15, 129, x + 15, 160), 195, 345, fill=OUTLINE, width=4 * K)  # lashes
    # Nose, smile, blush
    d.arc(p(146, 162, 154, 172), 20, 160, fill=SKIN_SHADE, width=2 * K)
    d.arc(p(138, 170, 162, 190), 25, 155, fill=LIPS, width=4 * K)
    blush = Image.new("RGBA", im.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(blush)
    for x in (108, 192):
        bd.ellipse(p(x - 12, 168, x + 12, 180), fill=BLUSH)
    im.alpha_composite(blush.filter(ImageFilter.GaussianBlur(2 * K)))
    return im.resize((W, H), Image.LANCZOS)


def knock_sound(path):
    """One soft knock on glass, a short and quickly fading thud (bubble.ps1 plays
    it on each tap of the animation: knock... knock)."""
    rate = 22050
    samples = []
    for start in (0.0,):
        while len(samples) < int(start * rate):
            samples.append(0.0)
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
