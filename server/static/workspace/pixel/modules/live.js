function resolveBasePath() {
  const configured = document.querySelector('meta[name="aw-base-path"]')?.content || "";
  if (configured && !configured.includes("__AW_BASE__")) return configured.replace(/\/$/, "");
  const marker = "/workspace/pixel";
  const index = location.pathname.indexOf(marker);
  return index > 0 ? location.pathname.slice(0, index) : "";
}

function names(payload) {
  return [...new Set([
    ...(Array.isArray(payload.participants) ? payload.participants : []),
    payload.from,
    payload.from_person,
    payload.to,
    payload.to_person,
    payload.name,
  ].filter(Boolean))];
}

export class LiveClient {
  constructor(director, actors, callbacks = {}) {
    this.director = director;
    this.actors = actors;
    this.basePath = resolveBasePath();
    this.onConnection = callbacks.onConnection || (() => {});
    this.onUnavailable = callbacks.onUnavailable || (() => {});
    this.socket = null;
    this.reconnectTimer = null;
    this.busyPollTimer = null;
    this.reconnectAttempt = 0;
    this.everConnected = false;
    this.unavailableTimer = null;
    this.stopped = false;
  }

  async fetchInitial() {
    try {
      const response = await fetch(`${this.basePath}/api/animas`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return [];
      const data = await response.json();
      return Array.isArray(data) ? data : data.animas || [];
    } catch {
      return [];
    }
  }

  // Long-running silent work (e.g. a cron delegated to an external coding
  // engine) emits no tool events for minutes. The busy sidecar in /api/animas
  // still reports it, so poll periodically and keep those actors awake.
  startBusyPolling(intervalSeconds = 30) {
    if (this.busyPollTimer) return;
    const poll = async () => {
      if (this.stopped) return;
      const animas = await this.fetchInitial();
      for (const anima of animas) {
        const busy = anima?.busy;
        if (!busy?.is_busy || !anima.name || this.actors.isHuman(anima.name)) continue;
        const progressAt = Date.parse(busy.last_progress_at || busy.busy_since || "");
        if (!Number.isFinite(progressAt) || Date.now() - progressAt > 15 * 60 * 1000) continue;
        const lanes = (busy.lanes || []).join(",");
        // Map the busy lanes to a kind-of-work context so each activity gets
        // its own label. Cron runs also use the background lane; live WS
        // events with a cron ctx overwrite the label when they arrive.
        let ctx = "task:busy";
        if (lanes.includes("chat")) ctx = "chat";
        else if (lanes.includes("background-worker")) ctx = "workers";
        else if (lanes.includes("inbox")) ctx = "inbox:busy";
        this.actors.noteActivity(anima.name, ctx);
      }
    };
    poll();
    this.busyPollTimer = setInterval(poll, intervalSeconds * 1000);
  }

  connect() {
    if (this.stopped || this.socket?.readyState === WebSocket.OPEN ||
        this.socket?.readyState === WebSocket.CONNECTING) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${location.host}${this.basePath}/ws`;
    this.onConnection("connecting");
    try {
      this.socket = new WebSocket(url);
    } catch {
      this.markUnavailable();
      this.scheduleReconnect();
      return;
    }

    this.socket.addEventListener("open", () => {
      this.everConnected = true;
      this.reconnectAttempt = 0;
      clearTimeout(this.unavailableTimer);
      this.onConnection("online");
    });
    this.socket.addEventListener("message", (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "ping") {
          this.socket?.send(JSON.stringify({ type: "pong" }));
          return;
        }
        this.handleEvent(message.type, message.data || {});
      } catch {
        // Existing workspace intentionally ignores non-JSON WebSocket frames.
      }
    });
    this.socket.addEventListener("error", () => {
      this.onConnection("offline");
      this.markUnavailable();
    });
    this.socket.addEventListener("close", () => {
      this.socket = null;
      this.onConnection("offline");
      this.markUnavailable();
      this.scheduleReconnect();
    });
  }

  markUnavailable() {
    if (this.everConnected || this.unavailableTimer) return;
    this.unavailableTimer = setTimeout(() => {
      this.unavailableTimer = null;
      if (!this.everConnected) this.onUnavailable();
    }, 1800);
  }

  scheduleReconnect() {
    if (this.stopped || this.reconnectTimer) return;
    const delay = Math.min(30000, 1000 * (2 ** this.reconnectAttempt)) + Math.random() * 500;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectAttempt += 1;
      this.connect();
    }, delay);
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.reconnectTimer);
    clearInterval(this.busyPollTimer);
    this.busyPollTimer = null;
    clearTimeout(this.unavailableTimer);
    this.socket?.close();
    this.socket = null;
  }

  isHumanSender(value, data = {}) {
    return data.meta?.from_type === "human" || this.actors?.isHuman(value);
  }

  handleEvent(type, data) {
    if (type === "anima.status") {
      this.actors.setState(data.name, data.status);
      return;
    }
    if (type === "anima.interaction") {
      if (data.type !== "message") return;
      if (this.isHumanSender(data.from_person, data)) {
        this.director.dispatch("instruction", data);
      } else {
        this.director.dispatch("message_sent", data);
      }
      return;
    }
    if (type === "anima.cron") {
      // Fires when a cron task finishes. Command-type crons emit no tool
      // activity while running, so this is the visible signal that the anima
      // is doing scheduled work; the state decays back to sleeping later.
      const name = data.name;
      if (name && !this.actors.isHuman(name)) {
        this.actors.noteActivity(name, "cron:done");
      }
      return;
    }
    if (type === "anima.heartbeat") {
      // Completion event: the scheduled run just finished, drop back to idle
      // (which then decays to sleeping without further activity).
      const name = data.name || data.actor || data.target;
      if (name && !this.actors.isHuman(name)) this.actors.setState(name, "idle");
      this.director.dispatch("heartbeat", data);
      return;
    }
    if (type === "anima.tool_activity") {
      if (data.name && !this.actors.isHuman(data.name)) {
        // ctx is often unset in practice; the entry type (cron_executed,
        // heartbeat_start, tool_use, ...) still identifies the work.
        this.actors.noteActivity(
          data.name,
          data.ctx || data.meta?.ctx || data.type || "",
          data.tool || data.tool_name || "",
        );
      }
      this.handleToolActivity(data);
      return;
    }
    if (type === "board.post") {
      this.director.dispatch("board_post", { ...data, participants: names(data) });
      return;
    }
    if (type === "anima.proactive_message") {
      const from = data.name || data.anima;
      const to = data.to_person || data.to || data.target;
      if (this.isHumanSender(from, data)) {
        this.director.dispatch("instruction", { ...data, from });
      } else if (to) {
        this.director.dispatch("dm_sent", { ...data, from, to });
      }
      return;
    }
    this.handleDirectEvent(type, data);
  }

  handleToolActivity(data) {
    const event = String(data.event || data.type || "").toLowerCase();
    const meta = data.meta || {};
    if (event === "message_sent" && data.to_person) {
      if (meta.intent === "delegation") {
        this.director.dispatch("delegation", {
          ...data,
          from: data.name,
          to: data.to_person,
          participants: names({ ...data, from: data.name }),
        });
      } else if (this.isHumanSender(data.name, data)) {
        this.director.dispatch("instruction", data);
      } else {
        this.director.dispatch("message_sent", { ...data, from: data.name, to: data.to_person });
      }
    }
    const tool = String(data.tool_name || data.tool || "").toLowerCase();
    const explicitOutbound = ["external_out", "report_out", "external", "report"].includes(event);
    const reportedOutbound = ["tool_use", "tool_end"].includes(event) &&
      (meta.direction === "out" || meta.to_type === "external" ||
       tool.includes("external") || tool.includes("report"));
    if (explicitOutbound || reportedOutbound) {
      this.director.dispatch(tool.includes("report") || event.includes("report") ? "report_out" : "external_out", {
        ...data,
        name: data.name,
      });
    }
  }

  handleDirectEvent(type, data) {
    const normalized = String(type || "").toLowerCase().replaceAll(".", "_");
    if (["message_sent", "dm_sent"].includes(normalized)) {
      if (this.isHumanSender(data.from || data.from_person, data)) {
        this.director.dispatch("instruction", data);
      } else {
        this.director.dispatch(normalized, data);
      }
    } else if (["delegation", "board_post"].includes(normalized)) {
      this.director.dispatch(normalized, { ...data, participants: names(data) });
    } else if (["external_out", "report_out", "heartbeat"].includes(normalized)) {
      this.director.dispatch(normalized, data);
    }
  }
}

export { resolveBasePath };
