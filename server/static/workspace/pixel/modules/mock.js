const STATES = Object.freeze([
  "idle", "working", "thinking", "talking", "sleeping",
  "success", "error", "walking", "reporting",
]);

function performanceEvents(actorIds) {
  const first = (index = 0) => actorIds[index % actorIds.length];
  const group = (offset) => actorIds.slice(offset, offset + 2);
  return [
    {
      label: "envelope",
      run: ({ director }) => director.dispatch("dm_sent", {
        from: first(1),
        to: first(actorIds.length - 1),
        summary: "連携事項",
      }),
    },
    {
      label: "meeting",
      run: ({ director, performanceTick }) => {
        const participants = performanceTick % 2 ? group(3) : group(0);
        director.dispatch(performanceTick % 2 ? "board_post" : "delegation", { participants });
      },
    },
    {
      label: "delivery",
      run: ({ director, performanceTick }) => director.dispatch(
        performanceTick % 2 ? "report_out" : "external_out",
        { name: first(performanceTick + 2) },
      ),
    },
    {
      label: "instruction",
      run: ({ director, performanceTick }) => {
        const summaries = ["午前の優先事項を確認", "顧客向けレポートを準備", "リリース前チェックを実施"];
        director.dispatch("instruction", { summary: summaries[performanceTick % summaries.length] });
      },
    },
  ];
}

export class MockDemo {
  constructor(actors, director, options = {}) {
    this.actors = actors;
    this.director = director;
    this.stateInterval = options.stateInterval || 2400;
    this.performanceInterval = options.performanceInterval || 6000;
    this.performanceDelay = options.performanceDelay ?? Math.min(4000, this.performanceInterval);
    this.actorIds = actors.ids({ includeHuman: false });
    this.performanceEvents = performanceEvents(this.actorIds);
    this.stateTick = 0;
    this.performanceTick = 0;
    this.stateTimer = null;
    this.performanceTimer = null;
    this.running = false;
    window.__pixelDemo = {
      running: false,
      eventsDispatched: 0,
      totalStateCombinations: STATES.length * this.actorIds.length,
      performanceCycle: this.performanceEvents.map((event) => event.label),
      performanceInterval: this.performanceInterval,
      performanceHistory: [],
      lastEvent: "",
      cycles: 0,
      states: [...STATES],
      actors: [...this.actorIds],
      maxMovingActors: 2,
    };
  }

  start() {
    if (this.running) return;
    this.running = true;
    window.__pixelDemo.running = true;
    this.runStateTick();
    this.performanceTimer = setTimeout(() => this.runPerformanceTick(), this.performanceDelay);
  }

  runStateTick() {
    if (!this.running) return;
    this.actorIds.forEach((id, index) => {
      const state = STATES[(this.stateTick + index * 2) % STATES.length];
      const actor = this.actors.get(id);
      if (actor?.isSeated) this.actors.setState(id, state);
    });
    const heartbeatId = this.actorIds[this.stateTick % this.actorIds.length];
    if (heartbeatId) this.director.dispatch("heartbeat", { name: heartbeatId });
    window.__pixelDemo.eventsDispatched += 1;
    window.__pixelDemo.lastEvent = `state-mix:${this.stateTick}`;
    this.stateTick += 1;
    if (this.stateTick % STATES.length === 0) {
      window.__pixelDemo.cycles += 1;
    }
    this.stateTimer = setTimeout(() => this.runStateTick(), this.stateInterval);
  }

  runPerformanceTick() {
    if (!this.running) return;
    let event = this.performanceEvents[this.performanceTick % this.performanceEvents.length];
    const moving = this.actors.movingCount();
    if ((event.label === "meeting" && moving > 0) ||
        (event.label === "delivery" && moving >= 2)) {
      event = this.performanceEvents.find((candidate) => candidate.label === "instruction");
    }
    event.run({
      actors: this.actors,
      director: this.director,
      performanceTick: this.performanceTick,
    });
    window.__pixelDemo.eventsDispatched += 1;
    window.__pixelDemo.lastEvent = `performance:${event.label}`;
    window.__pixelDemo.performanceHistory.push({
      label: event.label,
      at: performance.now(),
    });
    window.__pixelDemo.performanceHistory = window.__pixelDemo.performanceHistory.slice(-12);
    this.performanceTick += 1;
    this.performanceTimer = setTimeout(() => this.runPerformanceTick(), this.performanceInterval);
  }

  stop() {
    this.running = false;
    window.__pixelDemo.running = false;
    clearTimeout(this.stateTimer);
    clearTimeout(this.performanceTimer);
  }
}

export { STATES };
