import { AssetStore } from "./assets.js";
import { preloadPixelFonts } from "./pixel-text.js";
import { loadScene, sampleAnimas } from "./scene-layout.js";
import { SceneRenderer } from "./scene-render.js";
import { ActorManager } from "./actors.js";
import { Director } from "./director.js";
import { LiveClient } from "./live.js";
import { MockDemo } from "./mock.js";

const canvas = document.querySelector("#workspace");
const loading = document.querySelector("#loading");
const dateText = document.querySelector("#dateText");
const demoMark = document.querySelector("#demoMark");
const connectionDot = document.querySelector("#connectionDot");
const dayNightButton = document.querySelector("#dayNight");
const params = new URLSearchParams(location.search);
const forceMock = params.get("mock") === "1";
const fastMock = params.get("fast") === "1";
const DISPLAY_SCALE = 4;
let logicalWidth = Number(canvas.getAttribute("width")) || 1120;
let logicalHeight = Number(canvas.getAttribute("height")) || 736;

function setConnection(mode) {
  connectionDot.className = "";
  demoMark.textContent = "";
  if (mode === "online") {
    connectionDot.classList.add("online");
  } else if (mode === "mock") {
    connectionDot.classList.add("mock");
    demoMark.textContent = "demo";
  }
}

function updateDateBoard() {
  dateText.textContent = new Intl.DateTimeFormat("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  }).format(new Date());
}

updateDateBoard();

function resizeCanvas() {
  const width = logicalWidth * DISPLAY_SCALE;
  const height = logicalHeight * DISPLAY_SCALE;
  const stage = document.querySelector("#stage");
  document.documentElement.style.setProperty("--pixel-scale", String(DISPLAY_SCALE));
  stage.dataset.pixelScale = String(DISPLAY_SCALE);
  stage.style.width = `${width}px`;
  stage.style.height = `${height}px`;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  window.__pixelDisplayScale = DISPLAY_SCALE;
}

async function start() {
  let live = null;
  let initialAnimas = forceMock ? sampleAnimas(params.get("count")) : [];
  if (forceMock && params.get("companies") === "1") {
    initialAnimas = initialAnimas.map((anima) => ({ ...anima, company: "alpha" }));
  }
  if (!forceMock) {
    live = new LiveClient(null, null);
    initialAnimas = await live.fetchInitial();
    if (!initialAnimas.length) initialAnimas = sampleAnimas();
  }
  const [scene, assets] = await Promise.all([
    loadScene(initialAnimas),
    AssetStore.load(initialAnimas, { runtime: !forceMock }),
    preloadPixelFonts(),
  ]);
  logicalWidth = scene.canvas.w;
  logicalHeight = scene.canvas.h;
  resizeCanvas();
  const renderer = new SceneRenderer(canvas, scene, assets);
  const actors = new ActorManager(scene, assets);
  let mock = null;
  let mockStarted = false;

  const startMock = () => {
    if (mockStarted) return;
    mockStarted = true;
    setConnection("mock");
    mock = new MockDemo(actors, director, fastMock ? {
      stateInterval: 60,
      performanceInterval: 240,
      performanceDelay: 80,
    } : {});
    mock.start();
  };

  actors.initialize(initialAnimas);
  const director = new Director(scene, assets, actors, renderer, { dayNightButton });

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
  let lightingElapsed = 0;
  const frame = (now) => {
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
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  window.__pixelOffice = {
    ready: true,
    scene,
    assets,
    actors,
    director,
    renderer,
    get mock() { return mock; },
    get live() { return live; },
  };
  loading.classList.add("hidden");
}

resizeCanvas();
start().catch((error) => {
  window.__pixelErrors.push(String(error?.stack || error));
  loading.textContent = "PIXEL OFFICE の起動に失敗しました";
  setConnection("offline");
});
