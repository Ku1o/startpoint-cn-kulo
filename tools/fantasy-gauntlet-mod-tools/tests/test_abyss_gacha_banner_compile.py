#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Current CDN/active abyss-gacha banner binding tests."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import wf_abyss_gacha_banner_compile as module
import wf_abyss_gacha_contract as contract
import wf_assets


def banner_payloads() -> dict[str, bytes]:
    payloads = {}
    for index, spec in enumerate(module.CURRENT_BANNERS, start=1):
        with Image.new("RGBA", spec.size, (index, index + 1, index + 2, 255)) as image:
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
        payloads[spec.logical_path] = wf_assets.png_encode(output.getvalue())
    return payloads


class AbyssGachaBannerCompileTests(unittest.TestCase):
    def test_binds_current_stored_banners_without_changing_the_bytes(self):
        payloads = banner_payloads()
        result = module.compile_current_banners(payloads)

        self.assertEqual(payloads, result.files)
        self.assertFalse(contract.LIST_BANNER_LOGICAL.endswith(".png"))
        self.assertEqual(
            f"{contract.LIST_BANNER_LOGICAL}.png",
            contract.LIST_BANNER_PAYLOAD_LOGICAL,
        )
        for logical, payload in result.files.items():
            self.assertTrue(payload.startswith(wf_assets.PNG_FAKE))
            with Image.open(io.BytesIO(wf_assets.png_decode(payload))) as image:
                image.load()
                self.assertEqual(
                    hashlib.sha256(image.tobytes()).hexdigest(),
                    result.report["decoded_readback"][logical]["pixel_sha256"],
                )
        self.assertEqual("bound_current_cdn_active_banners", result.report["status"])
        self.assertEqual(2, result.report["payload_count"])
        self.assertTrue(result.report["package_manifest_eligible"])
        self.assertFalse(result.report["writes_live"])

    def test_reads_each_banner_from_its_authoritative_current_root(self):
        payloads = banner_payloads()
        by_logical = {
            spec.logical_path: (
                spec.root_name,
                payloads[spec.logical_path],
                "current-terminal.zip!payload",
            )
            for spec in module.CURRENT_BANNERS
        }
        with (
            tempfile.TemporaryDirectory() as temporary_name,
            mock.patch.object(
                module.wf_assets,
                "read_current",
                side_effect=lambda _store, logical: by_logical[logical],
            ) as read_current,
        ):
            actual = module.load_current_banner_payloads(Path(temporary_name))
        self.assertEqual(payloads, actual)
        self.assertEqual(2, read_current.call_count)

    def test_rejects_wrong_root_signature_dimensions_and_payload_set(self):
        payloads = banner_payloads()
        first, second = module.CURRENT_BANNERS
        with (
            tempfile.TemporaryDirectory() as temporary_name,
            mock.patch.object(
                module.wf_assets,
                "read_current",
                return_value=("medium", payloads[first.logical_path], "wrong"),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "root drift"):
                module.load_current_banner_payloads(Path(temporary_name))

        changed = dict(payloads)
        changed[first.logical_path] = b"not stored PNG"
        with self.assertRaisesRegex(ValueError, "signature"):
            module.compile_current_banners(changed)

        with Image.new("RGBA", (10, 10), (1, 2, 3, 255)) as image:
            output = io.BytesIO()
            image.save(output, format="PNG")
        changed = dict(payloads)
        changed[second.logical_path] = wf_assets.png_encode(output.getvalue())
        with self.assertRaisesRegex(ValueError, "dimensions"):
            module.compile_current_banners(changed)

        changed.pop(second.logical_path)
        with self.assertRaisesRegex(ValueError, "payload set"):
            module.compile_current_banners(changed)


if __name__ == "__main__":
    unittest.main()
