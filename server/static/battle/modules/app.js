import { initI18n, applyTranslations, t } from '/shared/i18n.js';
import { createBattleView } from './view.js';

const demoMode = ['demo', 'mock'].some((key) => new URLSearchParams(location.search).get(key) === '1');
const root = document.querySelector('main.aw-battle');
let view = null;
let disposed = false;

async function start() {
  await initI18n();
  applyTranslations();
  if (disposed || !root) return;
  document.title = `AnimaWorks · ${t('battle.title')}`;
  view = createBattleView({ root, demo: demoMode });
}

window.addEventListener('pagehide', () => {
  disposed = true;
  view?.dispose();
  view = null;
});
window.addEventListener('pageshow', (event) => {
  if (event.persisted) location.reload();
});

void start().catch((error) => {
  if (disposed || !root) return;
  const message = root.querySelector('[data-battle="message"]');
  if (message) message.textContent = t('battle.load_error');
  console.error('Battle page initialization failed', error);
});
