export class BattleDemo {
  constructor(model, t) {
    this.model = model;
    this.t = t;
    this.time = 0;
    this.wave = 0;
    this.index = 0;
    model.roster(['Luca', 'Mira', 'Theo', 'Noa'].map(name => ({ name, status: 'idle' })));
    [...model.actors.values()].forEach((actor, i) => { actor.sprite = i; });
    this.nextWave();
  }
  nextWave() {
    this.wave++;
    const names = ['Luca', 'Mira', 'Theo'];
    const ids = names.map((_, i) => `demo-${this.wave}-${i}`);
    names.forEach((name, i) => {
      const task = this.model.task(name, ids[i], { title: this.t(`battle.demo_task_${i}`), status: 'in_progress', synthetic: true });
      task.sprite = (i + this.wave - 1) % 4;
    });
    const tool = (actor, target, name, extra = {}) => ['anima.tool_activity', {
      name: actor, type: 'tool_result', tool: name, ctx: `task:${ids[target]}`,
      meta: { anima_name: names[target], task_id: ids[target] }, ...extra,
    }];
    const done = i => ['anima.tool_activity', { name: names[i], type: 'task_updated',
      summary: this.t('battle.demo_done'), meta: { task_id: ids[i], status: 'done' } }];
    this.events = [
      [0.5, tool('Mira', 1, 'web_search', { summary: this.t('battle.demo_research') })],
      [5.5, tool('Luca', 0, 'Edit', { summary: this.t('battle.demo_build') })],
      [10.5, tool('Noa', 0, 'send_message', { summary: this.t('battle.demo_support') })],
      [15.5, tool('Theo', 2, 'Bash', { is_error: true, summary: this.t('battle.demo_error') })],
      [20.5, tool('Theo', 2, 'check_status', { summary: this.t('battle.demo_check') })],
      [25.5, done(1)],
      [30.5, tool('Theo', 2, 'Bash', { summary: this.t('battle.demo_retry') })],
      [35.5, done(0)],
      [40.5, done(2)],
    ];
    this.index = 0;
    this.time = 0;
  }
  update(dt) {
    this.time += dt;
    while (this.index < this.events.length && this.time >= this.events[this.index][0]) {
      const [, [type, data]] = this.events[this.index++];
      this.model.ingest(type, data);
    }
    if (this.time > 47 && !this.model.queue.length && !this.model.tasks.size) this.nextWave();
  }
}
