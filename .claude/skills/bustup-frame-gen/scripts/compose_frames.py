#!/usr/bin/env python3
"""grok image_edit の差分3枚から frame_base / frame_blinkhalf をPIL合成する。

usage: python3 compose_frames.py <expr_dir> [<expr_dir> ...]

各 <expr_dir> に eyes_closed.png / mouth_half.png / mouth_open.png がある前提。
差分3枚は解像度・フレーミングが互いに一致する（元src.pngとは一致しない）ので、
合成は必ず差分同士だけで行う。口領域は mouth_half と eyes_closed の
ピクセル差分の行分布から自動検出する（最下クラスタ=口）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops


def mouth_box(mh: Image.Image, ec: Image.Image) -> tuple[int, int, int, int] | None:
    d = np.asarray(ImageChops.difference(mh.convert("RGB"), ec.convert("RGB"))).sum(axis=2)
    mask = d > 60
    rows = mask.sum(axis=1)
    ys = np.where(rows > 3)[0]
    if not len(ys):
        return None
    # 行クラスタ分割（30px以上のギャップで区切る）。目と口が別クラスタになる
    clusters, start = [], ys[0]
    for a, b in zip(ys, ys[1:]):
        if b - a > 30:
            clusters.append((start, a))
            start = b
    clusters.append((start, ys[-1]))
    y0, y1 = clusters[-1]  # 最下クラスタ = 口
    sub = mask[y0 : y1 + 1]
    xs = np.where(sub.sum(axis=0) > 0)[0]
    m = 18
    return (int(xs.min() - m), int(y0 - m), int(xs.max() + m), int(y1 + m))


def compose(d: Path) -> None:
    ec = Image.open(d / "eyes_closed.png")
    mh = Image.open(d / "mouth_half.png")
    mo = Image.open(d / "mouth_open.png")
    assert ec.size == mh.size == mo.size, (d.name, ec.size, mh.size, mo.size)
    box = mouth_box(mh, ec)
    assert box, f"{d.name}: 口領域を検出できない（差分が無い＝生成失敗の疑い）"
    # 目開き(mh)ベースに 口閉じ(ec) の口だけ貼る → base（目開き+口閉じ）
    base = mh.copy()
    base.paste(ec.crop(box), box)
    base.save(d / "frame_base.png")
    # 目閉じ(ec)ベースに 口半開き(mh) の口だけ貼る → blinkhalf
    bh = ec.copy()
    bh.paste(mh.crop(box), box)
    bh.save(d / "frame_blinkhalf.png")
    print(d.name, ec.size, "mouth_box:", box)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        compose(Path(arg))
