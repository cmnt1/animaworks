// Presentation state only. Nothing in this module writes to the runtime.
export const COMMANDS = ['strike', 'magic', 'support', 'guard'];
const ACTIVE = new Set(['pending', 'in_progress', 'blocked', 'delegated', 'failed', 'error']);
const DONE = new Set(['done', 'completed']);
const RETREAT = new Set(['cancelled', 'expired', 'budget_skipped', 'undeclared']);
export const keyFor = (owner, id) => JSON.stringify([owner, id]);
export function hash(value) {
  let n = 0;
  for (const c of String(value)) n = ((n * 31) + c.codePointAt(0)) >>> 0;
  return n;
}
export function classify(tool = '', event = '') {
  const value = `${tool} ${event}`.toLowerCase();
  if (/send|message|delegate|submit_task|channel|board|report|slack|gmail/.test(value)) return 'support';
  if (/search|read|browse|fetch|web|recall|memory|knowledge|grep|glob/.test(value)) return 'magic';
  if (/heartbeat|think|plan|check|status|list_task/.test(value)) return 'guard';
  return 'strike';
}
export class BattleModel {
  constructor() {
    this.actors = new Map();
    this.tasks = new Map();
    this.queue = [];
    this.cleared = 0;
    this.seen = new Map();
    this.finished = new Map();
    this.revision = 0;
  }
  actor(name, state) {
    if (typeof name !== 'string' || !name || name === 'human') return null;
    let actor = this.actors.get(name);
    if (!actor) {
      actor = { name, state: state || 'idle', sprite: hash(name) % 4, lastAction: 0 };
      this.actors.set(name, actor);
    }
    if (state) actor.state = state;
    return actor;
  }
  roster(animas) {
    const names = new Set();
    for (const a of animas) {
      if (!a?.name) continue;
      names.add(a.name);
      const actor = this.actor(a.name, a.busy?.is_busy ? 'working' : a.status || 'idle');
      if (actor) actor.role = a.role || '';
    }
    for (const name of this.actors.keys()) {
      if (!names.has(name) && !this.queue.some(a => a.actor === name)) this.actors.delete(name);
    }
    this.revision++;
  }
  remember(map, key) {
    if (map.has(key)) return false;
    map.set(key, Date.now());
    if (map.size > 1500) map.delete(map.keys().next().value);
    return true;
  }
  task(owner, id, fields = {}) {
    if (!owner || !id) return null;
    const key = keyFor(owner, id);
    let task = this.tasks.get(key);
    if (!task) {
      task = { key, owner, id, assignee: owner, title: '', status: 'pending', hp: 999, maxHp: 999,
        sprite: hash(id) % 4, synthetic: false, updated: Date.now(), ...fields };
      this.tasks.set(key, task);
    } else Object.assign(task, fields, { updated: Date.now() });
    this.revision++;
    return task;
  }
  enqueue(action) {
    if (!this.actor(action.actor)) return;
    // Bound visual latency during a burst; retain terminal transitions.
    if (this.queue.length >= 64 && !action.finish && !action.retreat) {
      const match = this.queue.findLast(a => !a.finish && !a.retreat && a.actor === action.actor && a.target === action.target && a.command === action.command);
      if (match) { match.hits = (match.hits || 1) + 1; return; }
    }
    if (this.queue.length >= 96) {
      const index = this.queue.findIndex(a => !a.finish && !a.retreat);
      if (index >= 0) this.queue.splice(index, 1);
      else {
        const skipped = this.queue.shift();
        this.apply(skipped);
        this.settle(skipped);
      }
    }
    this.queue.push({ command: 'strike', hits: 1, ...action });
    this.revision++;
  }
  terminal(task, status, actor, detail = '') {
    if (!task || task.ending) return;
    task.status = status;
    if (!DONE.has(status) && !RETREAT.has(status)) return;
    task.ending = true;
    this.enqueue({ actor: actor || task.assignee || task.owner, target: task.key,
      command: 'strike', finish: DONE.has(status), retreat: RETREAT.has(status), detail });
  }
  reconcile(rows) {
    const present = new Set();
    for (const row of rows) {
      if (!row.anima_name || !row.task_id) continue;
      const key = keyFor(row.anima_name, row.task_id);
      const prev = this.tasks.get(key);
      const status = row.queue_status;
      if (row.queue_missing || (row.visibility && row.visibility !== 'active')) continue;
      present.add(key);
      // Historical completions at initial load never replay as new victories.
      if (!ACTIVE.has(status)) {
        if (prev) this.terminal(prev, status, row.assignee);
        else if (DONE.has(status) || RETREAT.has(status)) this.remember(this.finished, key);
        continue;
      }
      if (this.finished.has(key)) {
        // An older projection may still say "running" just after a WS finish.
        const updated = Date.parse(row.updated_at || row.queue_updated_at || '');
        if (!Number.isFinite(updated) || updated <= this.finished.get(key)) continue;
        this.finished.delete(key); // a newer authoritative update reopened it
      }
      if (prev?.ending) continue;
      this.task(row.anima_name, row.task_id, { title: row.summary || row.original_instruction || row.task_id,
        assignee: row.assignee || row.anima_name, status, synthetic: false });
    }
    for (const [key, task] of this.tasks) {
      if (!task.synthetic && !present.has(key) && !task.ending) {
        // Hidden/deleted tasks withdraw, never count as completed.
        this.terminal(task, 'cancelled');
      }
    }
    this.revision++;
  }
  targetFor(name, data, create = true) {
    const meta = data.meta || {};
    const ctx = data.ctx || meta.ctx || '';
    const id = meta.task_id || data.task_id || (ctx.startsWith('task:') ? ctx.slice(5) : '');
    if (id) {
      const owner = meta.anima_name || name;
      const key = keyFor(owner, id);
      if (this.finished.has(key)) return null;
      return this.tasks.get(key) || (create ? this.task(owner, id, {
        title: meta.title || data.summary || id, status: 'in_progress', synthetic: true,
      }) : null);
    }
    // Attribute unscoped tools only when exactly one running task is plausible.
    // Chat/heartbeat/inbox/cron lanes must not attack an unrelated task.
    if (!ctx) {
      const candidates = [...this.tasks.values()].filter(t => !t.synthetic && !t.ending && t.assignee === name && t.status === 'in_progress');
      if (candidates.length === 1) return candidates[0];
    }
    const lane = ctx || (data.thread_id ? `chat:${data.thread_id}` : 'activity');
    const key = keyFor(name, `activity:${lane}`);
    return this.tasks.get(key) || (create ? this.task(name, `activity:${lane}`, {
      synthetic: true, activity: true, lane, status: 'in_progress', titleKey: `battle.encounter_${lane.split(':')[0] in {chat:1,heartbeat:1,cron:1,inbox:1} ? lane.split(':')[0] : 'activity'}`,
    }) : null);
  }
  ingest(type, data = {}) {
    if (!data || typeof data !== 'object') return;
    const event = data.event || data.type || '';
    const name = data.name || data.anima ||
      (this.actors.has(data.from_person) ? data.from_person : this.actors.has(data.to_person) ? data.to_person : null);
    const actor = this.actor(name);
    if (!actor) return;
    if (type === 'anima.status') {
      actor.state = data.status || 'idle';
      this.revision++;
      return; // idle is not proof that a task completed
    }
    if (type === 'anima.heartbeat' || type === 'anima.cron') {
      const ctx = type.endsWith('heartbeat') ? 'heartbeat' : data.task ? `cron:${data.task}` : 'cron';
      const target = this.targetFor(name, { ...data, ctx });
      const result = data.result || {};
      const error = data.is_error || result.exit_code > 0 || ['error', 'failed'].includes(result.action);
      const cancelled = RETREAT.has(result.action) || result.stop_kind === 'budget_skipped' || result.stop_kind === 'interrupted';
      this.terminal(target, error ? 'error' : cancelled ? 'cancelled' : 'completed', name, data.summary || result.summary);
      if (error) this.enqueue({ actor: name, target: target?.key, command: 'guard', error: true, detail: result.summary });
      return;
    }
    if (!['anima.tool_activity', 'anima.interaction', 'anima.proactive_message', 'board.post'].includes(type)) return;
    const meta = data.meta || {};
    const stamp = data.ts || data.id;
    if (stamp && !this.remember(this.seen, `${name}:${event}:${stamp}:${data.tool || ''}`)) return;
    if (event === 'task_created' || event === 'task_exec_start') {
      const id = meta.task_id || data.task_id;
      if (!id) return;
      const key = keyFor(name, id);
      this.finished.delete(key);
      this.task(name, id, { title: meta.title || data.summary || id, assignee: meta.assignee || name,
        status: event === 'task_created' ? 'pending' : 'in_progress', synthetic: true });
      actor.state = 'working';
      return;
    }
    if (event === 'task_updated' || event === 'task_exec_end') {
      const target = this.targetFor(name, data);
      const status = meta.status || data.status;
      if (target) {
        if (ACTIVE.has(status)) target.status = status;
        this.terminal(target, status, name, data.summary);
        if (['failed', 'error', 'blocked'].includes(status)) this.enqueue({ actor: name, target: target.key, command: 'guard', error: true, detail: data.summary });
      }
      return;
    }
    if (event === 'tool_detail') return;
    if (event === 'tool_start') { actor.state = 'working'; this.revision++; return; }
    const tool = data.tool_name || data.tool || '';
    const toolId = data.tool_id || meta.tool_use_id;
    const isError = Boolean(data.is_error || meta.is_error || meta.result_status === 'fail');
    if (['tool_use', 'tool_result', 'tool_end'].includes(event) && toolId) {
      // The activity logger and chat stream can report the same tool result.
      const key = `${name}:tool:${toolId}:${isError ? 'error' : 'ok'}`;
      if (!this.remember(this.seen, key)) return;
      const queued = this.queue.find(action => action.actor === name && action.toolId === toolId);
      if (queued && isError) { queued.error = true; return; }
    }
    const relevant = ['tool_use', 'tool_result', 'tool_end', 'message_sent', 'message_received',
      'response_sent', 'channel_post', 'heartbeat_start', 'inbox_processing_start', 'inbox_processing_end'];
    if (type === 'anima.tool_activity' && !relevant.includes(event)) return;
    const fromHuman = data.from_person && !this.actors.has(data.from_person) && data.to_person === name;
    const ctx = data.ctx || (fromHuman ? 'chat' : event.startsWith('heartbeat') ? 'heartbeat' : event.startsWith('inbox') ? 'inbox' : '');
    const target = this.targetFor(name, { ...data, ctx });
    if (!target || target.ending) return;
    const command = classify(tool, type === 'anima.tool_activity' ? event : 'message');
    this.enqueue({ actor: name, target: target.key, command, tool, toolId, error: isError,
      detail: data.summary || data.content || data.to_person || '', recipient: data.to_person });
    actor.state = 'working';
    actor.lastAction = Date.now();
    if (['response_sent', 'inbox_processing_end'].includes(event) && target.activity) this.terminal(target, 'completed', name);
  }
  apply(action) {
    const target = this.tasks.get(action.target);
    const actor = this.actors.get(action.actor);
    if (actor) actor.lastAction = Date.now();
    if (!target) return 0;
    if (action.retreat) return 0;
    const power = Math.round((68 + hash(action.tool || action.command) % 93) * (action.roll || 1)
      * (action.critical ? 1.8 : 1) * (action.limit ? 1.5 : 1) * Math.min(action.hits || 1, 4));
    const damage = action.error || action.command === 'guard' ? 0 : action.finish ? target.hp : Math.min(target.hp - 1, power);
    target.hp -= damage;
    if (action.finish && !this.finished.has(target.key)) {
      if (!target.activity) this.cleared++;
      this.remember(this.finished, target.key);
    }
    this.revision++;
    return damage;
  }
  settle(action) {
    if (action.finish || action.retreat) this.tasks.delete(action.target);
    if (action.retreat) this.remember(this.finished, action.target);
    // Activity with no completion signal quietly leaves after five minutes.
    for (const [key, task] of this.tasks) {
      if (task.activity && Date.now() - task.updated > 300000 && !task.ending && !this.queue.some(a => a.target === key)) this.tasks.delete(key);
    }
    this.revision++;
  }
}
