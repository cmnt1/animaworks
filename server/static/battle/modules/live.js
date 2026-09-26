// Reuse Pixel's WebSocket transport (ping/pong, backoff, base path, cleanup).
import { LiveClient } from '../../workspace/pixel/modules/live.js';

export class BattleLiveClient extends LiveClient {
  constructor(model, callbacks = {}) {
    super(null, null, callbacks);
    this.model = model;
    this.onSnapshot = callbacks.onSnapshot || (() => {});
    this.onDataError = callbacks.onDataError || (() => {});
    this.syncing = false;
    this.taskRevision = 0;
    this.controller = null;
    this.syncTimer = null;
    const onConnection = this.onConnection;
    this.onConnection = state => {
      onConnection(state);
      if (state === 'online') void this.refresh();
    };
  }
  handleEvent(type, data) {
    this.model.ingest(type, data);
    if (['task_created', 'task_updated', 'task_exec_start', 'task_exec_end'].includes(data.type || data.event)) {
      this.taskRevision++;
      clearTimeout(this.syncTimer);
      this.syncTimer = setTimeout(() => this.refresh(), 800);
    }
  }
  async refresh() {
    if (this.stopped || this.syncing) return;
    this.syncing = true;
    this.controller = new AbortController();
    const timeout = setTimeout(() => this.controller?.abort(), 12000);
    const revision = this.taskRevision;
    try {
      const get = async path => {
        const response = await fetch(`${this.basePath}${path}`, {
          headers: { Accept: 'application/json' }, signal: this.controller.signal, cache: 'no-store',
        });
        if (!response.ok) throw new Error(String(response.status));
        return response.json();
      };
      const results = await Promise.allSettled([get('/api/animas'), get('/api/task-board')]);
      if (this.stopped) return;
      const [roster, tasks] = results;
      if (roster.status === 'fulfilled') {
        const rows = Array.isArray(roster.value) ? roster.value : roster.value.animas;
        if (!Array.isArray(rows)) throw new Error('roster');
        if (revision === this.taskRevision) this.model.roster(rows);
        this.onSnapshot(rows);
      }
      if (tasks.status === 'fulfilled') {
        if (!Array.isArray(tasks.value.tasks)) throw new Error('tasks');
        // A snapshot requested before a live transition must not resurrect it.
        if (revision === this.taskRevision) this.model.reconcile(tasks.value.tasks);
        else { clearTimeout(this.syncTimer); this.syncTimer = setTimeout(() => this.refresh(), 1000); }
      }
      const failure = results.find(result => result.status === 'rejected');
      this.onDataError(failure ? failure.reason.message : null);
    } catch (error) {
      if (!this.stopped) this.onDataError(error.message);
    } finally {
      clearTimeout(timeout);
      this.controller = null;
      this.syncing = false;
    }
  }
  start() {
    this.connect();
    void this.refresh();
    this.busyPollTimer = setInterval(() => this.refresh(), 15000);
  }
  stop() {
    super.stop();
    clearTimeout(this.syncTimer);
    this.controller?.abort();
  }
}
