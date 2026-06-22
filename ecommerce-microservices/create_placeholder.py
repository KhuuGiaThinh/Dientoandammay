from pathlib import Path

from PIL import Image, ImageDraw


def create_placeholder(text="MON AN", filename="default.jpg", size=(400, 300), bg_color="#FF6B35"):
    img = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size[0], size[1]], fill=bg_color)
    draw.text((size[0] // 2, size[1] // 2), text, fill="white", anchor="mm")

    output_dir = Path("frontend/static/images/foods")
    output_dir.mkdir(parents=True, exist_ok=True)
    img.save(output_dir / filename)


if __name__ == "__main__":
    create_placeholder()
