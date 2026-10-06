import { AssetStore } from "./assets.js";
import { preloadPixelFonts } from "./pixel-text.js";
import { loadScene, sampleAnimas } from "./scene-layout.js";
import { SceneRenderer } from "./scene-render.js";
import { ActorManager } from "./actors.js";
import { Director } from "./director.js";
import { LiveClient } from "./live.js";
import { MockDemo } from "./mock.js";
import { hitTestAnima } from "./hit-test.js";

const DISPLAY_SCALES = new Set([1, 2, 3, 4]);

function mockConfiguration(mock) {
  if (mock && typeof mock === "object") return mock;
  return { enabled: mock === true };
}

function reportError(error) {
  const message = `pixel-office: ${error?.stack || error}`;
  if (Array.isArray(window.__pixelErrors)) {
    window.__pixelErrors.push(message);
  } else {
    console.error(message);
  }
}

/**
 * Create and own a live pixel office runtime.
 *
 * The caller owns page layout; `hud.fitContainer` opts into responsive sizing,
 * while `hud.stage` is an optional fixed-size wrapper used by the standalone
 * pixel page. The returned ready promise resolves to the initialized runtime.
 *
 * @param {{ canvas: HTMLCanvasElement, hud?: object, mock?: boolean|object,
 *   onAnimaClick?: (name: string) => void }} options
 * @returns {{ highlight: (name: string|null) => void, dispose: () => void,
 *   ready: Promise<object|null>, scene: object|null, assets: object|null,
 *   actors: object|null, director: object|null, renderer: object|null,
 *   mock: object|null, live: object|null }}
 */
export function createPixelOffice({ canvas, hud = {}, mock = false, onAnimaClick = () => {} }) {
  if (!canvas) throw new TypeError("createPixelOffice requires a canvas");

  let disposed = false;
  let frameId = null;
  let resizeObserver = null;
  let resizeListenerAttached = false;
  let logicalWidth = Number(canvas.width) || 1120;
  let logicalHeight = Number(canvas.height) || 736;
  let scene = null;
  let assets = null;
  let renderer = null;
  let actors = null;
  let director = null;
  let live = null;
  let mockDemo = null;
  let highlightedName = null;
  let mockStarted = false;
  let lightingElapsed = 0;
  const mockOptions = mockConfiguration(mock);
  const forceMock = mockOptions.enabled === true;
  const fastMock = mockOptions.fast === true;

  function setConnection(mode) {
    if (hud.connectionDot) {
      hud.connectionDot.className = "";
      if (mode === "online") hud.connectionDot.classList.add("online");
      else if (mode === "mock") hud.connectionDot.classList.add("mock");
    }
    if (hud.demoMark) {
      hud.demoMark.textContent = mode === "mock" ? (hud.demoLabel || "") : "";
    }
  }

  function updateDateBoard() {
    if (!hud.dateText) return;
    hud.dateText.textContent = new Intl.DateTimeFormat("ja-JP", {
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
    }).format(new Date());
  }

  function availableScale() {
    const target = hud.fitContainer;
    if (!target) return null;
    const rect = target.getBoundingClientRect();
    const width = target.clientWidth || rect.width;
    const height = target.clientHeight || rect.height;
    if (!(width > 0 && height > 0)) return null;
    return Math.min(width / logicalWidth, height / logicalHeight);
  }

  function resizeCanvas() {
    if (disposed) return;
    const selected = hud.displayScale?.value;
    let scale;
    if (selected === "auto") {
      const fit = availableScale();
      if (fit == null) {
        scale = 1;
      } else {
        const integerScale = Math.floor(fit);
        scale = integerScale >= 1 ? integerScale : fit;
      }
    } else {
      const requested = Number(selected);
      scale = DISPLAY_SCALES.has(requested) ? requested : 1;
      const fit = availableScale();
      if (fit != null) scale = Math.min(scale, fit);
    }

    if (!Number.isFinite(scale) || scale <= 0) scale = 1;
    const width = logicalWidth * scale;
    const height = logicalHeight * scale;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    canvas.style.imageRendering = "pixelated";

    if (hud.stage) {
      document.documentElement.style.setProperty("--pixel-scale", String(scale));
      hud.stage.dataset.pixelScale = String(scale);
      hud.stage.style.width = `${width}px`;
      hud.stage.style.height = `${height}px`;
    }
    window.__pixelDisplayScale = scale;
  }

  function startMock() {
    if (disposed || mockStarted || !actors || !director) return;
    mockStarted = true;
    setConnection("mock");
    mockDemo = new MockDemo(actors, director, fastMock ? {
      stateInterval: 60,
      performanceInterval: 240,
      performanceDelay: 80,
    } : {});
    mockDemo.start();
  }

  function pointerHit(event) {
    if (!renderer || !canvas.width || !canvas.height) return null;
    return hitTestAnima({
      clientX: event.clientX,
      clientY: event.clientY,
      rect: canvas.getBoundingClientRect(),
      logicalWidth: canvas.width,
      logicalHeight: canvas.height,
      actors: renderer.actorHitTargets,
    });
  }

  function handlePointerMove(event) {
    if (event.pointerType === "touch") return;
    canvas.style.cursor = pointerHit(event) ? "pointer" : "";
  }

  function handlePointerLeave() {
    canvas.style.cursor = "";
  }

  function handlePointerUp(event) {
    if (event.pointerType !== "touch" && event.button !== 0) return;
    const name = pointerHit(event);
    if (name) onAnimaClick(name);
  }

  function handleScaleChange() {
    if (hud.scaleStorageKey) {
      try {
        localStorage.setItem(hud.scaleStorageKey, hud.displayScale.value);
      } catch { /* scale persistence is optional */ }
    }
    resizeCanvas();
  }

  updateDateBoard();
  canvas.style.touchAction = "manipulation";
  canvas.addEventListener("pointermove", handlePointerMove);
  canvas.addEventListener("pointerleave", handlePointerLeave);
  canvas.addEventListener("pointerup", handlePointerUp);
  hud.displayScale?.addEventListener("change", handleScaleChange);

  if (hud.fitContainer) {
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(resizeCanvas);
      resizeObserver.observe(hud.fitContainer);
    } else {
      window.addEventListener("resize", resizeCanvas);
      resizeListenerAttached = true;
    }
  }

  const ready = (async () => {
    let initialAnimas = [];
    if (forceMock) {
      initialAnimas = sampleAnimas(mockOptions.count);
      if (mockOptions.companies === "1" || mockOptions.companies === true) {
        initialAnimas = initialAnimas.map((anima) => ({ ...anima, company: "alpha" }));
      }
    } else {
      live = new LiveClient(null, null, {
        onConnection: setConnection,
        onUnavailable: startMock,
      });
      initialAnimas = await live.fetchInitial();
      if (!initialAnimas.length) initialAnimas = sampleAnimas();
    }
    if (disposed) return null;

    const loaded = await Promise.all([
      loadScene(initialAnimas),
      AssetStore.load(initialAnimas, { runtime: !forceMock }),
      preloadPixelFonts(),
    ]);
    if (disposed) return null;

    [scene, assets] = loaded;
    logicalWidth = scene.canvas.w;
    logicalHeight = scene.canvas.h;
    renderer = new SceneRenderer(canvas, scene, assets);
    actors = new ActorManager(scene, assets);
    actors.initialize(initialAnimas);
    director = new Director(scene, assets, actors, renderer, {
      dayNightButton: hud.dayNightButton,
      dayNightIcon: hud.dayNightIcon,
      dayNightLabel: hud.dayNightLabel,
      dayLabel: hud.dayLabel,
      nightLabel: hud.nightLabel,
    });
    renderer.setHighlight(highlightedName);
    resizeCanvas();

    if (forceMock) {
      startMock();
    } else {
      live.actors = actors;
      live.director = director;
      live.onConnection = (mode) => {
        if (!mockStarted) setConnection(mode);
      };
      live.onUnavailable = startMock;
      live.connect();
      live.startBusyPolling();
    }

    let lastTime = performance.now();
    const frame = (now) => {
      if (disposed) return;
      frameId = requestAnimationFrame(frame);
      const deltaSeconds = Math.min(0.05, Math.max(0, (now - lastTime) / 1000));
      lastTime = now;
      lightingElapsed += deltaSeconds;
      actors.update(deltaSeconds);
      director.update(deltaSeconds);
      renderer.update(deltaSeconds);
      if (lightingElapsed >= 60) {
        lightingElapsed = 0;
        director.applyAutomaticLighting();
      }
      renderer.draw(actors, director, now / 1000);
    };
    frameId = requestAnimationFrame(frame);

    return { scene, assets, actors, director, renderer, live };
  })().catch((error) => {
    reportError(error);
    throw error;
  });

  function highlight(name) {
    highlightedName = name == null ? null : String(name);
    renderer?.setHighlight(highlightedName);
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    if (frameId !== null) {
      cancelAnimationFrame(frameId);
      frameId = null;
    }
    resizeObserver?.disconnect();
    resizeObserver = null;
    if (resizeListenerAttached) {
      window.removeEventListener("resize", resizeCanvas);
      resizeListenerAttached = false;
    }
    canvas.removeEventListener("pointermove", handlePointerMove);
    canvas.removeEventListener("pointerleave", handlePointerLeave);
    canvas.removeEventListener("pointerup", handlePointerUp);
    hud.displayScale?.removeEventListener("change", handleScaleChange);
    canvas.style.cursor = "";
    live?.stop();
    mockDemo?.stop();
    director?.dispose();
    actors?.dispose();
  }

  return {
    ready,
    highlight,
    dispose,
    get scene() { return scene; },
    get assets() { return assets; },
    get actors() { return actors; },
    get director() { return director; },
    get renderer() { return renderer; },
    get mock() { return mockDemo; },
    get live() { return live; },
  };
}
