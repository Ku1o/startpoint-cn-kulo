#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wf_atf — skill_cutin 的 ATF(ETC1/ETC2)纹理重编码器(纯标准库)。

背景(FileReader.as 逆向):`/ui/skill_cutin_` 是全客户端唯一的「平台相关」资产,
真机(assetReadKind≠0/3)渲染只读 `skill_cutin_N.atf.deflate`(Android/iOS 平台根),
不读同名 PNG(medium 根,仅编辑器/特定模式用)。因此替换 cut-in 必须连 ATF
一起重生成,否则游戏内无变化——立绘等其他资产没有 ATF 配对,换 PNG 即生效。

原始 ATF 实测(alice, 1024x512):
  头 16B: 'ATF' 00 00 01 FF 03 | u32(总长-12) | format(0x05) log2w log2h mip数
  format 0x05 = RAW Compressed With Alpha,全 mip 链(11 级);
  每级 4 个平台槽 [DXT5, PVRTC, ETC1, ETC2](u32 长度前缀),Android 文件仅 ETC1 槽有数据,
  内容 = [颜色纹理][alpha 纹理] 两段 ETC1 直拼(8B/4x4 块,alpha 以灰度编码)。

Android 编码器:individual 模式(RGB444 基色)+ 8 张修正表全搜(亮度残差)+
flip 启发式。iOS 编码器:ETC2 RGBA 的 EAC alpha 块 + ETC1 兼容颜色块,
按每个 4x4 块交错排列。两者都使用块级缓存(实测官方图 50-75% 块重复)。
质量弱于官方 png2atf(无差分模式/穷举),但块内误差处于修正表步长量级;
alpha 掩码几乎无损。

用法:
  python wf_atf.py --selftest
  python wf_atf.py --regen character/alice/ui/skill_cutin_0.png   # 从 store 现有 PNG 重生成(备份+进 pending)
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ATF_HEAD8 = b"ATF\x00\x00\x01\xff\x03"  # 新版头 + ATF v3(与官方 cutin 文件逐字节一致)
# ETC1 修正表(Khronos OES_compressed_ETC1_RGB8):每表 (小步长 a, 大步长 b),
# 像素 2bit 索引 (msb,lsb): 00=+a 01=+b 10=-a 11=-b
_MODS = ((2, 8), (5, 17), (9, 29), (13, 42), (18, 60), (24, 80), (33, 106), (47, 183))
# ETC2 RGBA alpha 的 16 张修正表。与 Khronos/ANGLE 的 unsigned 8-bit
# alpha 解码表一致；alpha 值 = clamp(base + modifier * multiplier, 0, 255)。
_EAC_ALPHA_MODS = (
    (-3, -6, -9, -15, 2, 5, 8, 14),
    (-3, -7, -10, -13, 2, 6, 9, 12),
    (-2, -5, -8, -13, 1, 4, 7, 12),
    (-2, -4, -6, -13, 1, 3, 5, 12),
    (-3, -6, -8, -12, 2, 5, 7, 11),
    (-3, -7, -9, -11, 2, 6, 8, 10),
    (-4, -7, -8, -11, 3, 6, 7, 10),
    (-3, -5, -8, -11, 2, 4, 7, 10),
    (-2, -6, -8, -10, 1, 5, 7, 9),
    (-2, -5, -8, -10, 1, 4, 7, 9),
    (-2, -4, -8, -10, 1, 3, 7, 9),
    (-2, -5, -7, -10, 1, 4, 6, 9),
    (-3, -4, -7, -10, 2, 3, 6, 9),
    (-1, -2, -3, -10, 0, 1, 2, 9),
    (-4, -6, -8, -9, 3, 5, 7, 8),
    (-3, -5, -7, -9, 2, 4, 6, 8),
)
_SUB_FLIP0 = (tuple(range(8)), tuple(range(8, 16)))              # 两个 2x4 竖条(i = x*4+y)
_SUB_FLIP1 = (tuple(i for i in range(16) if i % 4 < 2),          # 两个 4x2 横条
              tuple(i for i in range(16) if i % 4 >= 2))


def inflate(data: bytes) -> bytes:
    return zlib.decompress(data, -15)


def deflate(data: bytes) -> bytes:
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return co.compress(data) + co.flush()


# ---------------------------------------------------------------- PNG 解码/编码

def png_decode_rgba(data: bytes) -> tuple[int, int, bytearray]:
    """标准 PNG → (w, h, RGBA bytearray)。仅 8-bit 非隔行(常规导出即满足)。"""
    if data[:8] != PNG_MAGIC:
        raise ValueError("不是标准 PNG(魔数不对)")
    pos = 8
    w = h = bitd = ct = interlace = None
    idat = bytearray()
    plte = b""
    trns = b""
    while pos + 8 <= len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        pos += 8
        chunk = data[pos:pos + ln]
        pos += ln + 4  # 跳过 CRC
        if typ == b"IHDR":
            w, h, bitd, ct, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"PLTE":
            plte = chunk
        elif typ == b"tRNS":
            trns = chunk
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
    if w is None:
        raise ValueError("PNG 缺 IHDR")
    if bitd != 8:
        raise ValueError(f"仅支持 8-bit PNG(实际 {bitd}-bit),请用普通方式重新导出")
    if interlace:
        raise ValueError("不支持隔行扫描(interlaced)PNG,请重新导出")
    nch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ct)
    if nch is None:
        raise ValueError(f"不支持的 PNG 颜色类型 {ct}")
    raw = zlib.decompress(bytes(idat))
    stride = w * nch
    if len(raw) < (stride + 1) * h:
        raise ValueError("PNG 像素数据不完整")
    out = bytearray(w * h * nch)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                pa = abs(b - c)
                pb = abs(a - c)
                pc = abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        elif f != 0:
            raise ValueError(f"未知 PNG filter {f}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    rgba = bytearray(w * h * 4)
    if ct == 6:
        rgba[:] = out
    elif ct == 2:
        for i in range(w * h):
            rgba[4 * i:4 * i + 3] = out[3 * i:3 * i + 3]
            rgba[4 * i + 3] = 255
    elif ct == 0:
        for i in range(w * h):
            g = out[i]
            rgba[4 * i] = rgba[4 * i + 1] = rgba[4 * i + 2] = g
            rgba[4 * i + 3] = 255
    elif ct == 4:
        for i in range(w * h):
            g = out[2 * i]
            rgba[4 * i] = rgba[4 * i + 1] = rgba[4 * i + 2] = g
            rgba[4 * i + 3] = out[2 * i + 1]
    else:  # ct == 3 调色板
        if not plte:
            raise ValueError("调色板 PNG 缺 PLTE")
        for i in range(w * h):
            j = out[i] * 3
            rgba[4 * i:4 * i + 3] = plte[j:j + 3]
            rgba[4 * i + 3] = trns[out[i]] if out[i] < len(trns) else 255
    return w, h, rgba


def png_encode_rgba(w: int, h: int, rgba: bytes) -> bytes:
    """RGBA → 标准 PNG(filter 0,测试/预览用)。"""
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(typ: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + typ + body + struct.pack(
            ">I", zlib.crc32(typ + body) & 0xFFFFFFFF)

    return (PNG_MAGIC + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- mip 链

def half_rgba(rgba: bytearray, w: int, h: int) -> tuple[int, int, bytearray]:
    """2x2 均值降采样(边长 1 时该轴保持)。"""
    nw, nh = max(w // 2, 1), max(h // 2, 1)
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        y0 = min(2 * y, h - 1) * w
        y1 = min(2 * y + 1, h - 1) * w
        ro = y * nw * 4
        for x in range(nw):
            x0 = min(2 * x, w - 1)
            x1 = min(2 * x + 1, w - 1)
            for c in range(4):
                out[ro + x * 4 + c] = (rgba[(y0 + x0) * 4 + c] + rgba[(y0 + x1) * 4 + c]
                                       + rgba[(y1 + x0) * 4 + c] + rgba[(y1 + x1) * 4 + c]) >> 2
    return nw, nh, out


# ---------------------------------------------------------------- ETC1 编码

def _enc_sub(px: list, idxs: tuple) -> tuple:
    """单子块:均值基色(RGB444)+ 8 修正表全搜亮度残差。返回 (r4,g4,b4,表号,2bit索引列表)。"""
    n = len(idxs)
    sr = sg = sb = 0
    for i in idxs:
        p = px[i]
        sr += p[0]
        sg += p[1]
        sb += p[2]
    r4 = (sr * 15 + n * 127) // (n * 255)
    g4 = (sg * 15 + n * 127) // (n * 255)
    b4 = (sb * 15 + n * 127) // (n * 255)
    base = (r4 + g4 + b4) * 17  # 亮度和(重建值 = c4*17)
    d = [px[i][0] + px[i][1] + px[i][2] - base for i in idxs]  # 3x 亮度残差
    best_err = 1 << 30
    best_k = 0
    best_cl = None
    for k in range(8):
        a, b = _MODS[k]
        a3, b3 = a * 3, b * 3
        err = 0
        cl = []
        for dv in d:
            e0 = dv - a3
            if e0 < 0:
                e0 = -e0
            e1 = dv - b3
            if e1 < 0:
                e1 = -e1
            e2 = dv + a3
            if e2 < 0:
                e2 = -e2
            e3 = dv + b3
            if e3 < 0:
                e3 = -e3
            if e0 <= e1 and e0 <= e2 and e0 <= e3:
                cl.append(0)
                err += e0
            elif e1 <= e2 and e1 <= e3:
                cl.append(1)
                err += e1
            elif e2 <= e3:
                cl.append(2)
                err += e2
            else:
                cl.append(3)
                err += e3
        if err < best_err:
            best_err, best_k, best_cl = err, k, cl
            if err == 0:
                break
    return r4, g4, b4, best_k, best_cl


def _encode_block(px: list) -> bytes:
    """一个 4x4 块(px[i], i = x*4+y)→ 8 字节 ETC1(individual 模式)。"""
    lum = [p[0] + p[1] + p[2] for p in px]
    c0 = abs(sum(lum[i] for i in _SUB_FLIP0[0]) - sum(lum[i] for i in _SUB_FLIP0[1]))
    c1 = abs(sum(lum[i] for i in _SUB_FLIP1[0]) - sum(lum[i] for i in _SUB_FLIP1[1]))
    flip = 0 if c0 >= c1 else 1
    subs = _SUB_FLIP0 if flip == 0 else _SUB_FLIP1
    r1, g1, b1, k1, cl1 = _enc_sub(px, subs[0])
    r2, g2, b2, k2, cl2 = _enc_sub(px, subs[1])
    msb = lsb = 0
    for idxs, cl in ((subs[0], cl1), (subs[1], cl2)):
        for i, c in zip(idxs, cl):
            msb |= ((c >> 1) & 1) << i
            lsb |= (c & 1) << i
    return bytes(((r1 << 4) | r2, (g1 << 4) | g2, (b1 << 4) | b2,
                  (k1 << 5) | (k2 << 2) | flip,
                  (msb >> 8) & 255, msb & 255, (lsb >> 8) & 255, lsb & 255))


def encode_etc1(rgba: bytearray, w: int, h: int, channel: str = "rgb") -> bytes:
    """整张纹理 → ETC1 字节。channel='rgb' 颜色纹理;'alpha' 用 A 通道灰度。"""
    nbx = max((w + 3) // 4, 1)
    nby = max((h + 3) // 4, 1)
    out = bytearray()
    cache: dict[bytes, bytes] = {}
    alpha = channel == "alpha"
    for by in range(nby):
        for bx in range(nbx):
            px = []
            for x in range(4):
                cx = min(bx * 4 + x, w - 1)
                for y in range(4):
                    cy = min(by * 4 + y, h - 1)
                    o = (cy * w + cx) * 4
                    if alpha:
                        a = rgba[o + 3]
                        px.append((a, a, a))
                    else:
                        px.append((rgba[o], rgba[o + 1], rgba[o + 2]))
            key = bytes(v for p in px for v in p)
            blk = cache.get(key)
            if blk is None:
                blk = _encode_block(px)
                cache[key] = blk
            out += blk
    return bytes(out)


def _encode_eac_alpha_block(values: tuple[int, ...]) -> bytes:
    """编码一个 ETC2 RGBA alpha 4x4 块。

    对每个(table, multiplier)用最小二乘意义下的基值估计，再在基值邻域
    选择最佳 selector。这个编码器只负责生成标准、可被 ETC2 解码器读取的
    alpha 块；质量目标是角色 cut-in 的透明边缘和大面积透明区稳定可用。
    """
    best_err = 1 << 60
    best_base = 0
    best_table = 0
    best_multiplier = 0
    best_indices: tuple[int, ...] = ()
    for table_index, modifiers in enumerate(_EAC_ALPHA_MODS):
        for multiplier in range(16):
            # selector 的最佳分配取决于 base，先用块均值作为稳定的基值估计，
            # 再在其邻域试探；alpha 修正表的 selector 集合整体接近对称。
            estimate = (sum(values) + 8) // 16
            candidates = {
                max(0, min(255, estimate - 1)),
                max(0, min(255, estimate)),
                max(0, min(255, estimate + 1)),
            }
            for base in candidates:
                error = 0
                indices = []
                for value in values:
                    target = value - base
                    index = min(
                        range(8),
                        key=lambda candidate: abs(target - modifiers[candidate] * multiplier),
                    )
                    decoded = max(0, min(255, base + modifiers[index] * multiplier))
                    error += (value - decoded) ** 2
                    indices.append(index)
                if error < best_err:
                    best_err = error
                    best_base = base
                    best_table = table_index
                    best_multiplier = multiplier
                    best_indices = tuple(indices)
                    if error == 0:
                        break
            if best_err == 0:
                break
        if best_err == 0:
            break

    packed = 0
    for index, selector in enumerate(best_indices):
        packed |= selector << (45 - index * 3)
    return bytes((best_base, (best_table << 4) | best_multiplier)) + packed.to_bytes(6, "big")


def encode_eac_alpha(rgba: bytearray, w: int, h: int) -> bytes:
    """整张 RGBA 纹理的 ETC2 8-bit alpha 块流。"""
    nbx = max((w + 3) // 4, 1)
    nby = max((h + 3) // 4, 1)
    out = bytearray()
    cache: dict[bytes, bytes] = {}
    for by in range(nby):
        for bx in range(nbx):
            values = []
            for x in range(4):
                cx = min(bx * 4 + x, w - 1)
                for y in range(4):
                    cy = min(by * 4 + y, h - 1)
                    values.append(rgba[(cy * w + cx) * 4 + 3])
            key = bytes(values)
            block = cache.get(key)
            if block is None:
                block = _encode_eac_alpha_block(tuple(values))
                cache[key] = block
            out += block
    return bytes(out)


# ---------------------------------------------------------------- ETC1 解码(验证用)

def decode_etc1(data: bytes, w: int, h: int) -> bytearray:
    """ETC1 → RGB bytearray(w*h*3)。用于自检与对拍官方文件。"""
    out = bytearray(w * h * 3)
    nbx = max((w + 3) // 4, 1)
    bi = 0
    for off in range(0, len(data), 8):
        b = data[off:off + 8]
        bx, by = bi % nbx, bi // nbx
        bi += 1
        flip = b[3] & 1
        k1, k2 = b[3] >> 5, (b[3] >> 2) & 7
        if (b[3] >> 1) & 1:  # differential 模式(官方文件可能用;自产不用)
            r1 = b[0] >> 3
            g1 = b[1] >> 3
            b1 = b[2] >> 3
            dr = (b[0] & 7) - ((b[0] & 4) << 1)
            dg = (b[1] & 7) - ((b[1] & 4) << 1)
            db = (b[2] & 7) - ((b[2] & 4) << 1)
            base1 = ((r1 << 3) | (r1 >> 2), (g1 << 3) | (g1 >> 2), (b1 << 3) | (b1 >> 2))
            r2, g2, b2 = r1 + dr, g1 + dg, b1 + db
            base2 = ((r2 << 3) | (r2 >> 2), (g2 << 3) | (g2 >> 2), (b2 << 3) | (b2 >> 2))
        else:
            base1 = ((b[0] >> 4) * 17, (b[1] >> 4) * 17, (b[2] >> 4) * 17)
            base2 = ((b[0] & 15) * 17, (b[1] & 15) * 17, (b[2] & 15) * 17)
        msb = (b[4] << 8) | b[5]
        lsb = (b[6] << 8) | b[7]
        subs = _SUB_FLIP0 if flip == 0 else _SUB_FLIP1
        for si, idxs in enumerate(subs):
            base = base1 if si == 0 else base2
            a, bb = _MODS[k1 if si == 0 else k2]
            for i in idxs:
                c = (((msb >> i) & 1) << 1) | ((lsb >> i) & 1)
                m = (a, bb, -a, -bb)[c]
                x, y = bx * 4 + i // 4, by * 4 + i % 4
                if x >= w or y >= h:
                    continue
                o = (y * w + x) * 3
                for ch in range(3):
                    v = base[ch] + m
                    out[o + ch] = 0 if v < 0 else (255 if v > 255 else v)
    return out


def decode_eac_alpha(data: bytes, w: int, h: int) -> bytearray:
    """ETC2 alpha 块流 → 8-bit alpha 平面(验证用)。"""
    nbx = max((w + 3) // 4, 1)
    nby = max((h + 3) // 4, 1)
    expected = nbx * nby * 8
    if len(data) != expected:
        raise ValueError(f"EAC alpha 长度 {len(data)} != 预期 {expected}")
    out = bytearray(w * h)
    for block_index in range(nbx * nby):
        block = data[block_index * 8:(block_index + 1) * 8]
        base = block[0]
        table_index = block[1] >> 4
        multiplier = block[1] & 0x0F
        packed = int.from_bytes(block[2:8], "big")
        bx = block_index % nbx
        by = block_index // nbx
        for index in range(16):
            selector = (packed >> (45 - index * 3)) & 7
            value = max(0, min(255, base + _EAC_ALPHA_MODS[table_index][selector] * multiplier))
            x = bx * 4 + index // 4
            y = by * 4 + index % 4
            if x < w and y < h:
                out[y * w + x] = value
    return out


def decode_etc2_rgba(data: bytes, w: int, h: int) -> bytearray:
    """解码本工具生成的 ETC2 RGBA(每块 alpha+color 交错)用于回归测试。"""
    nbx = max((w + 3) // 4, 1)
    nby = max((h + 3) // 4, 1)
    expected = nbx * nby * 16
    if len(data) != expected:
        raise ValueError(f"ETC2 RGBA 长度 {len(data)} != 预期 {expected}")
    out = bytearray(w * h * 4)
    for block_index in range(nbx * nby):
        alpha = decode_eac_alpha(data[block_index * 16:block_index * 16 + 8], 4, 4)
        color = decode_etc1(data[block_index * 16 + 8:block_index * 16 + 16], 4, 4)
        bx = block_index % nbx
        by = block_index // nbx
        for index in range(16):
            x = bx * 4 + index // 4
            y = by * 4 + index % 4
            if x < w and y < h:
                dst = (y * w + x) * 4
                block_x = index // 4
                block_y = index % 4
                src = (block_y * 4 + block_x) * 3
                out[dst:dst + 3] = color[src:src + 3]
                out[dst + 3] = alpha[block_y * 4 + block_x]
    return out


# ---------------------------------------------------------------- ATF 容器

def parse_atf(data: bytes) -> dict:
    """解析 cutin 型 ATF，支持 Android ETC1 槽和 iOS ETC2 槽。"""
    if data[:3] != b"ATF" or len(data) < 16 or data[6] != 0xFF:
        raise ValueError("不是新版头 ATF 文件")
    fmt = data[12]
    if fmt & 0x7F != 0x05:
        raise ValueError(f"ATF format=0x{fmt:02x},仅支持 0x05 RAW Compressed With Alpha")
    w, h, mips = 1 << data[13], 1 << data[14], data[15]
    o = 16
    pairs = []
    slot = None
    layout = None
    for _ in range(mips):
        row = []
        for _s in range(4):
            if o + 4 > len(data):
                raise ValueError("ATF 槽长度字段被截断")
            ln = int.from_bytes(data[o:o + 4], "big")
            if o + 4 + ln > len(data):
                raise ValueError("ATF 槽数据被截断")
            row.append(data[o + 4:o + 4 + ln])
            o += 4 + ln
        populated = [index for index, value in enumerate(row) if value]
        if populated == [2]:
            current_slot, current_layout = 2, "etc1"
        elif populated == [3]:
            current_slot, current_layout = 3, "etc2-rgba"
        elif not populated:
            current_slot, current_layout = slot, layout
        else:
            raise ValueError("ATF 同时包含多个平台槽，无法识别 cut-in 布局")
        if slot is None:
            slot, layout = current_slot, current_layout
        elif (current_slot, current_layout) != (slot, layout):
            raise ValueError("ATF 各 mip 的平台槽不一致")
        pairs.append(row[slot] if slot is not None else b"")
    if slot is None:
        raise ValueError("ATF 没有任何平台纹理数据")
    if o != len(data):
        raise ValueError(f"ATF 尾部有 {len(data) - o} 字节未解析数据")
    return {"w": w, "h": h, "mips": mips, "pairs": pairs,
            "slot": slot, "layout": layout}


def build_cutin_atf(png_data: bytes, ref_atf: bytes | None = None,
                    progress=None) -> bytes:
    """标准 PNG → cutin 型 ATF(RAW Compressed With Alpha,ETC1 颜色+alpha,全 mip 链)。

    ref_atf 提供时校验尺寸一致并沿用其 mip 数;否则按尺寸生成完整 mip 链。"""
    w, h, rgba = png_decode_rgba(png_data)
    if w & (w - 1) or h & (h - 1):
        raise ValueError(f"ATF 要求边长为 2 的幂,PNG 是 {w}x{h}")
    mips = max(w.bit_length(), h.bit_length())
    if ref_atf is not None:
        ref = parse_atf(ref_atf)
        if (ref["w"], ref["h"]) != (w, h):
            raise ValueError(f"PNG 尺寸 {w}x{h} 与原 ATF {ref['w']}x{ref['h']} 不一致"
                             f"(cut-in 必须同尺寸替换)")
        mips = ref["mips"]
    body = bytearray()
    cw, ch, cur = w, h, rgba
    zero4 = (0).to_bytes(4, "big")
    for lv in range(mips):
        if progress:
            progress(f"ETC1 编码 mip{lv} {cw}x{ch}")
        pair = encode_etc1(cur, cw, ch, "rgb") + encode_etc1(cur, cw, ch, "alpha")
        body += zero4 + zero4 + len(pair).to_bytes(4, "big") + pair + zero4
        if lv < mips - 1:
            cw, ch, cur = half_rgba(cur, cw, ch)
    return (ATF_HEAD8 + (4 + len(body)).to_bytes(4, "big")
            + bytes((0x05, w.bit_length() - 1, h.bit_length() - 1, mips)) + bytes(body))


def build_cutin_atf_ios(png_data: bytes, ref_atf: bytes | None = None,
                        progress=None) -> bytes:
    """标准 PNG → iOS cut-in ATF(ETC2 RGBA,slot 3)。

    iOS 的 slot 3 每个 4x4 块是 ``EAC alpha(8B) + ETC2 color(8B)``；
    颜色编码使用 ETC1 兼容子集，保证 ETC2 RGBA 解码器可读。
    """
    w, h, rgba = png_decode_rgba(png_data)
    if w & (w - 1) or h & (h - 1):
        raise ValueError(f"ATF 要求边长为 2 的幂,PNG 是 {w}x{h}")
    mips = max(w.bit_length(), h.bit_length())
    if ref_atf is not None:
        ref = parse_atf(ref_atf)
        if (ref["w"], ref["h"]) != (w, h):
            raise ValueError(f"PNG 尺寸 {w}x{h} 与原 ATF {ref['w']}x{ref['h']} 不一致"
                             f"(cut-in 必须同尺寸替换)")
        mips = ref["mips"]
    body = bytearray()
    zero4 = (0).to_bytes(4, "big")
    cw, ch, cur = w, h, rgba
    for lv in range(mips):
        if progress:
            progress(f"ETC2 编码 mip{lv} {cw}x{ch}")
        color = encode_etc1(cur, cw, ch, "rgb")
        alpha = encode_eac_alpha(cur, cw, ch)
        blocks = max((cw + 3) // 4, 1) * max((ch + 3) // 4, 1)
        payload = b"".join(
            alpha[index * 8:index * 8 + 8] + color[index * 8:index * 8 + 8]
            for index in range(blocks)
        )
        body += zero4 + zero4 + zero4 + len(payload).to_bytes(4, "big") + payload
        if lv < mips - 1:
            cw, ch, cur = half_rgba(cur, cw, ch)
    return (ATF_HEAD8 + (4 + len(body)).to_bytes(4, "big")
            + bytes((0x05, w.bit_length() - 1, h.bit_length() - 1, mips)) + bytes(body))


def validate_cutin_platform_pair(android_atf: bytes, ios_atf: bytes,
                                 png_data: bytes | None = None) -> dict:
    """校验同一逻辑 cut-in 的 Android ETC1 与 iOS ETC2 ATF 成对有效。

    这里显式拒绝两端字节相同，防止把 Android 文件复制到 ``ios_upload``
    作为兜底。传入源 PNG 时还会校验两端尺寸与 PNG 完全一致。
    """
    if android_atf == ios_atf:
        raise ValueError("Android/iOS ATF 内容相同，疑似直接复制 Android 文件")
    android = parse_atf(android_atf)
    ios = parse_atf(ios_atf)
    if (android["slot"], android["layout"]) != (2, "etc1"):
        raise ValueError(
            f"Android ATF 必须使用 ETC1 槽 2，实际为 slot={android['slot']} "
            f"layout={android['layout']}"
        )
    if (ios["slot"], ios["layout"]) != (3, "etc2-rgba"):
        raise ValueError(
            f"iOS ATF 必须使用 ETC2 槽 3，实际为 slot={ios['slot']} "
            f"layout={ios['layout']}"
        )
    shape = (android["w"], android["h"], android["mips"])
    if (ios["w"], ios["h"], ios["mips"]) != shape:
        raise ValueError(
            "Android/iOS ATF 尺寸或 mip 数不一致: "
            f"android={shape}, ios={(ios['w'], ios['h'], ios['mips'])}"
        )
    if png_data is not None:
        png_w, png_h, _rgba = png_decode_rgba(png_data)
        if (png_w, png_h) != shape[:2]:
            raise ValueError(
                f"源 PNG 尺寸 {(png_w, png_h)} 与平台 ATF 尺寸 {shape[:2]} 不一致"
            )
    for level, (android_payload, ios_payload) in enumerate(
            zip(android["pairs"], ios["pairs"])):
        mip_w = max(shape[0] >> level, 1)
        mip_h = max(shape[1] >> level, 1)
        blocks = max((mip_w + 3) // 4, 1) * max((mip_h + 3) // 4, 1)
        expected = blocks * 16
        if len(android_payload) != expected:
            raise ValueError(
                f"Android ATF mip{level} 长度 {len(android_payload)} != {expected}"
            )
        if len(ios_payload) != expected:
            raise ValueError(
                f"iOS ATF mip{level} 长度 {len(ios_payload)} != {expected}"
            )
    return {
        "w": shape[0], "h": shape[1], "mips": shape[2],
        "android_slot": android["slot"], "ios_slot": ios["slot"],
    }


def build_cutin_platform_pair(
    png_data: bytes,
    android_ref_atf: bytes | None = None,
    ios_ref_atf: bytes | None = None,
    progress=None,
) -> tuple[bytes, bytes]:
    """从唯一源 PNG 独立生成 Android ETC1 与 iOS ETC2 ATF。"""
    android_progress = (
        (lambda message: progress("Android " + message)) if progress else None
    )
    ios_progress = (
        (lambda message: progress("iOS " + message)) if progress else None
    )
    android = build_cutin_atf(png_data, android_ref_atf, android_progress)
    ios = build_cutin_atf_ios(
        png_data,
        ios_ref_atf if ios_ref_atf is not None else android_ref_atf,
        ios_progress,
    )
    validate_cutin_platform_pair(android, ios, png_data)
    return android, ios


# ---------------------------------------------------------------- CLI

def _regen(png_logical: str) -> None:
    """从 store 现有 PNG 重生成 Android/iOS 配对 ATF。"""
    import time
    import shutil
    import wf_mod_tool as core
    import wf_assets
    import wf_gui  # add_pending / record_change(读 profiles 决定 store)

    store = core.default_target_store()
    ploc = wf_assets.locate(store, png_logical)
    if not ploc:
        raise SystemExit(f"store 里找不到源 PNG: {png_logical}")
    atf_logical = png_logical[:-4] + ".atf.deflate"
    android_fp = wf_assets.path_in_root(store, "android", atf_logical)
    ios_fp = wf_assets.path_in_root(store, "ios", atf_logical)
    png_raw = wf_assets.png_decode(ploc[1].read_bytes())
    android_ref = inflate(android_fp.read_bytes()) if android_fp.is_file() else None
    ios_ref = inflate(ios_fp.read_bytes()) if ios_fp.is_file() else None
    print(
        f"源 PNG [{ploc[0]}] {len(png_raw)}B;"
        f"Android ref={len(android_ref) if android_ref else 0}B;"
        f"iOS ref={len(ios_ref) if ios_ref else 0}B"
    )
    android_atf, ios_atf = build_cutin_platform_pair(
        png_raw, android_ref, ios_ref, progress=lambda s: print("  " + s)
    )
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backups = []
    for platform, target, plain in (
        ("android", android_fp, android_atf),
        ("ios", ios_fp, ios_atf),
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = None
        if target.is_file():
            backup = target.with_name(
                target.name + ".bak-wfmod-asset-" + stamp
            )
            if not backup.exists():
                shutil.copy2(target, backup)
        target.write_bytes(deflate(plain))
        wf_gui.add_pending(target)
        backups.append(backup)
        print(f"{platform}: slot={parse_atf(plain)['slot']} {len(plain)}B -> {target}")
    summary = (
        f"{atf_logical}: 从源 PNG 独立生成 Android ETC1(slot 2) 与 "
        f"iOS ETC2(slot 3)，{len(android_atf)}B/{len(ios_atf)}B"
    )
    wf_gui.record_change(atf_logical, summary, backups[0])
    print(summary)
    print("两端已写入 + 备份 + 加入 pending;发布后同包生效")


def _selftest() -> None:
    w, h = 64, 32
    rgba = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            o = (y * w + x) * 4
            rgba[o] = x * 255 // (w - 1)
            rgba[o + 1] = y * 255 // (h - 1)
            rgba[o + 2] = (x + y) * 255 // (w + h - 2)
            rgba[o + 3] = 255 if x < w // 2 else (w - 1 - x) * 255 // (w // 2)
    png = png_encode_rgba(w, h, bytes(rgba))
    w2, h2, back = png_decode_rgba(png)
    assert (w2, h2) == (w, h) and back == rgba, "PNG 编解码往返失败"
    atf = build_cutin_atf(png)
    p = parse_atf(atf)
    assert (p["w"], p["h"]) == (w, h) and p["mips"] == max(w.bit_length(), h.bit_length())
    half = len(p["pairs"][0]) // 2
    rgb = decode_etc1(p["pairs"][0][:half], w, h)
    alp = decode_etc1(p["pairs"][0][half:], w, h)
    ec = sum(abs(rgb[i * 3 + c] - rgba[i * 4 + c]) for i in range(w * h) for c in range(3)) / (w * h * 3)
    ea = sum(abs(alp[i * 3] - rgba[i * 4 + 3]) for i in range(w * h)) / (w * h)
    print(f"selftest: 颜色平均误差 {ec:.2f},alpha 平均误差 {ea:.2f}(阈值 12)")
    assert ec < 12 and ea < 12, "ETC1 编码质量异常"
    ios = build_cutin_atf_ios(png, atf)
    pair = validate_cutin_platform_pair(atf, ios, png)
    assert pair["ios_slot"] == 3, "iOS ETC2 槽位异常"
    print("selftest OK")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--regen", metavar="PNG_LOGICAL",
                    help="如 character/alice/ui/skill_cutin_0.png:从 store PNG 重生成 Android/iOS ATF")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    elif args.regen:
        _regen(args.regen)
    else:
        ap.print_help()
