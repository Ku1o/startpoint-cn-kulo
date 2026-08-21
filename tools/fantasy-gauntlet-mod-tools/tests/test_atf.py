# -*- coding: utf-8 -*-
"""wf_atf 回归测试(纯标准库,合成数据,不碰真实 store)。

覆盖:PNG 编解码往返、ETC1 编码→解码质量、ATF 容器结构(与官方 cutin 文件
逐字节同构:新版头 / format 0x05 / 每级 4 槽仅 ETC1 / 颜色+alpha 直拼)、
尺寸校验。比特布局已用官方 alice skill_cutin ATF 对拍验证(平均误差 2.80,
即官方编码器自身损耗水平)。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wf_atf  # noqa: E402


def _gradient_rgba(w: int, h: int) -> bytearray:
    rgba = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            o = (y * w + x) * 4
            rgba[o] = x * 255 // (w - 1)
            rgba[o + 1] = y * 255 // (h - 1)
            rgba[o + 2] = (x + y) * 255 // (w + h - 2)
            rgba[o + 3] = 255 if x < w // 2 else (w - 1 - x) * 255 // (w // 2)
    return rgba


class TestPngRoundtrip(unittest.TestCase):
    def test_rgba_roundtrip(self):
        w, h = 32, 16
        rgba = _gradient_rgba(w, h)
        png = wf_atf.png_encode_rgba(w, h, bytes(rgba))
        w2, h2, back = wf_atf.png_decode_rgba(png)
        self.assertEqual((w2, h2), (w, h))
        self.assertEqual(back, rgba)

    def test_reject_bad_magic(self):
        with self.assertRaises(ValueError):
            wf_atf.png_decode_rgba(b"not a png at all")


class TestEtc1(unittest.TestCase):
    def test_encode_decode_quality(self):
        """渐变图编码→解码平均误差应在修正表步长量级内。"""
        w, h = 64, 32
        rgba = _gradient_rgba(w, h)
        data = wf_atf.encode_etc1(rgba, w, h, "rgb")
        self.assertEqual(len(data), (w // 4) * (h // 4) * 8)
        dec = wf_atf.decode_etc1(data, w, h)
        n = w * h
        err = sum(abs(dec[i * 3 + c] - rgba[i * 4 + c])
                  for i in range(n) for c in range(3)) / (n * 3)
        self.assertLess(err, 8, f"ETC1 颜色编码质量异常: {err:.2f}")

    def test_flat_block_exact(self):
        """纯色块必须近乎无损(alpha 掩码大面积依赖此路径)。"""
        w, h = 8, 8
        rgba = bytearray(bytes((170, 170, 170, 255)) * (w * h))
        dec = wf_atf.decode_etc1(wf_atf.encode_etc1(rgba, w, h, "rgb"), w, h)
        err = max(abs(dec[i] - 170) for i in range(w * h * 3))
        self.assertLessEqual(err, 2)


class TestEacAlpha(unittest.TestCase):
    def test_encode_decode_quality(self):
        w, h = 64, 32
        rgba = _gradient_rgba(w, h)
        data = wf_atf.encode_eac_alpha(rgba, w, h)
        self.assertEqual(len(data), (w // 4) * (h // 4) * 8)
        decoded = wf_atf.decode_eac_alpha(data, w, h)
        err = sum(abs(decoded[i] - rgba[i * 4 + 3]) for i in range(w * h)) / (w * h)
        self.assertLess(err, 6, f"EAC alpha 编码质量异常: {err:.2f}")

    def test_flat_alpha_is_exact(self):
        w, h = 8, 8
        rgba = bytearray(bytes((20, 40, 80, 137)) * (w * h))
        decoded = wf_atf.decode_eac_alpha(wf_atf.encode_eac_alpha(rgba, w, h), w, h)
        self.assertLessEqual(max(abs(value - 137) for value in decoded), 1)


class TestAtfContainer(unittest.TestCase):
    def test_build_parse_roundtrip(self):
        w, h = 64, 32
        png = wf_atf.png_encode_rgba(w, h, bytes(_gradient_rgba(w, h)))
        atf = wf_atf.build_cutin_atf(png)
        self.assertEqual(atf[:8], wf_atf.ATF_HEAD8)
        self.assertEqual(int.from_bytes(atf[8:12], "big"), len(atf) - 12)
        p = wf_atf.parse_atf(atf)
        self.assertEqual((p["w"], p["h"]), (w, h))
        self.assertEqual(p["mips"], 7)  # max(log2 64, log2 32) + 1
        # 每级 = 颜色+alpha 两段 ETC1;块数按 ceil(边/4),最小 1
        for lv, pair in enumerate(p["pairs"]):
            mw, mh = max(w >> lv, 1), max(h >> lv, 1)
            nb = max((mw + 3) // 4, 1) * max((mh + 3) // 4, 1)
            self.assertEqual(len(pair), nb * 16, f"mip{lv} 长度不对")

    def test_ref_dims_mismatch_rejected(self):
        png32 = wf_atf.png_encode_rgba(32, 16, bytes(_gradient_rgba(32, 16)))
        ref = wf_atf.build_cutin_atf(
            wf_atf.png_encode_rgba(64, 32, bytes(_gradient_rgba(64, 32))))
        with self.assertRaises(ValueError):
            wf_atf.build_cutin_atf(png32, ref)

    def test_non_pot_rejected(self):
        png = wf_atf.png_encode_rgba(48, 32, bytes(_gradient_rgba(48, 32)))
        with self.assertRaises(ValueError):
            wf_atf.build_cutin_atf(png)

    def test_build_ios_etc2_interleaves_alpha_and_color(self):
        w, h = 64, 32
        png = wf_atf.png_encode_rgba(w, h, bytes(_gradient_rgba(w, h)))
        atf = wf_atf.build_cutin_atf_ios(png)
        parsed = wf_atf.parse_atf(atf)
        self.assertEqual(parsed["slot"], 3)
        self.assertEqual(parsed["layout"], "etc2-rgba")
        self.assertEqual(parsed["mips"], 7)
        for level, payload in enumerate(parsed["pairs"]):
            mw, mh = max(w >> level, 1), max(h >> level, 1)
            blocks = max((mw + 3) // 4, 1) * max((mh + 3) // 4, 1)
            self.assertEqual(len(payload), blocks * 16)
        source = _gradient_rgba(w, h)
        decoded = wf_atf.decode_etc2_rgba(parsed["pairs"][0], w, h)
        alpha_err = sum(
            abs(decoded[i * 4 + 3] - source[i * 4 + 3])
            for i in range(w * h)
        ) / (w * h)
        self.assertLess(alpha_err, 6)

    def test_platform_pair_validation_rejects_android_copy(self):
        w, h = 16, 8
        png = wf_atf.png_encode_rgba(w, h, bytes(_gradient_rgba(w, h)))
        android = wf_atf.build_cutin_atf(png)
        ios = wf_atf.build_cutin_atf_ios(png, android)
        report = wf_atf.validate_cutin_platform_pair(android, ios, png)
        self.assertEqual(report["android_slot"], 2)
        self.assertEqual(report["ios_slot"], 3)
        with self.assertRaisesRegex(ValueError, "直接复制"):
            wf_atf.validate_cutin_platform_pair(android, android, png)

    def test_platform_pair_builder_uses_one_png_and_distinct_slots(self):
        w, h = 16, 8
        png = wf_atf.png_encode_rgba(w, h, bytes(_gradient_rgba(w, h)))
        android, ios = wf_atf.build_cutin_platform_pair(png)
        self.assertNotEqual(android, ios)
        self.assertEqual(wf_atf.parse_atf(android)["slot"], 2)
        self.assertEqual(wf_atf.parse_atf(ios)["slot"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
