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
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const scale = Math.max(
    1,
    Math.floor(Math.min(viewportWidth / logicalWidth, viewportHeight / logicalHeight)),
  );
  const width = logicalWidth * scale;
  const height = logicalHeight * scale;
  const stage = document.querySelector("#stage");
  document.documentElement.style.setProperty("--pixel-scale", String(scale));
  stage.dataset.pixelScale = String(scale);
  stage.style.width = `${width}px`;
  stage.style.height = `${height}px`;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  window.__pixelDisplayScale = scale;
}

async function start() {
  let live = null;
  let initialAnimas = forceMock ? sampleAnimas() : [];
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
  const companyCount = new Set(
    initialAnimas
      .filter((anima) => !anima.is_human)
      .map((anima) => String(anima.company || "default")),
  ).size;
  assets.selectOfficeBackground(companyCount);
  const officeBackground = assets.officeBackground();
  if (officeBackground && assets.officeBackgroundSlots) {
    const config = assets.manifest.scene.office_bg;
    scene.background_mode = {
      enabled: true,
      slots: assets.officeBackgroundSlots,
    };
    scene.canvas.w = config.w || officeBackground.naturalWidth || scene.canvas.w;
    scene.canvas.h = config.h || officeBackground.naturalHeight || scene.canvas.h;
  }
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

window.addEventListener("resize", resizeCanvas);
resizeCanvas();
start().catch((error) => {
  window.__pixelErrors.push(String(error?.stack || error));
  loading.textContent = "PIXEL OFFICE の起動に失敗しました";
  setConnection("offline");
});
