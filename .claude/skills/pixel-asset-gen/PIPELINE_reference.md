# mio土台・キャラクター差し替えパイプライン

最初に合格した3体で確立した実手順を、別キャラクターでも同じ入力と後処理を
再現できる形で記録する。`SPEC.md` が正であり、本書は実行手順を補足する。

## 1. 1行分の入力画像

組み込み `image_gen` を1行につき1回呼ぶ。CLI画像生成は使わない。

入力画像は次の3枚（yoruだけは人物参照が旧ドット絵1枚）を、この順序で渡す。

1. **編集土台**: `ref/base_row<N>_<state>.png` をPOINTで400%拡大し、透明部分を
   `#FF00FF` で埋めた1536×384画像
2. **人物参照1**: `<character>/assets/avatar_chibi.png`
3. **人物参照2**: `<character>/assets/avatar_bustup.png`

組み込みツール呼び出しの形:

```json
{
  "referenced_image_paths": [
    "<作業ディレクトリ>/tools/mio_x4_magenta/base_row<N>_<state>.png",
    "<data_dir>/animas/<name>/assets/avatar_chibi.png",
    "<data_dir>/animas/<name>/assets/avatar_bustup.png"
  ],
  "prompt": "<下記のプロンプト全文>"
}
```

yoruでは後ろ2つを
そのキャラの旧スプライトシート1枚へ置き換える。

土台の作成コマンド:

```bash
magick <作業ディレクトリ>/ref/base_row0_idle.png \
  -filter point -resize 400% \
  -background '#FF00FF' -alpha background -alpha remove -alpha off \
  <作業ディレクトリ>/<name>/intermediate/base_row0_idle_x4_magenta.png
```

`row0_idle` は各行のファイル名に置き換える。低解像度の384×96を直接渡すと、
モデルが顔・髪・体型を再解釈するため、**全10行を例外なく**最近傍400%版の編集土台にする。
途中の行から低解像度入力へ戻してはいけない。

### 実際に使用したプロンプト

下記をそのままコピーし、`<name>`、`<state>`、`<state instructions>`、
人物の外見記述だけを置換する。

```text
Use case: precise-object-edit
Asset type: production pixel-art character animation strip
Primary request: Edit Image 1. Replace only the character identity with <name> from Images 2 and 3. Keep Image 1 as the exact layout, scale, silhouette, animation, and pixel-grid target.
Input images: Image 1 is the edit target and approved base animation strip; Image 2 is the character chibi identity reference; Image 3 is the character bust-up identity and color reference.
Subject: Use <name>'s exact hair shape, hair color, bangs, hair accessory, eye color, and clothing colors from the identity references. The row state is <state>: <state instructions>.
Style/medium: crisp native pixel art, hard one-pixel edges, no antialiasing, same pixel density and outline weight as Image 1.
Composition/framing: exactly four equal left-to-right animation frames. Preserve every frame's pose, gesture, direction, crop, body size, shoulder width, head-top height, exposed face size, face center, eye/nose/mouth positions, and spacing from Image 1. Do not enlarge the face or head.
Scene/backdrop: perfectly flat solid #FF00FF chroma-key background only.
Constraints: Change only character identity colors and identity details. Preserve the clean flat skin area of the face. Eyes, eyebrows, nose, mouth, and blush must remain small, separated, readable pixel clusters matching Image 1. No new dark marks, shadows, outlines, hair strands, or isolated pixels may overlap the eyes, nose, mouth, cheeks, or exposed face. Keep dark hair clearly separated from the face boundary. The background must be one uniform #FF00FF with no shadows, gradients, texture, floor, or lighting variation.
Avoid: extra frames, merged frames, panels, borders, labels, text, speech bubbles, props, desk, chair, monitor, keyboard, cast shadow, reflection, watermark, smooth vector edges, painterly shading, facial moles, facial dirt, black blobs, stray dark pixels, and any dark patch crossing onto the face.
```

`Subject` の直後に、生成前に確定したidentityを曖昧さなく追記する。参照画像間に矛盾がある場合、
モデルへ選択させない。例えば瞳色やサイドポニーの有無を1つに決め、10行すべてで同じ文を使う。

`<state instructions>` は次を使う。

| row | state | state instructions |
|---:|---|---|
| 0 | idle | preserve the four idle/blink expressions exactly |
| 1 | working | preserve the four working poses and the visible upper-body crop exactly |
| 2 | thinking | preserve the four thinking gestures and hand positions exactly |
| 3 | talking | preserve the four talking mouth/gesture phases exactly |
| 4 | walk_down | preserve the four front-facing walk phases exactly |
| 5 | walk_up | preserve the four back-facing walk phases exactly |
| 6 | walk_side | preserve the four side-facing walk phases exactly |
| 7 | sleeping | preserve the four sleeping poses and closed-eye expressions exactly |
| 8 | success | preserve the four success gesture phases exactly |
| 9 | error | preserve the four worried/error expressions and sweat marks exactly |

合格した3体の生成では、上記と同じ `precise-object-edit` 構成で、
土台、chibi、bust-upを同時入力し、状態ごとに最後の動作文だけを差し替えた。

## 2. マゼンタ背景の透過

抜き色は **`#FF00FF` 固定**。緑背景は禁止。

合格3体で使用したヘルパー呼び出し:

```bash
python3 ~/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py \
  --input <作業ディレクトリ>/<name>/intermediate/<row>_band.png \
  --out <作業ディレクトリ>/<name>/intermediate/<row>_keyed.png \
  --auto-key border \
  --soft-matte \
  --transparent-threshold 12 \
  --opaque-threshold 220 \
  --despill
```

ただし、暗色キャラを守るために次のガードを必ず入れる。

- 生成画像から「幅の25%以上がマゼンタである走査行」の連続帯だけを抽出する。
- helper後の半透明画素比率が1.5%を超えたらhelper出力を採用しない。
  元のマゼンタ帯へ戻り、HSVで高彩度マゼンタだけを透明化する。
- 暗色・黒に近いRGBは透明化しない。
- 最後にアルファを `a >= 128 ? 255 : 0` へ二値化する。
- BOX縮小で生じた明度10%以下の近黒色の緑/マゼンタ色相は、透明化せず
  `max(r,g,b)` のグレーへ中和する。透明化すると黒髪やスーツに穴が開く。
- 緑背景は使わないが、参照キャラに本来ある緑眼や緑系アクセントは保持する。
  「緑色相」という理由だけで一律中和してはいけない。中和対象は上記の近黒色ノイズだけ。

実装は次を使う。

```bash
python3 .claude/skills/pixel-asset-gen/scripts/process_generated_row.py \
  <作業ディレクトリ>/<name>/intermediate/row<N>_generated.png \
  <作業ディレクトリ>/ref/base_row<N>_<state>.png \
  <作業ディレクトリ>/<name>/row<N>_<state>.png \
  --work-dir <作業ディレクトリ>/<name>/intermediate/processed_row<N>
```

## 3. 96×96×4への縮小

1. 透過後の横長画像を幅25%ずつ、4セルに分割する。
2. 各セルをアルファ境界でtrimする。
3. 対応するmioの96×96セルから不透明bbox
   `(ref_left, ref_top, ref_right, ref_bottom)` を得る。
4. 生成スプライトを **BOXフィルタ**で
   `ref_width × ref_height` に1回だけ縮小する。
5. 96×96透明キャンバスの `(ref_left, ref_top)` へ整数座標で配置する。
6. 4セルを横連結して384×96にする。

この処理は生成物を救済するための自由変形ではない。生成された人物の縦横比が目視で崩れている場合は
その行を不合格にして再生成する。処理後にシート全体へ横85%などの追加スケールを掛けてはいけない。

実コードではPillowの次の処理に相当する。

```python
generated_sprite.resize(
    (ref_right - ref_left, ref_bottom - ref_top),
    resample=Image.Resampling.BOX,
)
```

モデル出力寸法は一定でないため固定倍率ではない。入力土台はPOINTで正確に4倍、
出力は各mioセルの実bboxへBOXで直接1回だけ縮小する。ぼやける場合だけPOINTを試す。
posterize、減色、輪郭のスムージングは行わない。

## 4. 位置合わせと後処理

1. 各セルをmioと同じbbox上端へ置くことで頭頂yを揃える。
2. 頭部上端から40px以内の中央連結成分を測る。
3. 生成物の頭部中心とmioの頭部中心との差を丸め、x方向へ整数平行移動する。
4. 頭部幅がmioより10pxを超える場合だけ、頭部外縁を左右対称に削る。
   顔内部、目、口、頬には触れない。
5. アルファを再度二値化する。
6. 10行を明示順で縦連結する。

```bash
magick \
  row0_idle.png row1_working.png row2_thinking.png row3_talking.png \
  row4_walk_down.png row5_walk_up.png row6_walk_side.png \
  row7_sleeping.png row8_success.png row9_error.png \
  -append pixel_sheet.png
```

## 5. 顔のゴミを防ぐために効いた点

- 低解像度土台ではなく、POINT 400%のmioを**編集対象**として先頭入力する。
- 「新規キャラを描く」ではなく、`Replace only the character identity` とする。
- 顔サイズ、目鼻口位置、全ポーズを不変条件として列挙する。
- プロンプトで、顔上の黒い塊、孤立暗色、髪線の顔への侵入を明示的に禁止する。
- 黒髪・暗色服をクロマキーと誤認しない。暗色は絶対に透明化しない。
- 生成直後の大画像と、縮小後の各384×96行を両方目視する。
- 数値検査が通っても、各行を400%以上で見て、目・鼻・口・頬の周囲に
  不連続な暗色画素があればその行を再生成する。顔のゴミを後処理で塗り潰さない。
- 1回の再生成では、問題のある行と顔のゴミ禁止だけを変更し、他の条件を動かさない。

黒髪では髪の輪郭・眼鏡・目の線が同じ暗色になりやすい。顔と髪の境界に明確な肌色の
連続領域を残し、「dark hair clearly separated from the face boundary」を入れる。

## 6. やってはいけないこと

- 緑背景を使う。despillで肌や淡色服が緑になる。
- 384×96の低解像度土台をそのまま渡す。顔が再解釈されて大きくなる。
- キャラクターを土台なしで新規描画する。
- 10行を1回で生成する。必ず1行1回。
- auto-key結果を無条件に使う。黒髪・濃紺服が欠けることがある。
- 暗色画素をクロマキー残滓として透明化する。
- 顔の黒い塊を機械的な塗り潰しやinpaintで隠す。表情も壊れるため再生成する。
- posterizeや減色で顔のゴミを消そうとする。
- 小数座標移動、複数回リサイズ、補間付き平行移動をする。
- compareスクリプトだけで合格にする。顔は必ず目視する。
- 最終検証後にシート全体または全セルへ横・縦だけの一括補正を掛ける。
- 机、椅子、モニタ、キーボード、影、文字、吹き出しを追加する。

## 7. 行ごとの検査

```bash
python3 .claude/skills/pixel-asset-gen/scripts/compare_to_reference.py \
  <作業ディレクトリ>/<name>/row<N>_<state>.png \
  <作業ディレクトリ>/ref/base_row<N>_<state>.png --tol 1
```

さらに `view_image` で384×96の行を原寸または拡大表示し、4フレームすべての顔を確認する。
最終シートでは次を実行する。

```bash
python3 .claude/skills/pixel-asset-gen/scripts/compare_to_reference.py \
  <作業ディレクトリ>/<name>/pixel_sheet.png \
  <作業ディレクトリ>/ref/mio_sheet_10rows.png --tol 1
```

合格条件は逸脱0、面積比0.75〜1.35、384×960 RGBA、アルファ2値、クロマ残滓4px以下、
全40フレームの顔の目視合格、identity不変条件の40/40一致、遷移GIFでの別人化・伸縮なし。
候補は `~/work/_tmp/` で人間の承認を得てからruntimeへ反映する。
