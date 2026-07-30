#!/usr/bin/env python3
"""生成したシートを、承認済みの基準シート(mio等)と1コマずつ突き合わせる。

    compare_to_reference.py <target_sheet.png> <reference_sheet.png> [--tol 1] [--rows 1,2,3]

キャラ差し替え方式（基準シートを土台に髪・目・服だけを変える）で作ったシートが、
頭の大きさや顔の位置を動かしていないかを検出する。比較項目:

- 頭頂y / 顔中心x … 基準±tol(既定1px)。ここがずれると席の中で顔が動いて見える
- 頭部幅 … 基準±head-tol(既定10px)。髪型が変われば正当に変わるので緩い
- 面積比(不透明画素数の比) … 0.75〜1.35。ここを外れたら透過処理でキャラが削れたか
  背景が残っている（暗色の服がクロマキーで消される事故を検出する）
- 顔(肌領域)の 幅・高さ・上端y … **参考表示のみ**。色で肌を判定するため、明るい髪色や
  クリーム色の服を肌と誤認する。合否には使わず、最終判断は比較画像の目視で行う

exit 0 = 頭頂y・顔中心x・頭部幅が許容内 / exit 1 = 逸脱あり
"""
import argparse
import sys

from PIL import Image


def opaque_mask(img):
    return img.getchannel("A").point(lambda v: 255 if v > 10 else 0)


def head_metrics(frame, band=40):
    m = opaque_mask(frame)
    bb = m.getbbox()
    if not bb:
        return None
    top = bb[1]
    w, h = m.size
    px = m.load()
    cx0 = w // 2
    best_w, best_cx = 0, cx0
    for y in range(top, min(top + band, h)):
        row = [x for x in range(w) if px[x, y]]
        if not row:
            continue
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
    return top, best_w, best_cx


def face_metrics(frame, limit=52):
    """肌色領域から顔の外接矩形を近似する。(幅, 高さ, 上端y, 中心x) または None。

    首から下（服）を拾わないよう y<limit に限定する。それでもクリーム色や淡いピンクの
    服は肌色と区別できないため、この指標は**参考値**として扱い、最終判断は目視で行う。
    """
    px = frame.load()
    w, h = frame.size
    pts = []
    for y in range(min(limit, h)):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 128:
                continue
            if r > 190 and r > g > b and (r - b) < 115 and g > 120:
                pts.append((x, y))
    if len(pts) < 20:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, min(ys),
            (max(xs) + min(xs) + 1) / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("reference")
    ap.add_argument("--tol", type=int, default=1)
    ap.add_argument("--head-tol", type=int, default=10,
                    help="頭部幅の許容差。髪型が変われば正当に変わるため緩め")
    ap.add_argument("--frame", type=int, default=96)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--rows", default="", help="対象の行番号(1始まり)をカンマ区切りで")
    args = ap.parse_args()

    tgt = Image.open(args.target).convert("RGBA")
    ref = Image.open(args.reference).convert("RGBA")
    if tgt.size != ref.size:
        print(f"NG: サイズ不一致 target={tgt.size} reference={ref.size}")
        return 1

    f, cols = args.frame, args.cols
    rows = tgt.height // f
    only = {int(x) for x in args.rows.split(",") if x.strip()}
    bad = 0
    for r in range(rows):
        if only and (r + 1) not in only:
            continue
        for c in range(cols):
            box = (c * f, r * f, c * f + f, r * f + f)
            th, rh = head_metrics(tgt.crop(box)), head_metrics(ref.crop(box))
            tf, rf = face_metrics(tgt.crop(box)), face_metrics(ref.crop(box))
            if not th or not rh:
                print(f"  行{r + 1} 列{c + 1}: 空フレーム  NG")
                bad += 1
                continue
            t_area = sum(1 for v in opaque_mask(tgt.crop(box)).getdata() if v)
            r_area = sum(1 for v in opaque_mask(ref.crop(box)).getdata() if v)
            ratio = t_area / r_area if r_area else 0
            d = [t - s for t, s in zip(th, rh)]
            msg = (f"  行{r + 1} 列{c + 1}: 頭頂y{d[0]:+.0f} 頭部幅{d[1]:+.0f} "
                   f"顔中心x{d[2]:+.1f}")
            # 頭部幅は髪型が変われば正当に変わるので緩い。頭頂yと顔中心xは厳格。
            ng = abs(d[0]) > args.tol or abs(d[2]) > args.tol or abs(d[1]) > args.head_tol
            # 透過処理でキャラが削れた/背景が残った場合の検出
            if not (0.75 <= ratio <= 1.35):
                ng = True
            msg += f" 面積比{ratio:.2f}"
            if tf and rf:
                fd = [t - s for t, s in zip(tf, rf)]
                msg += f" | (参考)顔幅{fd[0]:+.0f} 顔高{fd[1]:+.0f} 顔上端{fd[2]:+.0f}"
            print(f"{msg}  {'NG' if ng else 'ok'}")
            bad += ng

    print(f"逸脱 {bad} フレーム (tol=±{args.tol})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
