"""Product images are normalised on upload: square crop, 800×800, WebP (smaller files, fixed dimensions for CLS)."""

import io
import os

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

SIZE = 800
QUALITY = 82


def to_square_webp(uploaded) -> ContentFile:
    uploaded.seek(0)
    with Image.open(uploaded) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
        img = ImageOps.fit(img, (SIZE, SIZE), method=Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, "WEBP", quality=QUALITY, method=6)
    name = os.path.splitext(os.path.basename(uploaded.name))[0] + ".webp"
    return ContentFile(buffer.getvalue(), name=name)
