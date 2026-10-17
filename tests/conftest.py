import pytest
from PIL import Image, ImageDraw


@pytest.fixture
def image_factory(tmp_path):
    def create(name="image.png", variant=0):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (96, 72), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((5 + variant, 8, 53, 55), fill="navy")
        draw.ellipse((35, 20 + variant, 88, 65), fill="orange")
        image.save(path)
        return path

    return create
