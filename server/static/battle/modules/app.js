import { initI18n, applyTranslations, t } from '/shared/i18n.js';
import { basePath } from '/shared/base-path.js';
import { BattleModel, COMMANDS } from './model.js';
import { BattleRenderer, phaseAt } from './renderer.js';
import { BattleLiveClient } from './live.js';
import { BattleDemo } from './demo.js';
import { BattleCombat, monsterName, skillLabel } from './combat.js';

const $ = id => document.getElementById(id);
const demoMode = new URLSearchParams(location.search).get('demo') === '1' || new URLSearchParams(location.search).get('mock') === '1';
const model = new BattleModel();
const combat = new BattleCombat(model);
const renderer = new BattleRenderer($('battle'), model, t);
let live, demo, current = null, elapsed = 0, damage = 0, applied = false;
let paused = false, speed = 1, phase = 'idle', lastTime = 0, renderTime = 0, uiTime = 0;
let connection = 'connecting', dataError = null, frameId, disposed = false;
let targetSignature = '';

function title(task) { return task ? task.titleKey ? t(task.titleKey) : task.title : ''; }
function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function meter(value) {
  const el = element('div', 'meter'), fill = element('i');
  fill.style.width = `${Math.max(0, Math.min(100, value))}%`;
  el.append(fill);
  return el;
}
function setConnection(state) {
  connection = state;
  const el = $('connection');
  el.dataset.state = state;
  el.textContent = t(`battle.${demoMode ? 'demo' : state}`);
}
function log(action, text) {
  const li = element('li');
  li.dataset.side = action.side;
  li.dataset.skill = action.skill;
  li.dataset.source = action.cosmetic ? 'scene' : 'activity';
  li.append(element('time', '', new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })),
    element('span', 'log-actor', action.side === 'enemy' ? monsterName(model.tasks.get(action.target), t) : action.actor), element('span', 'log-text', text));
  $('journal').prepend(li);
  while ($('journal').children.length > 60) $('journal').lastChild.remove();
}
function actionMessage(action) {
  const task = model.tasks.get(action.target);
  const target = monsterName(task, t), skill = skillLabel(action, t);
  if (action.side === 'enemy') return t(action.evaded ? 'battle.enemy_evaded' : action.blocked ? 'battle.enemy_blocked' : 'battle.enemy_hit', { target, actor: action.actor, skill, damage });
  if (action.recover) return t('battle.recovery_message', { actor: action.actor, hp: action.healed });
  if (action.counter) return t('battle.counter_message', { actor: action.actor, target, skill });
  if (action.retreat) return t('battle.retreat_message', { target });
  if (action.finish) return t(task?.activity ? 'battle.activity_done' : 'battle.victory', { actor: action.actor, target });
  if (action.error) return t('battle.error_message', { actor: action.actor, target });
  const message = t('battle.action_message', { actor: action.actor, skill, target });
  return action.healed > 0 ? `${message} ${t('battle.heal_message', { actor: action.recipient, hp: action.healed })}` : message;
}
function updateUI() {
  const { party, enemies, totalActors, totalTasks } = renderer.visible(current);
  $('activeCount').textContent = String([...model.tasks.values()].filter(task => !task.activity).length);
  $('clearCount').textContent = String(model.cleared);
  $('reserveCount').textContent = totalTasks > 3 ? t('battle.reserve', { count: totalTasks - 3 }) : '';
  $('queueCount').textContent = model.queue.length ? t('battle.queued', { count: model.queue.length }) : t('battle.up_to_date');
  $('empty').hidden = totalTasks > 0 || Boolean(current);
  $('phaseLabel').textContent = paused ? t('battle.paused') : t(`battle.phase_${phase}`);
  const enemyTurn = current?.side === 'enemy';
  $('theater').dataset.side = current?.side || 'idle';
  $('theater').dataset.phase = phase;
  $('theater').dataset.skill = current?.skill || '';
  $('turnLabel').textContent = t(enemyTurn ? 'battle.enemy_turn' : 'battle.ally_turn');
  $('commandActor').textContent = enemyTurn ? t('battle.enemy_turn') : current?.actor || t('battle.commands');
  $('partyPage').textContent = `${renderer.page + 1}/${Math.max(1, Math.ceil(totalActors / 4))} ›`;
  $('partyPage').disabled = totalActors <= 4 || Boolean(current);
  const signature = JSON.stringify(enemies.map(task => [task.key, task.hp, task.status, task.assignee, current?.target === task.key && phase !== 'command']));
  if (signature !== targetSignature) {
    targetSignature = signature;
    $('targets').replaceChildren(...enemies.map(task => {
      const selected = current?.target === task.key && phase !== 'command';
      const row = element('div', `target-row${selected ? ' selected' : ''}`);
      const name = element('button', 'target-name', monsterName(task, t));
      name.type = 'button'; name.dataset.task = task.key;
      name.title = t('battle.inspect_task');
      const meta = element('div', 'target-meta');
      meta.append(element('span', '', task.assignee), element('span', '', t(`battle.status_${task.status}`)));
      row.append(name, meta, meter(task.hp / task.maxHp * 100));
      return row;
    }));
    if (!enemies.length) $('targets').append(element('span', 'target-meta', t('battle.no_targets')));
  }
  $('commands').replaceChildren(...COMMANDS.map(command => element('div',
    `command${!enemyTurn && current?.command === command && phase !== 'idle' ? ' selected' : ''}`, t(`battle.command_${command}`))));
  $('party').replaceChildren(...party.map(actor => {
    const selected = current?.actor === actor.name;
    const row = element('div', `party-row${selected ? ' selected' : ''}`);
    const name = element('span', 'party-name', actor.name); name.title = actor.role ? `${actor.name} · ${actor.role}` : actor.name;
    const busy = !['idle', 'sleeping', 'offline', 'stopped'].includes(actor.state);
    const vital = combat.vital(actor);
    row.dataset.hp = vital.hp; row.dataset.actor = actor.name;
    row.classList.toggle('wounded', vital.hp < 400);
    const label = t(selected && enemyTurn ? 'battle.under_attack' : selected ? 'battle.acting' : busy ? 'battle.working' : 'battle.ready');
    const gauges = element('div', 'party-gauges');
    const hp = meter(vital.hp / vital.maxHp * 100); hp.classList.add('hp-meter');
    const limit = meter(vital.limit); limit.classList.add('limit-meter');
    gauges.append(element('span', 'hp-value', t('battle.hp_value', { hp:vital.hp, max:vital.maxHp })), hp, limit);
    gauges.title = t('battle.limit_gauge', { value: vital.limit });
    row.append(name, element('span', 'party-state', label), gauges);
    return row;
  }));
  if (!party.length) $('party').append(element('span', 'target-meta', t('battle.no_party')));
  if (!current) {
    $('announcement').textContent = '';
    $('message').textContent = t(dataError === '401' || dataError === '403' ? 'battle.auth_error' : dataError ? 'battle.data_error' : connection === 'offline' && !demoMode ? 'battle.offline_message' : 'battle.waiting');
    $('detail').textContent = dataError ? t('battle.retry_hint') : t(demoMode ? 'battle.demo_hint' : 'battle.live_hint');
  }
}
function enterPhase(next) {
  phase = next;
  if (!current) return;
  const task = model.tasks.get(current.target);
  const target = monsterName(task, t), enemyTurn = current.side === 'enemy';
  const actor = enemyTurn ? target : current.actor;
  if (next === 'command') {
    $('announcement').textContent = actor;
    $('message').textContent = t(enemyTurn ? 'battle.enemy_prepares' : 'battle.select_command', { actor });
  } else if (next === 'target') {
    $('announcement').textContent = t('battle.select_target', { target: enemyTurn ? current.actor : target });
    $('message').textContent = $('announcement').textContent;
  } else if (next === 'cast' || next === 'attack') {
    $('announcement').textContent = skillLabel(current, t);
    $('message').textContent = t('battle.casting', { actor, skill: skillLabel(current, t) });
  } else if (next === 'damage' || next === 'message') {
    if (!applied) {
      damage = combat.apply(current); applied = true;
      log(current, actionMessage(current));
    }
    $('announcement').textContent = current.finish ? t('battle.complete') : current.error ? t('battle.miss') : skillLabel(current, t);
    $('message').textContent = actionMessage(current);
  }
  $('detail').textContent = current.cosmetic ? t('battle.scene_hint') : [current.tool, current.detail].filter(Boolean).join(' · ');
  updateUI();
}
function frame(now) {
  if (disposed) return;
  const dt = Math.min(.1, Math.max(0, (now - (lastTime || now)) / 1000));
  lastTime = now;
  if (!paused && !document.hidden) {
    const step = dt * speed;
    renderTime += step;
    combat.tick(step);
    demo?.update(step);
    if (!current) {
      const { party, enemies } = renderer.visible();
      current = combat.next(party, enemies, demoMode || (connection === 'online' && !dataError));
      elapsed = 0; applied = false; damage = 0;
      if (current) enterPhase('command');
    } else {
      elapsed += step;
      const next = phaseAt(elapsed, current);
      if (next === 'done') {
        if (!applied) combat.apply(current);
        combat.settle(current);
        current = null; phase = 'idle'; updateUI();
      } else if (next !== phase) enterPhase(next);
    }
  }
  uiTime += dt;
  if (uiTime > .2) { updateUI(); uiTime = 0; }
  renderer.draw(renderTime, current, elapsed, damage);
  frameId = requestAnimationFrame(frame);
}
async function start() {
  await initI18n();
  applyTranslations();
  document.title = `AnimaWorks · ${t('battle.title')}`;
  $('battle').setAttribute('aria-label', t('battle.canvas'));
  $('theater').setAttribute('aria-label', t('battle.title'));
  $('modeLabel').textContent = t(demoMode ? 'battle.demo_mode' : 'battle.live');
  $('modeSwitch').textContent = t(demoMode ? 'battle.live_button' : 'battle.demo_button');
  $('modeSwitch').href = `${basePath}/battle${demoMode ? '' : '?demo=1'}`;
  $('pause').addEventListener('click', () => {
    paused = !paused;
    $('pause').textContent = t(paused ? 'battle.resume' : 'battle.pause');
    $('pause').setAttribute('aria-pressed', String(paused));
    updateUI();
  });
  $('speed').addEventListener('change', event => { speed = Number(event.target.value); });
  $('partyPage').addEventListener('click', () => { renderer.page++; updateUI(); });
  $('partyPage').setAttribute('aria-label', t('battle.next_party'));
  $('targets').addEventListener('click', event => {
    const button = event.target.closest('[data-task]');
    const task = button && model.tasks.get(button.dataset.task);
    if (!task) return;
    $('taskMonster').textContent = monsterName(task, t);
    $('taskTitle').textContent = title(task);
    $('taskOwner').textContent = task.assignee;
    $('taskDialog').showModal();
  });
  $('taskClose').addEventListener('click', () => $('taskDialog').close());
  $('fullscreen').hidden = !document.fullscreenEnabled;
  $('fullscreen').addEventListener('click', async () => {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await $('theater').requestFullscreen(); }
    catch { $('message').textContent = t('battle.fullscreen_error'); }
  });
  await renderer.load();
  if (demoMode) { demo = new BattleDemo(model, t); setConnection('demo'); }
  else {
    live = new BattleLiveClient(model, {
      onConnection: setConnection,
      onSnapshot: rows => { void renderer.loadActors(rows.map(a => a.name).filter(Boolean), basePath); },
      onDataError: error => { dataError = error; updateUI(); },
    });
    live.start();
  }
  updateUI();
  frameId = requestAnimationFrame(frame);
}
window.addEventListener('pagehide', () => { disposed = true; live?.stop(); cancelAnimationFrame(frameId); });
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
document.addEventListener('visibilitychange', () => { lastTime = 0; if (!document.hidden && live) { live.connect(); void live.refresh(); } });
start().catch(error => {
  $('message').textContent = t('battle.load_error');
  $('detail').textContent = String(error.message);
  setConnection('offline');
  console.error('Battle initialization failed', error);
});
