"""Draws the minimized-panel mascot (bubble.ps1): the HireAce mark as a little
round agent, with the logo's blue dot as its antenna. Run: python make_bubble.py"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

NAVY, BLUE, WHITE = "#0f172a", "#2f6bff", "#ffffff"
S = 768  # drawn large, saved at 192 px for smooth edges
OUT = Path(__file__).parent


def frame(blink: bool) -> Image.Image:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # Soft shadow under the body, so it floats over the desktop
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([150, 250, 618, 718], fill=(0, 0, 0, 110))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(28)))
    d = ImageDraw.Draw(im)
    # Antenna: the logo's blue dot on a short stem
    d.rounded_rectangle([372, 120, 396, 230], radius=12, fill=NAVY)
    d.ellipse([336, 64, 432, 160], fill=BLUE)
    d.ellipse([360, 84, 384, 108], fill=(255, 255, 255, 140))  # shine
    # Body and face screen
    d.ellipse([132, 200, 636, 704], fill=NAVY)
    d.rounded_rectangle([206, 330, 562, 580], radius=110, fill="#1e3a8a")
    # Eyes
    if blink:
        for x in (300, 468):
            d.rounded_rectangle([x - 38, 444, x + 38, 462], radius=9, fill=WHITE)
    else:
        for x in (300, 468):
            d.ellipse([x - 34, 404, x + 34, 500], fill=WHITE)
            d.ellipse([x - 4, 418, x + 20, 442], fill=BLUE)
    # Smile and cheeks
    d.arc([336, 470, 432, 540], start=20, end=160, fill=WHITE, width=16)
    for x in (238, 530):
        d.ellipse([x - 26, 512, x + 26, 544], fill=(255, 140, 180, 150))
    return im.resize((192, 192), Image.LANCZOS)


if __name__ == "__main__":
    frame(False).save(OUT / "bubble.png")
    frame(True).save(OUT / "bubble-blink.png")
