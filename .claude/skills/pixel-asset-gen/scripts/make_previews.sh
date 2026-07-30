#!/usr/bin/env bash
# スプライトシートから確認用のGIF/拡大画像を作る。
#
#   make_previews.sh <sheet.png> <出力ディレクトリ> <日付プレフィクス> [行名...]
#
# 例: make_previews.sh mio_sheet.png ~/work/_tmp/2026xxxx_mio 20260729 \
#        idle working thinking talking sleeping success trouble break
#
# 生成物:
#   <prefix>_sheet_x4.png        シート全体の400%拡大（実寸のドットを確認）
#   <prefix>_anim_<n>_<name>.gif 各行4コマのループGIF（400%・白背景）
#   <prefix>_anim_全行まとめ.gif 全行が同時に動く一覧
#   <prefix>_anim_遷移チェック.gif 各行1コマ目を順に切り替え（行間のサイズ差を検出）
set -euo pipefail

SHEET="$1"; OUT="$2"; PREFIX="$3"; shift 3
NAMES=("$@")
FRAME=96
COLS=4
SCALE=400
mkdir -p "$OUT"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

ROWS=$(( $(identify -format '%h' "$SHEET") / FRAME ))

magick "$SHEET" -filter point -resize ${SCALE}% "$OUT/${PREFIX}_sheet_x4.png"

# 行ごとのGIF。速度は行名から決める（待機・居眠りは遅く、作業・会話は速く）
for ((r = 0; r < ROWS; r++)); do
  name="${NAMES[$r]:-row$((r + 1))}"
  case "$name" in
    idle | sleeping | break) delay=22 ;;
    working | talking) delay=12 ;;
    *) delay=15 ;;
  esac
  for ((c = 0; c < COLS; c++)); do
    magick "$SHEET" -crop ${FRAME}x${FRAME}+$((c * FRAME))+$((r * FRAME)) +repage \
      -background white -alpha remove -alpha off \
      -filter point -resize ${SCALE}% "$TMP/f_${r}_${c}.png"
  done
  magick -delay "$delay" -loop 0 "$TMP"/f_${r}_*.png \
    "$OUT/${PREFIX}_anim_$((r + 1))_${name}.gif"
done

# 全行まとめ（シート全体をコマごとに切り出してループ）
for ((c = 0; c < COLS; c++)); do
  magick "$SHEET" -crop ${FRAME}x$((FRAME * ROWS))+$((c * FRAME))+0 +repage \
    -background white -alpha remove -alpha off \
    -filter point -resize 200% "$TMP/all_${c}.png"
done
magick -delay 15 -loop 0 "$TMP"/all_*.png "$OUT/${PREFIX}_anim_全行まとめ.gif"

# 遷移チェック（各行の1コマ目を順に切替。行間で頭が伸縮・ジャンプしないか見る）
magick -delay 60 -loop 0 "$TMP"/f_*_0.png "$OUT/${PREFIX}_anim_遷移チェック.gif"

echo "OK: $OUT に ${ROWS}行分のプレビューを生成"
