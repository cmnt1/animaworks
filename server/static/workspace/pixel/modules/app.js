import { initI18n, t } from "/shared/i18n.js";
import { createPixelOffice } from "./office.js";

const canvas = document.querySelector("#workspace");
const loading = document.querySelector("#loading");
const dateText = document.querySelector("#dateText");
const demoMark = document.querySelector("#demoMark");
const connectionDot = document.querySelector("#connectionDot");
const dayNightButton = document.querySelector("#dayNight");
const displayScaleSelect = document.querySelector("#displayScale");
const stage = document.querySelector("#stage");
const params = new URLSearchParams(location.search);
const forceMock = params.get("mock") === "1";
const fastMock = params.get("fast") === "1";
const DISPLAY_SCALE_KEY = "aw-pixel-display-scale";
let storedDisplayScale = 2;
try {
  storedDisplayScale = Number(localStorage.getItem(DISPLAY_SCALE_KEY)) || 2;
} catch { /* keep the standalone default */ }
const displayScale = [1, 2, 3, 4].includes(storedDisplayScale) ? storedDisplayScale : 2;
displayScaleSelect.value = String(displayScale);

let pixelOffice = null;

async function start() {
  await initI18n();
  pixelOffice = createPixelOffice({
    canvas,
    hud: {
      stage,
      displayScale: displayScaleSelect,
      scaleStorageKey: DISPLAY_SCALE_KEY,
      dateText,
      demoMark,
      demoLabel: t("ws.pixel.demo"),
      connectionDot,
      dayNightButton,
      dayNightIcon: document.querySelector("#dayNightIcon"),
      dayNightLabel: document.querySelector("#dayNightLabel"),
      dayLabel: t("ws.pixel.day"),
      nightLabel: t("ws.pixel.night"),
    },
    mock: {
      enabled: forceMock,
      count: params.get("count"),
      companies: params.get("companies"),
      fast: fastMock,
    },
  });

  const runtime = await pixelOffice.ready;
  if (!runtime) return;
  window.__pixelOffice = {
    ready: true,
    scene: runtime.scene,
    assets: runtime.assets,
    actors: runtime.actors,
    director: runtime.director,
    renderer: runtime.renderer,
    get mock() { return pixelOffice?.mock || null; },
    get live() { return pixelOffice?.live || null; },
    highlight: (name) => pixelOffice?.highlight(name),
    dispose: () => pixelOffice?.dispose(),
  };
  loading.classList.add("hidden");
}

start().catch((error) => {
  pixelOffice?.dispose();
  window.__pixelErrors.push(String(error?.stack || error));
  loading.textContent = "PIXEL OFFICE の起動に失敗しました";
  connectionDot.className = "";
});
