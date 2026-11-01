// ── Slash commands in the chat input: /compact /thread /threads /<skill> ──
// Backed by the same APIs as the TUI (cli/tui/client.py).

/** Fixed commands; `labelKey` resolves through t(). */
export const SLASH_COMMANDS = Object.freeze([
  { name: "compact", labelKey: "chat.presence.slash_compact" },
  { name: "thread", labelKey: "chat.presence.slash_thread" },
  { name: "threads", labelKey: "chat.presence.slash_threads" },
]);

/**
 * Build the candidate list: fixed commands first, then skills.
 * skills = [{ name, ref, description, active }]
 */
export function buildSlashItems(skills, t) {
  const items = SLASH_COMMANDS.map((c) => ({
    kind: "command", name: c.name, desc: t(c.labelKey), key: c.name,
  }));
  const taken = new Set(items.map((i) => i.name));
  for (const s of skills || []) {
    if (!s?.name || taken.has(s.name)) continue;
    items.push({
      kind: "skill",
      name: s.name,
      ref: s.ref || s.name,
      desc: s.description || t("chat.presence.slash_skill"),
      active: Boolean(s.active),
      key: `skill:${s.name}`,
    });
  }
  return items;
}

/** Case-insensitive prefix-then-substring match on the text after "/". */
export function filterSlashItems(items, query) {
  const q = String(query || "").replace(/^\//, "").toLowerCase();
  if (!q) return items;
  const starts = [];
  const contains = [];
  for (const it of items) {
    const n = it.name.toLowerCase();
    if (n.startsWith(q)) starts.push(it);
    else if (n.includes(q)) contains.push(it);
  }
  return [...starts, ...contains];
}

/** The palette opens only while the first token is being typed. */
export function slashQuery(value) {
  const m = /^\/([^\s/]*)$/.exec(String(value || ""));
  return m ? m[1] : null;
}

export function createSlashPalette(ctx) {
  const $ = ctx.$;
  const { state, deps } = ctx;
  const { t, api, escapeHtml } = deps;
  const input = $("chatPageInput");
  const form = $("chatPageForm");
  if (!input || !form) return { destroy() {} };

  const el = document.createElement("div");
  el.className = "chat-slash-palette";
  el.setAttribute("role", "listbox");
  el.hidden = true;
  form.appendChild(el);

  let items = [];
  let shown = [];
  let index = 0;
  let skillsFor = "";
  let skills = [];
  let note = null;

  async function _loadSkills() {
    const name = state.selectedAnima;
    const tid = state.selectedThreadId || "default";
    const key = `${name}|${tid}`;
    if (!name || key === skillsFor) return;
    skillsFor = key;
    try {
      const resp = await api(`/api/animas/${encodeURIComponent(name)}/skills?thread_id=${encodeURIComponent(tid)}`);
      skills = resp?.skills || [];
    } catch { skills = []; }
    items = buildSlashItems(skills, t);
    _render();
  }

  function _close() { el.hidden = true; shown = []; }

  function _render() {
    const q = slashQuery(input.value);
    if (q === null || input.disabled) { _close(); return; }
    shown = filterSlashItems(items.length ? items : buildSlashItems([], t), q);
    if (!shown.length) { _close(); return; }
    index = Math.min(index, shown.length - 1);
    el.innerHTML = shown.map((it, i) =>
      `<button type="button" class="chat-slash-item${i === index ? " active" : ""}" role="option" data-i="${i}">`
      + `<span class="chat-slash-name">/${escapeHtml(it.name)}</span>`
      + `<span class="chat-slash-desc">${it.active ? "● " : ""}${escapeHtml(it.desc)}</span></button>`,
    ).join("");
    el.hidden = false;
  }

  function _say(text) {
    clearTimeout(note);
    el.hidden = false;
    el.innerHTML = `<div class="chat-slash-note">${escapeHtml(text)}</div>`;
    note = setTimeout(() => { if (!shown.length) el.hidden = true; }, 3000);
  }

  function _clearInput() {
    input.value = "";
    input.style.height = "auto";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  async function _run(item) {
    const name = state.selectedAnima;
    const tid = state.selectedThreadId || "default";
    if (!name) return;
    _clearInput();
    _close();
    try {
      if (item.name === "compact") {
        await api(`/api/animas/${encodeURIComponent(name)}/chat/compact`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ thread_id: tid }),
        });
        _say(t("chat.presence.slash_done_compact"));
      } else if (item.name === "thread" && item.kind === "command") {
        ctx.controllers.thread.createNewThread();
      } else if (item.name === "threads" && item.kind === "command") {
        const dd = $("chatThreadDropdown");
        if (dd && getComputedStyle(dd).display !== "none") dd.classList.add("open");
        else $("chatThreadTabs")?.querySelector(".thread-tab")?.focus();
      } else if (item.kind === "skill") {
        const active = await api(`/api/animas/${encodeURIComponent(name)}/skills/active?thread_id=${encodeURIComponent(tid)}`);
        const refs = (active?.accepted || []).map((a) => a.ref);
        if (!refs.includes(item.ref)) refs.push(item.ref);
        const res = await api(`/api/animas/${encodeURIComponent(name)}/skills/active`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ thread_id: tid, refs, confirm_risk: false }),
        });
        const bad = (res?.rejections || [])[0];
        _say(bad ? `${item.name}: ${bad.reason}` : `/${item.name} ✓`);
        skillsFor = "";
        _loadSkills();
      }
    } catch {
      _say(t("chat.presence.slash_failed"));
    }
  }

  function _onInput() {
    index = 0;
    if (slashQuery(input.value) !== null) _loadSkills();
    _render();
  }

  function _onKeydown(e) {
    if (el.hidden || !shown.length) return;
    if (e.isComposing) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      e.stopImmediatePropagation();
      index = (index + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length;
      _render();
    } else if (e.key === "Tab" || (e.key === "Enter" && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey)) {
      e.preventDefault();
      e.stopImmediatePropagation();
      _run(shown[index]);
    } else if (e.key === "Escape") {
      e.stopImmediatePropagation();
      _close();
    }
  }

  el.addEventListener("mousedown", (e) => e.preventDefault());
  el.addEventListener("click", (e) => {
    const btn = e.target.closest(".chat-slash-item");
    if (btn) _run(shown[Number(btn.dataset.i)]);
  });
  input.addEventListener("input", _onInput);
  input.addEventListener("keydown", _onKeydown, true);
  input.addEventListener("blur", () => setTimeout(_close, 150));

  return {
    destroy() {
      input.removeEventListener("input", _onInput);
      input.removeEventListener("keydown", _onKeydown, true);
      el.remove();
    },
  };
}
