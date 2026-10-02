"""Native FileReader storage roots for character UI images.

UI PNGs use medium_upload at full image scale, small_upload at 0.7 scale.
Skill cut-ins use independently encoded platform ATFs instead. Their authoring
PNGs may remain common; atlases and battle pixel images are common resources.
"""
from __future__ import annotations


def is_scaled_character_png(logical: str) -> bool:
    return (logical.startswith("character/") and "/ui/" in logical
            and logical.endswith(".png") and "/ui/skill_cutin_" not in logical)


def missing_character_image_roots(logicals, root_paths) -> list[tuple[str, str]]:
    present = set(root_paths)
    return [(root, logical) for logical in logicals
            if is_scaled_character_png(logical)
            for root in ("medium_upload", "small_upload")
            if (root, logical) not in present]
