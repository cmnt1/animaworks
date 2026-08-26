/**
 * BustupAnimator — 静止画5フレーム + CSS/JS で動く「疑似Live2D」。
 *
 * リギング・モーションデータ・外部ライブラリは使わず、
 * 表情ごとのピクセル一致アライン済みフレームPNG 5枚をコンテナにスタックし、
 * まばたき・呼吸・視線追従・TTS音量(RMS)連動の口パクでキャラクターを動かす。
 *
 * フレームが見つからないanima・表情では、既存の静的 bustup 画像へフォールバックする。
 *
 * 純関数（DOM非依存・テスト対象）:
 *   - selectFrameKey(mouth, blinking): 表示フレーム選択
 *   - nextMouthState(state, rms, now): 口パクのヒステリシス+最短保持
 */

import {
  assetUrl,
  bustupExpressionCandidates,
  isRealisticMode,
} from "../../modules/avatar-resolver.js";

const VALID_EXPRESSIONS = new Set([
  "neutral", "smile", "laugh", "troubled", "surprised", "thinking", "embarrassed",
]);

const FRAME_KEYS = ["neutral", "blink", "half", "open", "blinkhalf"];
const KEY_SUFFIX = { neutral: "base", blink: "blink", half: "half", open: "open", blinkhalf: "blinkhalf" };

// ---- timing / motion constants (docs_demo_reference.html と同一) ----
const BLINK_MIN_MS = 2500;         // まばたき最小間隔
const BLINK_RANGE_MS = 4000;       // まばたき間隔ランダム幅
const BLINK_CLOSED_MS = 130;       // 一回目の閉眼時間
const BLINK_CLOSED_MS2 = 110;      // 二連まばたきの二回目閉眼時間
const DOUBLE_BLINK_GAP_MS = 140;   // 二連まばたき内のギャップ
const DOUBLE_BLINK_PROB = 0.2;     // 二連まばたきになる確率
const LERP = 0.06;                 // 視線追従のlerp係数
const ROTATE_Y = 3;                // rotateY 最大角度 (deg)
const ROTATE_X = 2.2;              // rotateX 最大角度 (deg)
const TRANS_X = 5;                  // 平行移動 max (px)
const TRANS_Y = 3;                  // 平行移動 max (px)
const PERSPECTIVE_PX = 900;         // 視点距離 (px)
const XFADE_MS = 300;               // 表情切替のクロスフェード時間

// ---- 口パク純関数用定数 ----
export const MOUTH_THRESHOLDS = {
  closedToHalf: 0.06,   // 開き方向: 閉 -> 半開
  halfToOpen: 0.18,     // 開き方向: 半開 -> 開
};
// 閉じ方向は開き方向の70%（ヒステリシス）
const CLOSE_RATIO = 0.7;
export const MIN_FRAME_HOLD_MS = 60; // 最短フレーム保持(チャタリング防止)

/**
 * フレーム合成: (mouth, blinking) -> 表示フレームキー。
 * docs_demo_reference.html の render() と同一ロジック。
 * @param {"closed"|"half"|"open"} mouth
 * @param {boolean} blinking
 * @returns {"neutral"|"blink"|"half"|"open"|"blinkhalf"}
 */
export function selectFrameKey(mouth, blinking) {
  if (blinking) return mouth === "closed" ? "blink" : "blinkhalf";
  if (mouth === "closed") return "neutral";
  if (mouth === "half") return "half";
  return "open";
}

/**
 * 口パク状態遷移（純関数・ヒステリシス+最短保持）。
 * @param {{mouth:"closed"|"half"|"open", changedAt:number}} state 直前状態
 * @param {number} rms 現在の音量 (0..1)
 * @param {number} now 現在時刻(ms)
 * @returns {{mouth:"closed"|"half"|"open", changedAt:number}} 次の状態
 */
export function nextMouthState(state, rms, now) {
  // 最短フレーム保持: 前回遷移から十分経っていなければ変更しない
  if (now - state.changedAt < MIN_FRAME_HOLD_MS) return state;
  if (!Number.isFinite(rms) || rms < 0) rms = 0;

  const { closedToHalf, halfToOpen } = MOUTH_THRESHOLDS;
  const halfToClosed = closedToHalf * CLOSE_RATIO;
  const openToHalf = halfToOpen * CLOSE_RATIO;

  let next = state.mouth;
  if (state.mouth === "closed") {
    if (rms >= closedToHalf) next = "half";
  } else if (state.mouth === "half") {
    if (rms >= halfToOpen) next = "open";
    else if (rms < halfToClosed) next = "closed";
  } else if (state.mouth === "open") {
    if (rms < openToHalf) next = "half";
  }

  if (next === state.mouth) return state;
  return { mouth: next, changedAt: now };
}

function frameFileFor(expr, key) {
  return `avatar_bustup_${expr}_frame_${KEY_SUFFIX[key]}.png`;
}

function frameSetCacheKey(animaName, expr) {
  return `${animaName}::${expr}`;
}

/**
 * フレームセット存在判定。base の存在 = セット全体の存在とみなす。
 * (animaName, expr) 単位でキャッシュ。
 * @param {string} animaName
 * @param {string} expr
 * @returns {Promise<boolean>}
 */
async function hasFrameSet(animaName, expr) {
  // フレームはアニメ調のみ。realistic表示モードでは静的bustupに任せる
  if (isRealisticMode()) return false;
  const key = frameSetCacheKey(animaName, expr);
  if (_frameSetCache.has(key)) return _frameSetCache.get(key);

  const url = assetUrl(animaName, frameFileFor(expr, "neutral"));
  let exists = false;
  try {
    const resp = await fetch(url, { method: "HEAD" });
    exists = resp.ok;
  } catch {
    exists = false;
  }
  _frameSetCache.set(key, exists);
  return exists;
}

const _frameSetCache = new Map();

/**
 * 画像プリロード。成功時 true / 失敗時 false。
 */
function loadImage(img, url) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (ok) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };
    img.onload = () => done(true);
    img.onerror = () => done(false);
    img.src = url;
  });
}

/**
 * 一つのコンテナ内で5フレームをスタックして駆動するアニメータ。
 */
export class BustupAnimator {
  /**
   * @param {HTMLElement} container アニメーションを注入するコンテナ要素
   * @param {string} animaName 対象anima名
   */
  constructor(container, animaName) {
    this._container = container;
    this._animaName = animaName;
    this._reduceMotion =
      typeof window !== "undefined" &&
      !!window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this._destroyed = false;

    // 状態
    this._expression = "neutral";
    this._mode = null; // "frames" | "static" | "none" | null(未構築)
    this._state = { mouth: "closed", changedAt: 0 };
    this._blinking = false;
    this._lipsyncOn = false;
    this._getRMS = null;
    this._gen = 0;

    // 視線追従
    this._tx = 0;
    this._ty = 0;
    this._cx = 0;
    this._cy = 0;

    // DOM層（クロスフェード用に2層交互に使う）
    this._stage = document.createElement("div");
    this._stage.className = "bustup-animator-stage";
    this._rig = document.createElement("div");
    this._rig.className = "bustup-animator-rig";
    this._layerA = this._createLayer();
    this._layerB = this._createLayer();
    this._currentLayer = this._layerA;
    this._flipLayer = this._layerB;
    this._currentLayer.el.classList.add("active");
    this._rig.appendChild(this._layerA.el);
    this._rig.appendChild(this._layerB.el);
    this._stage.appendChild(this._rig);
    container.appendChild(this._stage);

    this._onPointerMove = this._onPointerMove.bind(this);
    this._loop = this._loop.bind(this);
    window.addEventListener("pointermove", this._onPointerMove);

    this._blinkTimer = null;
    this._xfadeTimer = null;
    this._raf = null;

    this._raf = requestAnimationFrame(this._loop);
    this._scheduleBlink();
  }

  _createLayer() {
    const el = document.createElement("div");
    el.className = "bustup-animator-set";
    const breathe = document.createElement("div");
    breathe.className = "bustup-animator-breather";
    const fallback = document.createElement("img");
    fallback.className = "bustup-animator-fallback";
    fallback.alt = this._animaName;
    fallback.draggable = false;
    const frames = {};
    for (const key of FRAME_KEYS) {
      const img = document.createElement("img");
      img.className = "bustup-animator-frame";
      img.dataset.frame = key;
      img.alt = this._animaName;
      img.draggable = false;
      frames[key] = img;
      breathe.appendChild(img);
    }
    breathe.appendChild(fallback);
    el.appendChild(breathe);
    return { el, breathe, frames, fallback };
  }

  _clearLayer(layer) {
    for (const key of FRAME_KEYS) {
      const img = layer.frames[key];
      img.onload = null;
      img.onerror = null;
      img.removeAttribute("src");
      img.classList.remove("on");
    }
    layer.fallback.onload = null;
    layer.fallback.onerror = null;
    layer.fallback.removeAttribute("src");
    layer.el.classList.remove("static", "active");
  }

  _setLayerMode(layer, mode) {
    layer.el.classList.toggle("static", mode === "static");
  }

  /**
   * 表情のフレームセットをプリロードし、揃ったら約300msのクロスフェードで切替。
   * フレームセットが無い表情は静的フォールバック画像1枚へ。
   * @param {string} expression
   */
  async setExpression(expression) {
    if (this._destroyed) return;
    const expr = VALID_EXPRESSIONS.has(expression) ? expression : "neutral";
    if (this._expression === expr && this._mode !== null) return;
    this._expression = expr;

    const gen = ++this._gen;

    const hasFrames = await hasFrameSet(this._animaName, expr);
    if (this._destroyed || gen !== this._gen) return;

    const target = this._flipLayer;
    this._clearLayer(target);

    let mode;
    let ok;
    if (hasFrames) {
      mode = "frames";
      ok = await this._preloadFrames(target, expr);
    } else {
      mode = "static";
      ok = await this._preloadStatic(target, expr);
    }
    if (this._destroyed || gen !== this._gen) return;

    // フレーム読み込みに失敗したら静的フォールバックへ落とす
    if (!ok && mode === "frames") {
      mode = "static";
      ok = await this._preloadStatic(target, expr);
      if (this._destroyed || gen !== this._gen) return;
    }

    this._mode = ok ? mode : "none";
    this._setLayerMode(target, mode);
    this._clearDynamicFlags(target);
    this._render(target);
    this._activateLayer(target);
  }

  async _preloadFrames(layer, expr) {
    const results = await Promise.all(
      FRAME_KEYS.map((key) =>
        loadImage(layer.frames[key], assetUrl(this._animaName, frameFileFor(expr, key))),
      ),
    );
    return results.every(Boolean);
  }

  async _preloadStatic(layer, expr) {
    const img = layer.fallback;
    // 旧 _setBustupExpression と同じく、expr 候補が全滅したら中性候補へフォールバック。
    // 表情差分を持たないanimaでも表情タグで空表示にさせない。
    const candidates = [...bustupExpressionCandidates(expr)];
    if (expr !== "neutral") candidates.push(...bustupExpressionCandidates("neutral"));
    for (const filename of candidates) {
      const ok = await loadImage(img, assetUrl(this._animaName, filename));
      if (ok) return true;
    }
    img.removeAttribute("src");
    return false;
  }

  // 使い回しフレームに残った }.on を外してから render で正しく立て直す
  _clearDynamicFlags(layer) {
    for (const key of FRAME_KEYS) layer.frames[key].classList.remove("on");
    layer.fallback.classList.remove("on");
  }

  _render(layer = this._currentLayer) {
    const key = selectFrameKey(this._state.mouth, this._blinking);
    for (const [k, img] of Object.entries(layer.frames)) {
      img.classList.toggle("on", k === key);
    }
    return key;
  }

  _activateLayer(newLayer) {
    const old = this._currentLayer;
    if (old === newLayer) return;
    this._rig.classList.add("xfade");
    old.el.classList.remove("active");
    newLayer.el.classList.add("active");
    this._currentLayer = newLayer;
    this._flipLayer = old;
    clearTimeout(this._xfadeTimer);
    this._xfadeTimer = setTimeout(() => {
      if (!this._destroyed) this._rig.classList.remove("xfade");
    }, XFADE_MS);
  }

  // ---- まばたき ----
  _scheduleBlink() {
    if (this._destroyed) return;
    clearTimeout(this._blinkTimer);
    this._blinkTimer = setTimeout(
      () => this._doBlink(),
      BLINK_MIN_MS + Math.random() * BLINK_RANGE_MS,
    );
  }

  _doBlink() {
    if (this._destroyed) return;
    this._blinking = true;
    this._render();
    this._blinkTimer = setTimeout(() => {
      if (this._destroyed) return;
      this._blinking = false;
      this._render();
      if (Math.random() < DOUBLE_BLINK_PROB) {
        this._blinkTimer = setTimeout(() => {
          if (this._destroyed) return;
          this._blinking = true;
          this._render();
          this._blinkTimer = setTimeout(() => {
            if (this._destroyed) return;
            this._blinking = false;
            this._render();
            this._scheduleBlink();
          }, BLINK_CLOSED_MS2);
        }, DOUBLE_BLINK_GAP_MS);
      } else {
        this._scheduleBlink();
      }
    }, BLINK_CLOSED_MS);
  }

  // ---- 視線追従 ----
  _onPointerMove(e) {
    if (this._destroyed || this._reduceMotion) {
      this._tx = 0;
      this._ty = 0;
      return;
    }
    const r = this._rig.getBoundingClientRect();
    const nx = (e.clientX - (r.left + r.width / 2)) / window.innerWidth;
    const ny = (e.clientY - (r.top + r.height / 2)) / window.innerHeight;
    this._tx = Math.max(-1, Math.min(1, nx * 2));
    this._ty = Math.max(-1, Math.min(1, ny * 2));
  }

  _loop() {
    if (this._destroyed) return;
    // 口パク: RMS を読み closed/half/open を判定
    if (this._lipsyncOn && this._getRMS) {
      const prev = this._state;
      this._state = nextMouthState(this._state, this._getRMS(), performance.now());
      if (this._state !== prev) this._render();
    }
    // 視線追従 lerp
    this._cx += (this._tx - this._cx) * LERP;
    this._cy += (this._ty - this._cy) * LERP;
    if (!this._reduceMotion) {
      this._rig.style.transform =
        `rotateY(${this._cx * ROTATE_Y}deg) rotateX(${-this._cy * ROTATE_X}deg) ` +
        `translate(${this._cx * TRANS_X}px, ${this._cy * TRANS_Y}px)`;
    }
    this._raf = requestAnimationFrame(this._loop);
  }

  // ---- 口パクAPI ----
  /**
   * TTS再生のRMS(0..1)を返す取得関数を渡して口パクを開始。
   * @param {() => number} getRMS
   */
  startLipsync(getRMS) {
    if (this._destroyed) return;
    this._getRMS = typeof getRMS === "function" ? getRMS : null;
    this._lipsyncOn = Boolean(this._getRMS);
    this._state = { mouth: "closed", changedAt: 0 };
  }

  /** 口パク停止。停止時は口を閉じる。 */
  stopLipsync() {
    this._lipsyncOn = false;
    this._getRMS = null;
    this._setMouth("closed");
  }

  _setMouth(m) {
    if (this._state.mouth === m) return;
    this._state = { mouth: m, changedAt: performance.now() };
    this._render();
  }

  // ---- ライフサイクル ----
  destroy() {
    if (this._destroyed) return;
    this._destroyed = true;
    this._lipsyncOn = false;
    this._getRMS = null;
    clearTimeout(this._blinkTimer);
    clearTimeout(this._xfadeTimer);
    if (this._raf) cancelAnimationFrame(this._raf);
    window.removeEventListener("pointermove", this._onPointerMove);
    if (this._container && this._stage.parentNode === this._container) {
      this._container.removeChild(this._stage);
    }
  }
}
