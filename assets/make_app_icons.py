"""Draws the phone app's icons from the HireAce mark (agent/frontend): the install
icons, the maskable one (Android crops it to a circle or squircle, so the mark sits
inside the middle 80%) and the iPhone home-screen icon. Run: python make_app_icons.py"""

from pathlib import Path

from PIL import Image, ImageDraw

NAVY, BLUE = "#0f172a", "#2f6bff"
WEB = Path(__file__).parent.parent / "agent" / "frontend"


def mark(size: int, rounded: bool, inset: float = 0.0) -> Image.Image:
    big = size * 4
    k = big * (1 - 2 * inset) / 64  # the mark is drawn on a 64-unit grid
    off = big * inset
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if rounded:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=big * 14 / 64, fill=NAVY)
    else:
        d.rectangle([0, 0, big, big], fill=NAVY)

    def p(x, y):
        return (off + x * k, off + y * k)

    d.ellipse([*p(26.5, 9.5), *p(37.5, 20.5)], fill=BLUE)
    d.line([p(18, 52), p(32, 25), p(46, 52)], fill="white", width=int(6 * k), joint="curve")
    d.line([p(24.5, 42), p(39.5, 42)], fill="white", width=int(6 * k))
    return im.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    for size in (192, 512):
        mark(size, rounded=True).save(WEB / "public" / "icons" / f"icon-{size}.png")
    mark(512, rounded=False, inset=0.12).save(WEB / "public" / "icons" / "maskable-512.png")
    # iPhone rounds the corners itself and shows transparency as black
    mark(180, rounded=False, inset=0.06).convert("RGB").save(WEB / "app" / "apple-icon.png")
