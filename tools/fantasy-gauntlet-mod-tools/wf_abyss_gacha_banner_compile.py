#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only binding and validation for the current abyss-gacha banners."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from PIL import Image, UnidentifiedImageError

import wf_abyss_gacha_contract as contract
import wf_assets
import wf_live_cdn


@dataclass(frozen=True)
class BannerSpec:
    root_name: str
    logical_path: str
    size: tuple[int, int]


@dataclass(frozen=True)
class BannerCompilation:
    files: Mapping[str, bytes]
    report: Mapping[str, object]


CURRENT_BANNERS = (
    BannerSpec(
        "upload",
        contract.LIST_BANNER_PAYLOAD_LOGICAL,
        (510, 180),
    ),
    BannerSpec(
        "medium",
        contract.TOP_BANNER_PAYLOAD_LOGICAL,
        (1440, 1789),
    ),
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_rgba(raw: bytes, label: str) -> Image.Image:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            if image.mode != "RGBA":
                raise ValueError(f"{label} must be RGBA; actual={image.mode}")
            return image.copy()
    except UnidentifiedImageError as exc:
        raise ValueError(f"{label} is not a valid PNG") from exc


def load_current_banner_payloads(target_store: Path) -> dict[str, bytes]:
    """Read the two banners from the server-visible CDN/active terminal state."""

    # A package build must start from a freshly replayed server view, not a
    # sub-second cache left by an earlier GUI read.
    wf_live_cdn.clear_cache()
    payloads: dict[str, bytes] = {}
    for spec in CURRENT_BANNERS:
        try:
            current = wf_assets.read_current(Path(target_store), spec.logical_path)
        except wf_live_cdn.LiveCdnError as exc:
            raise ValueError(
                f"cannot replay current CDN/active terminal: {exc}"
            ) from exc
        if current is None:
            raise ValueError(
                "current CDN/active banner is missing: "
                f"{spec.root_name}:{spec.logical_path}"
            )
        root_name, raw, _source = current
        if root_name != spec.root_name:
            raise ValueError(
                "current CDN/active banner root drift: "
                f"{spec.logical_path}; expected={spec.root_name}, actual={root_name}"
            )
        payloads[spec.logical_path] = raw
    return payloads


def compile_current_banners(
    payloads: Mapping[str, bytes],
) -> BannerCompilation:
    """Validate already-published WF PNG bytes and return them unchanged."""

    expected = {spec.logical_path for spec in CURRENT_BANNERS}
    if set(payloads) != expected:
        raise ValueError(
            "current banner payload set is not exact: "
            f"missing={sorted(expected-set(payloads))}, "
            f"extra={sorted(set(payloads)-expected)}"
        )

    files: dict[str, bytes] = {}
    input_hashes: dict[str, str] = {}
    readback: dict[str, dict[str, object]] = {}
    for spec in CURRENT_BANNERS:
        stored = payloads[spec.logical_path]
        if not isinstance(stored, bytes):
            raise ValueError(
                f"current banner payload must be bytes: {spec.logical_path}"
            )
        if not stored.startswith(wf_assets.PNG_FAKE):
            raise ValueError(
                "current banner WF storage signature is absent: "
                f"{spec.logical_path}"
            )
        decoded_raw = wf_assets.png_decode(stored)
        decoded = _load_rgba(decoded_raw, f"decoded {spec.logical_path}")
        if decoded.size != spec.size:
            raise ValueError(
                "current banner dimensions drift: "
                f"{spec.logical_path}; expected={spec.size}, actual={decoded.size}"
            )
        files[spec.logical_path] = stored
        input_hashes[f"{spec.root_name}:{spec.logical_path}"] = _sha(stored)
        readback[spec.logical_path] = {
            "width": decoded.width,
            "height": decoded.height,
            "mode": decoded.mode,
            "pixel_sha256": _sha(decoded.tobytes()),
            "decoded_png_sha256": _sha(decoded_raw),
        }

    return BannerCompilation(files, {
        "schema_version": 2,
        "status": "bound_current_cdn_active_banners",
        "payload_count": len(files),
        "source": "server-current-cdn+active-terminal",
        "input_sha256": input_hashes,
        "output_sha256": {
            logical: _sha(raw) for logical, raw in sorted(files.items())
        },
        "decoded_readback": readback,
        "logical_paths": sorted(files),
        "package_manifest_eligible": True,
        "writes_live": False,
        "formal_workspace_written": False,
    })


__all__ = [
    "BannerSpec", "BannerCompilation", "CURRENT_BANNERS",
    "load_current_banner_payloads", "compile_current_banners",
]
