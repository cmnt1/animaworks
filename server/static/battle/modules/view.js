import { t } from '/shared/i18n.js';
import { basePath } from '/shared/base-path.js';
import { BattleModel, COMMANDS } from './model.js';
import { BattleRenderer, phaseAt } from './renderer.js';
import { BattleLiveClient } from './live.js';
import { BattleDemo } from './demo.js';
import { BattleCombat, monsterName, skillLabel } from './combat.js';

const HERO_POSITIONS = [
  { x: 708, y: 258 },
  { x: 747, y: 302 },
  { x: 786, y: 346 },
  { x: 825, y: 390 },
];

function battleMarkup() {
  return `
    <header class="masthead">
      <a class="brand" href="${basePath}/">✦ <span>ANIMAWORKS</span></a>
      <nav aria-label="Workspace"><a href="${basePath}/workspace/pixel/">PIXEL</a><span class="current">BATTLE</span></nav>
      <span class="connection" data-battle="connection" role="status" data-i18n="battle.connecting"></span>
    </header>
    <section class="heading">
      <div><p class="eyebrow" data-i18n="battle.eyebrow"></p><h1 data-i18n="battle.title"></h1><p class="subtitle" data-i18n="battle.subtitle"></p></div>
      <div class="counters"><div><b data-battle="active-count">0</b><span data-i18n="battle.encounters"></span></div><div><b data-battle="clear-count">0</b><span data-i18n="battle.cleared"></span></div></div>
    </section>
    <section class="theater" data-battle="theater" aria-label="Battle">
      <div class="field-bar"><span><i></i> <span data-i18n="battle.field"></span></span><span data-battle="mode-label" data-i18n="battle.live"></span></div>
      <div class="field">
        <canvas data-battle="canvas" width="960" height="440" role="img" data-i18n-title="battle.canvas"></canvas>
        <div class="announcement" data-battle="announcement" role="status"></div>
        <div class="empty" data-battle="empty" hidden><span>✦</span><p data-i18n="battle.empty"></p><small data-i18n="battle.empty_hint"></small></div>
        <div class="field-caption"><span data-battle="phase-label"></span><span data-battle="turn-label"></span></div>
      </div>
      <div class="hud">
        <section class="panel targets"><h2><span data-i18n="battle.targets"></span><small data-battle="reserve-count"></small></h2><div data-battle="targets"></div></section>
        <section class="panel commands"><h2 data-battle="command-actor" data-i18n="battle.commands"></h2><div data-battle="commands"></div></section>
        <section class="panel party"><h2><span data-i18n="battle.party"></span><button data-battle="party-page" type="button"></button></h2><div data-battle="party"></div></section>
      </div>
      <div class="message-box"><span class="message-star">✦</span><div><p data-battle="message" role="status"></p><small data-battle="detail"></small></div><span class="advance">▾</span></div>
    </section>
    <div class="controls">
      <div class="playback"><button data-battle="pause" type="button" data-i18n="battle.pause"></button><label><span data-i18n="battle.speed"></span><select data-battle="speed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></label><button data-battle="fullscreen" type="button" data-i18n="battle.fullscreen"></button></div>
      <div class="mode-switch"><a data-battle="mode-switch" href="${basePath}/battle?demo=1" data-i18n="battle.demo_button"></a></div>
    </div>
    <p class="explanation" data-i18n="battle.explanation"></p>
    <dialog data-battle="task-dialog" aria-label=""><h2 data-battle="task-monster"></h2><p data-i18n="battle.original_task"></p><p class="task-title" data-battle="task-title"></p><small data-battle="task-owner"></small><form method="dialog"><button data-battle="task-close" type="submit" data-i18n="battle.close"></button></form></dialog>
    <details class="journal" open><summary><span data-i18n="battle.journal"></span><span class="queue-count" data-battle="queue-count"></span></summary><ol data-battle="journal"></ol></details>
    <footer><span data-i18n="battle.footer"></span><a href="${basePath}/workspace/" data-i18n="battle.workspace"></a></footer>
  `;
}

function translateRoot(root) {
  for (const el of root.querySelectorAll('[data-i18n]')) {
    const key = el.dataset.i18n;
    const value = t(key);
    if (value !== key) el.textContent = value;
  }
  for (const el of root.querySelectorAll('[data-i18n-title]')) {
    el.title = t(el.dataset.i18nTitle);
  }
  for (const el of root.querySelectorAll('[data-i18n-placeholder]')) {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  }
}

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function meter(value) {
  const el = element('div', 'meter');
  const fill = element('i');
  fill.style.width = `${Math.max(0, Math.min(100, value))}%`;
  el.append(fill);
  return el;
}

/**
 * Mount a self-contained battle view inside a page-owned root.
 *
 * @param {{ root: HTMLElement, demo?: boolean, onAnimaClick?: (name: string) => void }} options
 * @returns {{ dispose: () => void }}
 */
export function createBattleView({ root, demo = false, onAnimaClick = () => {} } = {}) {
  if (!root || !root.ownerDocument || !root.classList || !root.replaceChildren) {
    throw new TypeError('createBattleView requires a DOM root element');
  }

  const doc = root.ownerDocument;
  const usesRootAsBattle = root.classList.contains('aw-battle');
  const battleRoot = usesRootAsBattle ? root : doc.createElement('main');
  if (!usesRootAsBattle) {
    battleRoot.className = 'aw-battle';
    root.replaceChildren(battleRoot);
  }
  battleRoot.innerHTML = battleMarkup();
  translateRoot(battleRoot);

  const $ = (name) => battleRoot.querySelector(`[data-battle="${name}"]`);
  const demoMode = demo === true;
  const model = new BattleModel();
  const combat = new BattleCombat(model);
  const canvas = $('canvas');
  const theater = $('theater');
  const renderer = new BattleRenderer(canvas, model, t);
  const cleanups = [];
  let live = null;
  let demoRuntime = null;
  let current = null;
  let elapsed = 0;
  let damage = 0;
  let applied = false;
  let paused = false;
  let speed = 1;
  let phase = 'idle';
  let lastTime = 0;
  let renderTime = 0;
  let uiTime = 0;
  let connection = 'connecting';
  let dataError = null;
  let frameId = null;
  let disposed = false;
  let targetSignature = '';

  $('canvas').setAttribute('aria-label', t('battle.canvas'));
  theater.setAttribute('aria-label', t('battle.title'));
  $('task-dialog').setAttribute('aria-label', t('battle.original_task'));
  $('mode-label').textContent = t(demoMode ? 'battle.demo_mode' : 'battle.live');
  $('mode-switch').textContent = t(demoMode ? 'battle.live_button' : 'battle.demo_button');
  $('mode-switch').href = `${basePath}/battle${demoMode ? '?demo=0' : '?demo=1'}`;
  $('party-page').setAttribute('aria-label', t('battle.next_party'));

  function listen(target, type, handler) {
    target.addEventListener(type, handler);
    cleanups.push(() => target.removeEventListener(type, handler));
  }

  function title(task) {
    return task ? task.titleKey ? t(task.titleKey) : task.title : '';
  }

  function setConnection(state) {
    if (disposed) return;
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
    li.append(
      element('time', '', new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })),
      element('span', 'log-actor', action.side === 'enemy' ? monsterName(model.tasks.get(action.target), t) : action.actor),
      element('span', 'log-text', text),
    );
    $('journal').prepend(li);
    while ($('journal').children.length > 60) $('journal').lastChild.remove();
  }

  function actionMessage(action) {
    const task = model.tasks.get(action.target);
    const target = monsterName(task, t);
    const skill = skillLabel(action, t);
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
    if (disposed) return;
    const { party, enemies, totalActors, totalTasks } = renderer.visible(current);
    $('active-count').textContent = String([...model.tasks.values()].filter((task) => !task.activity).length);
    $('clear-count').textContent = String(model.cleared);
    $('reserve-count').textContent = totalTasks > 3 ? t('battle.reserve', { count: totalTasks - 3 }) : '';
    $('queue-count').textContent = model.queue.length ? t('battle.queued', { count: model.queue.length }) : t('battle.up_to_date');
    $('empty').hidden = totalTasks > 0 || Boolean(current);
    $('phase-label').textContent = paused ? t('battle.paused') : t(`battle.phase_${phase}`);
    const enemyTurn = current?.side === 'enemy';
    theater.dataset.side = current?.side || 'idle';
    theater.dataset.phase = phase;
    theater.dataset.skill = current?.skill || '';
    $('turn-label').textContent = t(enemyTurn ? 'battle.enemy_turn' : 'battle.ally_turn');
    $('command-actor').textContent = enemyTurn ? t('battle.enemy_turn') : current?.actor || t('battle.commands');
    $('party-page').textContent = `${renderer.page + 1}/${Math.max(1, Math.ceil(totalActors / 4))} ›`;
    $('party-page').disabled = totalActors <= 4 || Boolean(current);

    const signature = JSON.stringify(enemies.map((task) => [task.key, task.hp, task.status, task.assignee, current?.target === task.key && phase !== 'command']));
    if (signature !== targetSignature) {
      targetSignature = signature;
      $('targets').replaceChildren(...enemies.map((task) => {
        const selected = current?.target === task.key && phase !== 'command';
        const row = element('div', `target-row${selected ? ' selected' : ''}`);
        const name = element('button', 'target-name', monsterName(task, t));
        name.type = 'button';
        name.dataset.task = task.key;
        name.title = t('battle.inspect_task');
        const meta = element('div', 'target-meta');
        meta.append(element('span', '', task.assignee), element('span', '', t(`battle.status_${task.status}`)));
        row.append(name, meta, meter(task.hp / task.maxHp * 100));
        return row;
      }));
      if (!enemies.length) $('targets').append(element('span', 'target-meta', t('battle.no_targets')));
    }

    $('commands').replaceChildren(...COMMANDS.map((command) => element(
      'div',
      `command${!enemyTurn && current?.command === command && phase !== 'idle' ? ' selected' : ''}`,
      t(`battle.command_${command}`),
    )));
    $('party').replaceChildren(...party.map((actor) => {
      const selected = current?.actor === actor.name;
      const row = element('div', `party-row${selected ? ' selected' : ''}`);
      const name = element('button', 'party-name', actor.name);
      name.type = 'button';
      name.dataset.actor = actor.name;
      name.title = actor.role ? `${actor.name} · ${actor.role}` : actor.name;
      const busy = !['idle', 'sleeping', 'offline', 'stopped'].includes(actor.state);
      const vital = combat.vital(actor);
      row.dataset.hp = vital.hp;
      row.dataset.actor = actor.name;
      row.classList.toggle('wounded', vital.hp < 400);
      const label = t(selected && enemyTurn ? 'battle.under_attack' : selected ? 'battle.acting' : busy ? 'battle.working' : 'battle.ready');
      const gauges = element('div', 'party-gauges');
      const hp = meter(vital.hp / vital.maxHp * 100);
      hp.classList.add('hp-meter');
      const limit = meter(vital.limit);
      limit.classList.add('limit-meter');
      gauges.append(element('span', 'hp-value', t('battle.hp_value', { hp: vital.hp, max: vital.maxHp })), hp, limit);
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
    const target = monsterName(task, t);
    const enemyTurn = current.side === 'enemy';
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
        damage = combat.apply(current);
        applied = true;
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
    if (!paused && !doc.hidden) {
      const step = dt * speed;
      renderTime += step;
      combat.tick(step);
      demoRuntime?.update(step);
      if (!current) {
        const { party, enemies } = renderer.visible();
        current = combat.next(party, enemies, demoMode || (connection === 'online' && !dataError));
        elapsed = 0;
        applied = false;
        damage = 0;
        if (current) enterPhase('command');
      } else {
        elapsed += step;
        const next = phaseAt(elapsed, current);
        if (next === 'done') {
          if (!applied) combat.apply(current);
          combat.settle(current);
          current = null;
          phase = 'idle';
          updateUI();
        } else if (next !== phase) {
          enterPhase(next);
        }
      }
    }
    uiTime += dt;
    if (uiTime > .2) {
      updateUI();
      uiTime = 0;
    }
    renderer.draw(renderTime, current, elapsed, damage);
    frameId = requestAnimationFrame(frame);
  }

  function selectActor(name) {
    if (!name || typeof onAnimaClick !== 'function') return;
    try {
      const result = onAnimaClick(name);
      if (result && typeof result.catch === 'function') {
        result.catch((error) => console.error('Battle Anima selection failed', error));
      }
    } catch (error) {
      console.error('Battle Anima selection failed', error);
    }
  }

  function canvasActorAt(event) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const x = (event.clientX - rect.left) * canvas.width / rect.width;
    const y = (event.clientY - rect.top) * canvas.height / rect.height;
    const { party } = renderer.visible(current);
    let selected = null;
    let closest = 1;
    for (let index = 0; index < party.length && index < HERO_POSITIONS.length; index++) {
      const point = HERO_POSITIONS[index];
      const dx = (x - point.x) / 39;
      const dy = (y - (point.y - 39)) / 45;
      const distance = dx * dx + dy * dy;
      if (distance <= closest) {
        closest = distance;
        selected = party[index];
      }
    }
    return selected;
  }

  function initialize() {
    return renderer.load().then(() => {
      if (disposed) return;
      if (demoMode) {
        demoRuntime = new BattleDemo(model, t);
        setConnection('demo');
      } else {
        live = new BattleLiveClient(model, {
          onConnection: setConnection,
          onSnapshot: (rows) => { void renderer.loadActors(rows.map((actor) => actor.name).filter(Boolean), basePath); },
          onDataError: (error) => {
            if (disposed) return;
            dataError = error;
            updateUI();
          },
        });
        live.start();
      }
      updateUI();
      frameId = requestAnimationFrame(frame);
    });
  }

  listen($('pause'), 'click', () => {
    paused = !paused;
    $('pause').textContent = t(paused ? 'battle.resume' : 'battle.pause');
    $('pause').setAttribute('aria-pressed', String(paused));
    updateUI();
  });
  listen($('speed'), 'change', (event) => { speed = Number(event.target.value); });
  listen($('party-page'), 'click', () => { renderer.page++; updateUI(); });
  listen($('targets'), 'click', (event) => {
    const button = event.target.closest('[data-task]');
    const task = button && model.tasks.get(button.dataset.task);
    if (!task) return;
    $('task-monster').textContent = monsterName(task, t);
    $('task-title').textContent = title(task);
    $('task-owner').textContent = task.assignee;
    const dialog = $('task-dialog');
    if (!dialog.open) dialog.showModal();
  });
  listen($('task-close'), 'click', () => {
    const dialog = $('task-dialog');
    if (dialog.open) dialog.close();
  });
  $('fullscreen').hidden = !doc.fullscreenEnabled;
  listen($('fullscreen'), 'click', async () => {
    try {
      if (doc.fullscreenElement) await doc.exitFullscreen();
      else await theater.requestFullscreen();
    } catch {
      $('message').textContent = t('battle.fullscreen_error');
    }
  });
  listen($('party'), 'click', (event) => {
    const button = event.target.closest('[data-actor]');
    if (button && $('party').contains(button)) selectActor(button.dataset.actor);
  });
  listen(canvas, 'pointermove', (event) => {
    if (event.pointerType === 'touch') return;
    canvas.style.cursor = canvasActorAt(event) ? 'pointer' : '';
  });
  listen(canvas, 'pointerleave', () => { canvas.style.cursor = ''; });
  listen(canvas, 'click', (event) => {
    const actor = canvasActorAt(event);
    if (actor) selectActor(actor.name);
  });
  listen(doc, 'visibilitychange', () => {
    lastTime = 0;
    if (!doc.hidden && live) {
      live.connect();
      void live.refresh();
    }
  });

  void initialize().catch((error) => {
    if (disposed) return;
    $('message').textContent = t('battle.load_error');
    $('detail').textContent = String(error?.message || error);
    setConnection('offline');
    console.error('Battle initialization failed', error);
  });

  return {
    dispose() {
      if (disposed) return;
      disposed = true;
      if (frameId !== null) cancelAnimationFrame(frameId);
      frameId = null;
      for (const cleanup of cleanups.splice(0)) cleanup();
      live?.stop();
      live = null;
      demoRuntime = null;
      const dialog = $('task-dialog');
      if (dialog.open) dialog.close();
      if (doc.fullscreenElement === theater && doc.exitFullscreen) {
        void doc.exitFullscreen().catch(() => {});
      }
      if (battleRoot === root) battleRoot.replaceChildren();
      else battleRoot.remove();
    },
  };
}
