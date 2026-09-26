import test from 'node:test';
import assert from 'node:assert/strict';
import { BattleModel, classify, keyFor } from '../../../server/static/battle/modules/model.js';
import { BattleDemo } from '../../../server/static/battle/modules/demo.js';
const row = (owner, id, status = 'in_progress', extra = {}) => ({ anima_name: owner, task_id: id, assignee: owner, queue_status: status, visibility: 'active', summary: id, ...extra });
const event = (m, name, type, meta = {}, extra = {}) => m.ingest('anima.tool_activity', { name, type, meta, ...extra });

test('the same task ID in different queues is a distinct monster', () => {
  const m = new BattleModel(); m.reconcile([row('a', 'same'), row('b', 'same')]);
  event(m, 'a', 'task_updated', { task_id: 'same', status: 'done' });
  const finish = m.queue.shift(); m.apply(finish); m.settle(finish);
  assert.equal(m.cleared, 1); assert.equal(m.tasks.size, 1);
  assert(m.tasks.has(keyFor('b', 'same')));
});
test('idle and repeated tool hits never falsely complete a task', () => {
  const m = new BattleModel(); m.reconcile([row('a', 'work')]);
  m.ingest('anima.status', { name: 'a', status: 'idle' });
  for (let i = 0; i < 30; i++) {
    event(m, 'a', 'tool_result', { task_id: 'work' }, { tool: 'Bash', tool_id: String(i) });
    m.apply(m.queue.shift());
  }
  assert.equal(m.tasks.get(keyFor('a', 'work')).hp, 1);
  assert.equal(m.cleared, 0);
});
test('historical completions, failure, cancellation and disappearance are not victories', () => {
  const m = new BattleModel();
  m.reconcile([row('a', 'old', 'done'), row('a', 'fail'), row('a', 'cancel'), row('a', 'hidden')]);
  assert.equal(m.queue.length, 0);
  event(m, 'a', 'task_updated', { task_id: 'fail', status: 'failed' });
  event(m, 'a', 'task_updated', { task_id: 'cancel', status: 'cancelled' });
  m.reconcile([row('a', 'fail', 'failed'), row('a', 'cancel', 'cancelled')]);
  for (const action of m.queue.splice(0)) { m.apply(action); m.settle(action); }
  assert.equal(m.cleared, 0); assert.equal(m.tasks.size, 1);
  assert.equal(m.tasks.get(keyFor('a', 'fail')).hp, 999);
});
test('scope task context, chat context and concurrent unscoped work separately', () => {
  const m = new BattleModel(); m.reconcile([row('a', 'one'), row('a', 'two')]);
  event(m, 'a', 'tool_result', {}, { tool: 'Read', ctx: 'task:two' });
  assert.equal(m.queue.at(-1).target, keyFor('a', 'two'));
  event(m, 'a', 'tool_result', {}, { tool: 'Read', ctx: 'chat:human' });
  assert.equal(m.tasks.get(m.queue.at(-1).target).activity, true);
  event(m, 'a', 'tool_result', {}, { tool: 'Read' });
  assert.equal(m.tasks.get(m.queue.at(-1).target).activity, true);
});
test('tool stream duplicates count once and failures do no damage', () => {
  const m = new BattleModel(); m.reconcile([row('a', 'one')]);
  event(m, 'a', 'tool_start', {}, { tool_id: 'id', tool_name: 'Edit' });
  assert.equal(m.queue.length, 0);
  event(m, 'a', 'tool_use', { tool_use_id: 'id' }, { tool: 'Edit' });
  event(m, 'a', 'tool_end', {}, { tool_id: 'id', tool_name: 'Edit' });
  assert.equal(m.queue.length, 1);
  event(m, 'a', 'tool_end', {}, { tool_id: 'id2', tool_name: 'Bash', is_error: true });
  const before = m.tasks.get(keyFor('a', 'one')).hp;
  assert.equal(m.apply(m.queue.at(-1)), 0);
  assert.equal(m.tasks.get(keyFor('a', 'one')).hp, before);
});
test('completion deduplicates across executor, task update and polling', () => {
  const m = new BattleModel(); m.reconcile([row('a', 'one')]);
  event(m, 'a', 'task_exec_end', { task_id: 'one', status: 'completed' });
  event(m, 'a', 'task_updated', { task_id: 'one', status: 'done' });
  m.reconcile([row('a', 'one', 'done')]);
  assert.equal(m.queue.length, 1);
  const action = m.queue.shift(); m.apply(action); m.settle(action);
  event(m, 'a', 'task_updated', { task_id: 'one', status: 'done' });
  assert.equal(m.tasks.size, 0); assert.equal(m.cleared, 1);
});
test('explicit task execution failures do not complete tasks', () => {
  const m = new BattleModel();
  event(m, 'a', 'task_exec_start', { task_id: 'job', title: 'Build' });
  event(m, 'a', 'task_exec_end', { task_id: 'job', status: 'error' });
  assert.equal(m.queue[0].error, true); assert.equal(m.queue[0].finish, undefined);
  assert.equal(m.cleared, 0);
});
test('event queue is bounded during bursts and still includes completion', () => {
  const m = new BattleModel(); m.reconcile([row('a', 'one')]);
  for (let i = 0; i < 1000; i++) event(m, 'a', 'tool_result', { task_id: 'one' }, { tool: 'Read', tool_id: `${i}` });
  event(m, 'a', 'task_updated', { task_id: 'one', status: 'done' });
  assert(m.queue.length <= 96); assert.equal(m.queue.at(-1).finish, true);
  assert(m.queue.some(action => action.hits > 1));
});
test('unknown and malformed input is safe', () => {
  const m = new BattleModel();
  m.ingest('anima.tool_activity', null); m.ingest('unknown', {});
  m.ingest('anima.tool_activity', { name: '<script>alert(1)</script>', type: 'tool_detail' });
  assert.equal(m.queue.length, 0);
});
test('command interpretation maps actual tool names', () => {
  assert.equal(classify('mcp__aw__search_memory'), 'magic');
  assert.equal(classify('web_search'), 'magic');
  assert.equal(classify('Edit'), 'strike');
  assert.equal(classify('Bash'), 'strike');
  assert.equal(classify('send_message'), 'support');
  assert.equal(classify('submit_tasks'), 'support');
  assert.equal(classify('check_status'), 'guard');
});
test('demo cycles through all commands, failures, victory and another wave', () => {
  const m = new BattleModel(), demo = new BattleDemo(m, key => key);
  const commands = new Set(); let error = false;
  for (let i = 0; i < 49; i++) {
    demo.update(1);
    for (const action of m.queue.splice(0)) {
      commands.add(action.command); error ||= Boolean(action.error);
      m.apply(action); m.settle(action);
    }
  }
  assert.deepEqual(commands, new Set(['strike', 'magic', 'support', 'guard']));
  assert(error); assert.equal(m.cleared, 3); assert.equal(demo.wave, 2); assert.equal(m.tasks.size, 3);
});
test('stale running snapshots cannot resurrect a just-completed monster', () => {
  const m = new BattleModel(); m.reconcile([row('a', 'job')]);
  event(m, 'a', 'task_updated', { task_id: 'job', status: 'done' });
  const action = m.queue.shift(); m.apply(action); m.settle(action);
  m.reconcile([row('a', 'job', 'in_progress', { updated_at: '2020-01-01T00:00:00Z' })]);
  assert.equal(m.tasks.size, 0);
  m.reconcile([row('a', 'job', 'pending', { updated_at: '2099-01-01T00:00:00Z' })]);
  assert.equal(m.tasks.size, 1);
});
test('a flood of terminal transitions is bounded and never leaves immortal enemies', () => {
  const m = new BattleModel();
  for (let i = 0; i < 200; i++) {
    event(m, 'a', 'task_created', { task_id: `${i}` });
    event(m, 'a', 'task_updated', { task_id: `${i}`, status: 'done' });
  }
  assert(m.queue.length <= 96);
  for (const action of m.queue.splice(0)) { m.apply(action); m.settle(action); }
  assert.equal(m.cleared, 200); assert.equal(m.tasks.size, 0);
});
test('scheduler completion uses the actual cron lane and honors failed command results', () => {
  const m = new BattleModel(); m.roster([{name: 'a'}]);
  event(m, 'a', 'tool_result', {}, { tool: 'Bash', ctx: 'cron:daily' });
  const target = m.queue[0].target;
  m.ingest('anima.cron', { name: 'a', task: 'daily', result: { exit_code: 1 } });
  assert.equal(m.queue.at(-1).target, target);
  assert.equal(m.queue.at(-1).error, true);
  assert.equal(m.tasks.get(target).ending, undefined);
  m.ingest('anima.cron', { name: 'a', task: 'daily', result: { exit_code: 0 } });
  assert.equal(m.queue.at(-1).finish, true);
  assert.equal(m.queue.at(-1).target, target);
});
test('human instructions target an activity encounter without creating a fake Anima', () => {
  const m = new BattleModel(); m.roster([{name: 'a'}]); m.reconcile([row('a', 'work')]);
  m.ingest('anima.interaction', { from_person: 'human-user', to_person: 'a', type: 'message', summary: 'Hello' });
  assert.equal(m.actors.size, 1);
  assert.equal(m.tasks.get(m.queue[0].target).lane, 'chat');
});
test('a failed result corrects its queued use event instead of showing success', () => {
  const m = new BattleModel(); m.reconcile([row('a', 'work')]);
  event(m, 'a', 'tool_use', { tool_use_id: 'id' }, {tool: 'Bash'});
  event(m, 'a', 'tool_result', { tool_use_id: 'id', result_status: 'fail' }, {tool: 'Bash'});
  assert.equal(m.queue.length, 1);
  assert.equal(m.queue[0].error, true);
  assert.equal(m.apply(m.queue[0]), 0);
});
