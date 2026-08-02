#!/usr/bin/env python3
"""スプライトシートの各フレームの頭部寸法・位置を測り、行間のばらつきを検出する。

使い方:
    measure_frames.py <sheet.png> [--cols 4] [--frame 96] [--tol 1] [--baseline <seed_96.png>]

頭部矩形は「フレーム上端から head-band(既定40px)以内で、中央列を含む連続した
不透明ランの最大幅」で近似する。腕を上げたポーズでも腕は別ランになるため巻き込まない。

exit 0 = 全フレームが基準±tol以内 / exit 1 = 逸脱あり
"""
import argparse
import sys

from PIL import Image


def opaque_mask(img):
    a = img.convert("RGBA").getchannel("A")
    return a.point(lambda v: 255 if v > 10 else 0)


def head_metrics(frame, band=40):
    """(頭頂y, 頭部幅, 顔中心x, 足元y) を返す。空フレームは None。"""
    m = opaque_mask(frame)
    bb = m.getbbox()
    if not bb:
        return None
    top, bottom = bb[1], bb[3] - 1
    w, h = m.size
    px = m.load()
    cx0 = w // 2
    best_w, best_cx = 0, cx0
    for y in range(top, min(top + band, h)):
        row = [x for x in range(w) if px[x, y]]
        if not row:
            continue
        # 中央列にいちばん近い連続ランを取る（上げた腕などの別ランを除外）
        runs, start = [], row[0]
        for i in range(1, len(row)):
            if row[i] != row[i - 1] + 1:
                runs.append((start, row[i - 1]))
                start = row[i]
        runs.append((start, row[-1]))
        run = min(runs, key=lambda r: abs((r[0] + r[1]) / 2 - cx0))
        rw = run[1] - run[0] + 1
        if rw > best_w:
            best_w, best_cx = rw, (run[0] + run[1] + 1) / 2
    return top, best_w, best_cx, bottom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--frame", type=int, default=96)
    ap.add_argument("--tol", type=int, default=1)
    ap.add_argument("--baseline", help="種画像(96x96)。省略時は全フレームの中央値を基準にする")
    ap.add_argument(
        "--free-top-rows",
        default="",
        help="頭頂yの一致を免除する行番号(1始まり)をカンマ区切りで。例: 居眠り行=5",
    )
    ap.add_argument(
        "--rows",
        default="",
        help="測定対象の行番号(1始まり)をカンマ区切りで。上半身グループと歩行グループは"
        "頭の大きさが違うので分けて実行する。例: --rows 5,6,7",
    )
    ap.add_argument(
        "--check-bottom",
        action="store_true",
        help="足元y(不透明下端)も基準と比較する。全身の歩行行で使う",
    )
    args = ap.parse_args()

    sheet = Image.open(args.sheet).convert("RGBA")
    f = args.frame
    rows = sheet.height // f
    cols = args.cols
    free_top = {int(x) for x in args.free_top_rows.split(",") if x.strip()}
    only = {int(x) for x in args.rows.split(",") if x.strip()}

    data = []
    for r in range(rows):
        if only and (r + 1) not in only:
            continue
        for c in range(cols):
            fr = sheet.crop((c * f, r * f, c * f + f, r * f + f))
            mt = head_metrics(fr)
            data.append((r + 1, c + 1, mt))

    if args.baseline:
        base = head_metrics(Image.open(args.baseline).convert("RGBA"))
    else:

        def median(idx):
            vals = sorted(d[2][idx] for d in data if d[2])
            return vals[len(vals) // 2]

        base = (median(0), median(1), median(2), median(3))
    b_top, b_w, b_cx, b_bottom = base
    print(f"基準: 頭頂y={b_top} 頭部幅={b_w} 顔中心x={b_cx} 足元y={b_bottom}")

    bad = 0
    for r, c, mt in data:
        if mt is None:
            print(f"  行{r} 列{c}: 空フレーム  NG")
            bad += 1
            continue
        top, w, cx, bottom = mt
        dt, dw, dc, db = top - b_top, w - b_w, cx - b_cx, bottom - b_bottom
        ng = abs(dw) > args.tol or abs(dc) > args.tol or (
            abs(dt) > args.tol and r not in free_top
        )
        if args.check_bottom and abs(db) > args.tol:
            ng = True
        flag = "NG" if ng else "ok"
        extra = f" 足元y={bottom:3d}({db:+d})" if args.check_bottom else ""
        print(
            f"  行{r} 列{c}: 頭頂y={top:3d}({dt:+d}) 幅={w:3d}({dw:+d}) "
            f"中心x={cx:5.1f}({dc:+.1f}){extra}  {flag}"
        )
        bad += ng

    print(f"逸脱 {bad} / {len(data)} フレーム (tol=±{args.tol})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
