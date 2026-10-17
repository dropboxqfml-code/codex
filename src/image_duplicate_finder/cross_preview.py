"""Read-only, bounded and lazy previews. Never hand source files to Qt decoders."""

import io

from PIL import Image, ImageOps

from .scanner import SAFE_FORMATS, check_cancel
from .trash import verify_unchanged


def preview_pair(match, cancel):
    outputs = []
    for record in (match.reference, match.target):
        verify_unchanged(record, cancel)
        with Image.open(record.path, formats=SAFE_FORMATS) as source:
            if source.width * source.height > 40_000_000 or getattr(source, "n_frames", 1) != 1:
                raise ValueError("미리보기 리소스 제한을 초과합니다")
            normalized = ImageOps.exif_transpose(source).convert("RGBA")
            check_cancel(cancel)
            visual = Image.new("RGBA", normalized.size, "white")
            visual.alpha_composite(normalized)
            visual = visual.convert("RGB")
            visual.thumbnail((1200, 900))
            output = io.BytesIO()
            visual.save(output, "PNG")
        verify_unchanged(record, cancel)
        outputs.append(output.getvalue())
    return outputs
