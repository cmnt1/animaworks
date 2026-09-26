// Battle-only choreography. HP, counterattacks and recovery never change runtime state.
import { hash } from './model.js';

export const SKILLS = {
  strike: ['crescent', 'rush', 'skyfall', 'crosscut'],
  magic: ['flare', 'frost', 'thunder', 'meteor'],
  support: ['rally', 'heal', 'stars', 'chain'],
  guard: ['barrier', 'parry', 'focus', 'ward'],
};
export const ENEMY_SKILLS = [
  ['acid', 'bounce'], ['gaze', 'nightbolt'], ['quake', 'rockfall'], ['breath', 'dive'],
];
const PALETTE = { crescent:'#ffdea2', rush:'#f7b688', skyfall:'#fff0c2', crosscut:'#ffc995',
  flare:'#ff9569', frost:'#96e9ff', thunder:'#e2c2ff', meteor:'#ffcc81',
  rally:'#9bffe0', heal:'#8affc1', stars:'#f3e9a3', chain:'#97eaff',
  barrier:'#98bbff', parry:'#fff1bd', focus:'#bde9df', ward:'#c7abff',
  acid:'#a5f472', bounce:'#78ecd5', gaze:'#fb91e3', nightbolt:'#b892fc',
  quake:'#ffd398', rockfall:'#e0c79c', breath:'#ff8759', dive:'#ffb9a2' };
export const skillColor = action => PALETTE[action?.skill] || '#ffdfa5';
export const skillLabel = (action, t) => t(`battle.tech_${action?.skill || 'crescent'}`);

export function monsterIdentity(task) {
  if (task.monster) return task.monster;
  const source = `${task.title || ''} ${task.lane || ''}`.toLowerCase();
  const theme = /test|pytest|検証|テスト|error|修復|失敗/.test(source) ? 'storm'
    : /search|research|調査|検索|web/.test(source) ? 'mist'
    : /message|report|slack|chat|報告|連絡|返信|共有/.test(source) ? 'echo'
    : /read|memory|document|\.md|記憶|資料|仕様|文書/.test(source) ? 'rune'
    : /cron|schedule|定期|巡回|時刻/.test(source) ? 'clock'
    : /code|build|fix|\.py|\.js|実装|修正|開発|ファイル/.test(source) ? 'iron' : 'moon';
  task.monster = { theme, epithet: hash(task.key) % 3, species: task.sprite % 4 };
  return task.monster;
}
export function monsterName(task, t) {
  if (!task) return '';
  const m = monsterIdentity(task);
  return t('battle.monster_name', { epithet:t(`battle.epithet_${m.theme}_${m.epithet}`), species:t(`battle.species_${m.species}`) });
}

export function timings(action) {
  const pace = action?.pace || 1;
  return [0.5, 1.0, 1.65, 2.5, 3.2, 4.1].map(n => n * pace);
}
export const PHASES = ['command', 'target', 'cast', 'attack', 'damage', 'message'];
export function phaseAt(elapsed, action) {
  return PHASES[timings(action).findIndex(t => elapsed < t)] || 'done';
}
export function progressAt(elapsed, action, phase) {
  const index = PHASES.indexOf(phase), cuts = timings(action);
  const start = index <= 0 ? 0 : cuts[index - 1];
  return Math.max(0, Math.min(1, (elapsed - start) / (cuts[index] - start)));
}

export class BattleCombat {
  constructor(model, random = Math.random) {
    this.model = model;
    this.random = random;
    this.lastSkills = new Map();
    this.clock = 0;
    this.nextEnemyAt = 4;
    this.counter = null;
    this.enemyTurns = 0;
    this.allyTurns = 0;
  }
  vital(actor) {
    if (!actor.vital) actor.vital = { hp:1200, maxHp:1200, guard:0, limit:0 };
    return actor.vital;
  }
  choose(key, choices) {
    const previous = this.lastSkills.get(key);
    const options = choices.filter(value => value !== previous);
    const skill = options[Math.floor(this.random() * options.length)] || choices[0];
    this.lastSkills.set(key, skill);
    return skill;
  }
  tick(dt) { this.clock += dt; }
  prepare(action) {
    const actor = this.model.actors.get(action.actor);
    const vital = actor && this.vital(actor);
    const side = action.side || 'ally';
    const task = this.model.tasks.get(action.target);
    const command = action.command || 'strike';
    const skill = this.choose(`${side}:${side === 'enemy' ? task?.sprite : command}`, side === 'enemy'
      ? ENEMY_SKILLS[task?.sprite || 0] : SKILLS[command]);
    const critical = side === 'ally' && command !== 'guard' && (this.random() < .17 || (vital?.limit >= 100));
    const limit = critical && vital?.limit >= 100;
    if (limit) vital.limit = 0;
    return { ...action, side, command, skill, critical, limit,
      pace: (side === 'enemy' ? .85 : .92) + this.random() * .2,
      roll: .8 + this.random() * .5, combo: ['rush','crosscut','stars','chain'].includes(skill) ? 3 : 1,
      cosmetic: Boolean(action.cosmetic || side === 'enemy') };
  }
  next(party, enemies, allowEnemy = true) {
    const alive = enemies.filter(task => !task.ending && task.hp > 0);
    const fighters = party.filter(actor => !['offline','stopped'].includes(actor.state));
    // Recovery has priority when an actor is staggered. It is explicitly a scene action.
    const wounded = fighters.find(actor => this.vital(actor).hp < 250);
    if (wounded && alive.length && allowEnemy) {
      return this.prepare({ actor:wounded.name, target:alive[0].key, command:'support', recover:true, cosmetic:true });
    }
    if (allowEnemy && fighters.length && alive.length && this.clock >= this.nextEnemyAt) {
      const task = alive[this.enemyTurns % alive.length];
      const actor = fighters[this.enemyTurns % fighters.length];
      this.enemyTurns++;
      this.nextEnemyAt = this.clock + 8 + this.random() * 5;
      return this.prepare({ side:'enemy', actor:actor.name, target:task.key, command:'strike' });
    }
    if (this.counter && allowEnemy) {
      const action = this.counter; this.counter = null;
      if (this.model.tasks.has(action.target) && !this.model.tasks.get(action.target).ending && this.model.actors.has(action.actor)) return this.prepare(action);
    }
    while (this.model.queue.length) {
      const action = this.model.queue.shift();
      if (!this.model.tasks.has(action.target)) continue;
      this.allyTurns++;
      return this.prepare(action);
    }
    return null;
  }
  apply(action) {
    const actor = this.model.actors.get(action.actor);
    if (!actor) return action.cosmetic ? 0 : this.model.apply(action);
    const vital = this.vital(actor);
    if (action.side === 'enemy') {
      const task = this.model.tasks.get(action.target);
      if (!task || task.ending) { action.evaded = true; return 0; }
      const blocked = vital.guard > 0;
      const damage = Math.min(vital.hp, Math.round((135 + (task.sprite || 0) * 30) * action.roll * (blocked ? .25 : 1)));
      vital.hp = Math.max(0, vital.hp - damage);
      vital.limit = Math.min(100, vital.limit + (blocked ? 14 : 30));
      if (blocked) vital.guard--;
      action.blocked = blocked;
      action.staggered = vital.hp === 0;
      this.counter = { actor:actor.name, target:task.key, command:blocked ? 'guard' : 'strike', cosmetic:true, counter:true };
      this.model.revision++;
      return damage;
    }
    if (action.error || action.retreat) return this.model.apply(action);
    if (action.command === 'support' || action.recover) {
      const candidates = [...this.model.actors.values()];
      const recipient = action.recover ? actor : candidates.sort((a,b) => this.vital(a).hp - this.vital(b).hp)[0] || actor;
      const rv = this.vital(recipient);
      const heal = Math.min(rv.maxHp - rv.hp, Math.round((action.recover ? 650 : 300) * action.roll));
      rv.hp += heal;
      action.healed = heal;
      action.recipient = recipient.name;
    }
    if (action.command === 'guard') { vital.guard = 2; vital.limit = Math.min(100, vital.limit + 18); }
    else vital.limit = Math.min(100, vital.limit + 9);
    if (action.cosmetic) {
      const target = this.model.tasks.get(action.target);
      if (!target || target.ending || action.recover || action.command === 'guard') return 0;
      const damage = Math.min(target.hp - 1, Math.round(95 * action.roll * (action.critical ? 1.8 : 1)));
      target.hp -= damage;
      return damage;
    }
    return this.model.apply(action);
  }
  settle(action) {
    if (action.side !== 'enemy' && !action.cosmetic) this.model.settle(action);
  }
}
