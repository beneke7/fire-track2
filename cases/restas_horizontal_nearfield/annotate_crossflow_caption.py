#!/usr/bin/env python3
"""Correct the legacy still-air title on this case's computed VOF render.

The shared Restas renderer predates the uniform +y crossflow field. This helper
preserves its computed pixels and style, replacing only the second caption line
in the top margin and writing a separate PNG and JSON record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_png", type=Path)
    args = parser.parse_args()
    source = args.input_png.resolve()
    if source.suffix.lower() != ".png" or not source.is_file():
        parser.error("input_png must name an existing PNG render")
    source_record = source.with_suffix(".json")
    if not source_record.is_file():
        parser.error(f"missing renderer record: {source_record}")

    output = source.with_name(f"{source.stem}-crossflow.png")
    record_path = output.with_suffix(".json")
    if output.exists() or record_path.exists():
        parser.error(f"refusing to overwrite existing output: {output}")

    image = Image.open(source).convert("RGB")
    draw = ImageDraw.Draw(image)
    # The established renderer uses this matte background and dark blue text.
    # Cover only its inaccurate second line; alpha.water pixels begin much lower.
    draw.rectangle((0, 29, image.width, 63), fill="#f7f9fc")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-ExtraLight.ttf", 30)
    caption = "Crossflow air: 2 m/s in +y · exploratory mesh"
    draw.text((2, 27), caption, font=font, fill="#182338")
    image.save(output)

    record = json.loads(source_record.read_text(encoding="utf-8"))
    record["output_png"] = str(output)
    record["output_sha256"] = sha256(output)
    record["caption_correction"] = {
        "source_png": str(source),
        "source_png_sha256": sha256(source),
        "replaced_region_px": [0, 29, image.width, 63],
        "caption": caption,
        "reason": "The case has uniform +y crossflow; the shared renderer's legacy still-air caption is inaccurate.",
        "water_surface_pixels_changed": False,
    }
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Record {record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
