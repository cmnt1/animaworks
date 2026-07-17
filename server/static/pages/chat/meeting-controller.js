// ── Meeting Mode Controller ──────────────────────
import { t } from "../../shared/i18n.js";

export function createMeetingController(ctx) {
  const { state, deps } = ctx;
  const $ = ctx.$;
  const { api, escapeHtml } = deps;

  // ── State (mutate ctx.state directly) ──────────
  function init(options = {}) {
    state.meetingStandalone = Boolean(options.standalone);
    state.meetingMode = state.meetingStandalone;
    state.meetingRoom = null;
    state.meetingRooms = [];
    state.meetingProjectDepartments = [];
    state.meetingProjectTasks = [];
    state.meetingSelectedDepartment = "";
    state.meetingSelectedTaskCode = "";
    state.meetingShowArchived = false;
    state.meetingParticipants = [];
    state.meetingChair = null;
    state.meetingSpeakerQueue = [];
    state.meetingCompletedSpeakers = [];
    state.meetingCurrentSpeaker = "";
    state.meetingRoundStatus = "";
    state.meetingActionPanelOpen = false;
    state.meetingActionItems = [];
    state.meetingActionRoomId = "";
    _bindEvents();
    if (state.meetingMode) {
      refreshMeetingRooms();
      refreshProjectTasks();
    }
    _updateToggleUI();
    _updateMeetingPanel();
    _updateAnimaTabsVisibility();
  }

  function _bindEvents() {
    const toggle = $("meetingModeToggle");
    if (toggle) {
      toggle.addEventListener("click", () => toggleMeetingMode());
    }
  }

  function toggleMeetingMode() {
    if (state.meetingStandalone) return;
    state.meetingMode = !state.meetingMode;
    if (state.meetingMode) {
      refreshMeetingRooms();
      refreshProjectTasks();
    }
    if (!state.meetingMode) {
      state.meetingRoom = null;
      state.meetingParticipants = [];
    }
    _updateToggleUI();
    _updateMeetingPanel();
    _updateAnimaTabsVisibility();
    ctx.controllers.renderer?.renderChat();
  }

  function _updateToggleUI() {
    const toggle = $("meetingModeToggle");
    if (toggle) {
      toggle.classList.toggle("active", state.meetingMode);
      toggle.title = state.meetingMode ? t("meeting.toggle_active") : t("meeting.toggle");
    }
  }

  function _updateMeetingPanel() {
    const panel = $("meetingParticipantPanel");
    if (!panel) return;
    const main = panel.closest(".chat-page-main");

    if (!state.meetingMode) {
      panel.style.display = "none";
      main?.classList.remove("meeting-session-picker");
      return;
    }
    panel.style.display = "flex";
    main?.classList.toggle(
      "meeting-session-picker",
      Boolean(state.meetingStandalone && !state.meetingRoom)
    );

    if (state.meetingRoom) {
      _renderActiveRoomPanel(panel);
    } else {
      _renderSetupPanel(panel);
    }
  }

  function _updateAnimaTabsVisibility() {
    const tabsContainer = $("chatAnimaTabs");
    const addBtn = $("chatAddConversationArea");
    const threadTabs = $("chatThreadTabs");
    const toggle = $("meetingModeToggle");
    const splitBtn = $("chatSplitPaneBtn");
    const closeBtn = $("chatClosePaneBtn");
    if (tabsContainer) {
      tabsContainer.style.display = state.meetingMode ? "none" : "";
    }
    if (addBtn) {
      addBtn.style.display = state.meetingMode ? "none" : "";
    }
    if (threadTabs) {
      threadTabs.style.display = state.meetingMode ? "none" : "";
    }
    if (toggle && state.meetingStandalone) {
      toggle.style.display = "none";
    }
    if (splitBtn && state.meetingStandalone) {
      splitBtn.style.display = "none";
    }
    if (closeBtn && state.meetingStandalone) {
      closeBtn.style.display = "none";
    }
  }

  function _avatarHtml(name) {
    const url = state.animaTabAvatarUrls?.[name];
    const initial = escapeHtml((name || "?").charAt(0).toUpperCase());
    if (url) {
      return `<img class="chip-avatar chip-avatar-img" src="${escapeHtml(url)}" alt="${escapeHtml(name)}">`;
    }
    return `<span class="chip-avatar chip-avatar-initial">${initial}</span>`;
  }

  function _label(key, fallback) {
    const value = t(key);
    return value && value !== key ? value : fallback;
  }

  function _animaMeta(anima) {
    if (!anima) return "";
    return [anima.department, anima.title, anima.role]
      .map((v) => (v || "").trim())
      .filter(Boolean)
      .join(" · ");
  }

  // タスク部門（Obsidian カテゴリ、日本語）→ アニマ所属部門（英語）の対応表。
  // 両者は名称体系が異なるため、完全一致に加えてこの表でもマッチさせる。
  const DEPARTMENT_ALIASES = {
    "一般": ["Administration", "全社"],
    "経営": ["全社", "Administration"],
    "会計": ["Finance"],
    "投資": ["Finance"],
    "不動産": ["Property"],
    "アフィリエイト": ["Affiliate"],
  };

  function _departmentMatches(animaDepartment, selectedDepartment) {
    const dept = (animaDepartment || "").trim();
    if (!dept) return false;
    if (dept === selectedDepartment) return true;
    return (DEPARTMENT_ALIASES[selectedDepartment] || []).includes(dept);
  }

  function _selectDepartmentMembers(department) {
    if (!department) return;
    const members = state.animas.filter(
      (a) =>
        (a.status === "running" || a.status === "idle") &&
        _departmentMatches(a.department, department)
    );
    if (members.length === 0) return;
    const selected = new Set(members.map((a) => a.name));
    state.meetingParticipants = [...selected];
    if (!state.meetingChair || !selected.has(state.meetingChair)) {
      const leader = members.find((a) =>
        `${a.title || ""} ${a.role || ""}`.toUpperCase().includes("COO") ||
        `${a.title || ""} ${a.role || ""}`.includes("リーダー")
      );
      state.meetingChair = (leader || members[0]).name;
    }
  }

  function _roomTitle(room) {
    return room?.title?.trim() || t("meeting.default_title");
  }

  function _roomTime(room) {
    const value = room?.last_message_at || room?.closed_at || room?.created_at || "";
    if (!value) return "";
    try {
      return deps.smartTimestamp ? deps.smartTimestamp(value) : new Date(value).toLocaleString();
    } catch {
      return "";
    }
  }

  function _selectedProjectTask() {
    const department = state.meetingSelectedDepartment || "";
    const taskCode = state.meetingSelectedTaskCode || "";
    if (!department || !taskCode) return null;
    return (state.meetingProjectTasks || []).find(
      (task) => task.department === department && task.task_code === taskCode
    ) || null;
  }

  function _projectTaskTitle(room) {
    const code = room?.project_task_code || "";
    const title = room?.project_task_title || "";
    return [code, title].filter(Boolean).join(" ");
  }

  function _conversationToMessages(room) {
    return (room?.conversation || []).map((entry) => {
      const role = entry.role === "human" ? "user" : "assistant";
      const msg = {
        role,
        text: entry.text || "",
        timestamp: entry.ts || room.created_at || new Date().toISOString(),
      };
      if (role === "assistant") {
        msg.speaker = entry.speaker || "";
        msg.speakerRole = entry.role || "participant";
        msg.from_person = entry.speaker || "";
      }
      return msg;
    });
  }

  function _messageFingerprint(msg) {
    return [
      msg?.role || "",
      msg?.speaker || msg?.from_person || "",
      msg?.text || "",
    ].join("\u0001");
  }

  function _mergeLocalMeetingMessages(room, serverMessages) {
    if (!room?.room_id) return serverMessages;
    const existing = state.manager.getMessages("meeting", room.room_id) || [];
    if (!existing.length) return serverMessages;

    const serverKeys = new Set(serverMessages.map(_messageFingerprint));
    const localOnly = existing.filter((msg) => {
      if (!msg?._meetingLocal && !msg?.streaming) return false;
      return !serverKeys.has(_messageFingerprint(msg));
    });
    return localOnly.length ? [...serverMessages, ...localOnly] : serverMessages;
  }

  function _meetingRoundStatusHtml() {
    const current = state.meetingCurrentSpeaker || "";
    const queue = state.meetingSpeakerQueue || [];
    const completed = new Set(state.meetingCompletedSpeakers || []);
    const remaining = queue.filter((name) => name && name !== current && !completed.has(name));
    const next = remaining[0] || "";
    let label = "";
    if (current) {
      label = `発言中: ${current}`;
    } else if (state.meetingRoundStatus === "done") {
      label = "ラウンド完了";
    } else if (state.meetingRoundStatus === "waiting") {
      label = next ? `次の発言待ち: ${next}` : "次の発言待ち";
    } else if (state.meetingStreaming) {
      label = "発言者を確認中";
    }
    if (!label) return "";
    const rest = remaining.length > 1 ? `残り: ${remaining.slice(1).join(", ")}` : "";
    return `<div class="meeting-round-status ${current ? "is-speaking" : ""}">
      <span class="meeting-round-dot"></span>
      <span class="meeting-round-main">${escapeHtml(label)}</span>
      ${rest ? `<span class="meeting-round-rest">${escapeHtml(rest)}</span>` : ""}
    </div>`;
  }

  async function refreshMeetingRooms() {
    try {
      const url = state.meetingShowArchived
        ? "/api/rooms?include_closed=true&include_archived=true"
        : "/api/rooms?include_closed=true";
      const rooms = await api(url);
      state.meetingRooms = Array.isArray(rooms)
        ? rooms.sort((a, b) => new Date(b.last_message_at || b.created_at || 0) - new Date(a.last_message_at || a.created_at || 0))
        : [];
      _updateMeetingPanel();
    } catch (err) {
      deps.logger?.error?.("Failed to load meeting rooms", err);
    }
  }

  async function refreshProjectTasks() {
    try {
      const payload = await api("/api/rooms/project-tasks");
      const tasks = Array.isArray(payload?.tasks) ? payload.tasks : [];
      state.meetingProjectTasks = tasks;
      state.meetingProjectDepartments = Array.isArray(payload?.departments)
        ? payload.departments
        : [...new Set(tasks.map((task) => task.department).filter(Boolean))];
      if (
        state.meetingSelectedDepartment &&
        !state.meetingProjectDepartments.includes(state.meetingSelectedDepartment)
      ) {
        state.meetingSelectedDepartment = "";
        state.meetingSelectedTaskCode = "";
      }
      _updateMeetingPanel();
    } catch (err) {
      deps.logger?.error?.("Failed to load project tasks", err);
    }
  }

  function _renderProjectSelectors() {
    const departments = state.meetingProjectDepartments || [];
    const selectedDepartment = state.meetingSelectedDepartment || "";
    const allTasks = state.meetingProjectTasks || [];
    const tasks = allTasks.filter((task) => task.department === selectedDepartment && !task.corrupt);
    const corruptTasks = allTasks.filter((task) => task.corrupt);
    const selectedTask = _selectedProjectTask();
    const departmentOptions = [
      `<option value="">${escapeHtml(_label("meeting.project_department_placeholder", "部門を選択（任意）"))}</option>`,
      ...departments.map(
        (department) =>
          `<option value="${escapeHtml(department)}" ${department === selectedDepartment ? "selected" : ""}>${escapeHtml(department)}</option>`
      ),
    ].join("");
    const taskOptions = [
      `<option value="">${escapeHtml(_label("meeting.project_task_placeholder", "タスクコードを選択（任意）"))}</option>`,
      ...tasks.map((task) => {
        const label = `${task.task_code} ${task.title || ""}`.trim();
        return `<option value="${escapeHtml(task.task_code)}" ${task.task_code === state.meetingSelectedTaskCode ? "selected" : ""}>${escapeHtml(label)}</option>`;
      }),
    ].join("");

    const hint = selectedTask
      ? [selectedTask.status, selectedTask.next_action].filter(Boolean).join(" · ")
      : _label(
          "meeting.project_optional",
          "部門・タスクは任意です。空欄のままでもミーティングを開始できます",
        );

    const corruptBanner = corruptTasks.length
      ? `<div class="meeting-project-corrupt">⚠ ${escapeHtml(
          _label(
            "meeting.project_corrupt",
            "文字化けして読めないタスクノートがあります（cp932破損・要修復）",
          ),
        )}<ul>${corruptTasks
          .map((task) => {
            const recovered =
              task.title && task.title !== task.note_name ? ` — ${escapeHtml(task.title)}` : "";
            return `<li>${escapeHtml(task.note_name)}${recovered}</li>`;
          })
          .join("")}</ul></div>`
      : "";

    return `
      <div class="meeting-project-selectors">
        <label class="meeting-project-field">
          <span>${_label("meeting.project_department", "部門")}</span>
          <select data-chat-id="meetingProjectDepartmentSelect">${departmentOptions}</select>
        </label>
        <label class="meeting-project-field">
          <span>${_label("meeting.project_task", "タスクコード")}</span>
          <select data-chat-id="meetingProjectTaskSelect" ${selectedDepartment ? "" : "disabled"}>${taskOptions}</select>
        </label>
        <div class="meeting-project-hint">${escapeHtml(hint)}</div>
        ${corruptBanner}
      </div>`;
  }

  function _renderRoomList() {
    const rooms = state.meetingRooms || [];
    if (rooms.length === 0) {
      return `<div class="meeting-session-empty">${_label("meeting.sessions_empty", "保存済みのミーティングはありません")}</div>`;
    }
    return rooms
      .slice(0, 12)
      .map((room) => {
        const active = state.meetingRoom?.room_id === room.room_id;
        const statusParts = [];
        if (room.archived) statusParts.push(_label("meeting.archived", "アーカイブ"));
        statusParts.push(room.closed ? _label("meeting.closed", "終了") : _label("meeting.open", "進行中"));
        const status = statusParts.join(" · ");
        const count = Number(room.message_count || 0);
        const project = _projectTaskTitle(room);
        const roomId = escapeHtml(room.room_id);
        const archiveTitle = room.archived
          ? _label("meeting.unarchive", "アーカイブ解除")
          : _label("meeting.archive", "アーカイブ");
        return `
          <div class="meeting-session-row ${active ? "active" : ""} ${room.archived ? "is-archived" : ""}">
            <button type="button" class="meeting-session-item" data-room-id="${roomId}">
              <span class="meeting-session-title">${escapeHtml(_roomTitle(room))}</span>
              <span class="meeting-session-meta">${project ? `${escapeHtml(project)} · ` : ""}${escapeHtml(status)} · ${count} · ${escapeHtml(_roomTime(room))}</span>
            </button>
            <button type="button" class="meeting-session-rename" data-room-id="${roomId}" title="${_label("meeting.rename", "ミーティング名を変更")}">✎</button>
            <button type="button" class="meeting-session-archive" data-room-id="${roomId}" data-archived="${room.archived ? "1" : "0"}" title="${archiveTitle}">${room.archived ? "📤" : "📥"}</button>
            <button type="button" class="meeting-session-delete" data-room-id="${roomId}" title="${_label("meeting.delete", "削除")}">🗑</button>
          </div>`;
      })
      .join("");
  }

  function _renderSetupPanel(panel) {
    const isCoo = (a) =>
      `${a.title || ""} ${a.role || ""}`.toUpperCase().includes("COO");
    const DEPARTMENT_ORDER = ["全社", "Administration", "Property", "Finance", "Affiliate"];
    const deptRank = (a) => {
      const idx = DEPARTMENT_ORDER.indexOf((a.department || "").trim());
      return idx === -1 ? DEPARTMENT_ORDER.length : idx;
    };
    const titleRank = (a) => {
      const title = (a.title || "").trim();
      if (title.toUpperCase().includes("COO")) return 0;
      if (title.includes("グループリーダー")) return 1;
      if (title.includes("アソシエイト")) return 2;
      return 3;
    };
    const animas = state.animas
      .filter((a) => a.status === "running" || a.status === "idle")
      .sort(
        (a, b) =>
          (isCoo(b) ? 1 : 0) - (isCoo(a) ? 1 : 0) ||
          deptRank(a) - deptRank(b) ||
          (a.department || "").localeCompare(b.department || "", "ja") ||
          titleRank(a) - titleRank(b) ||
          (a.title || "").localeCompare(b.title || "", "ja") ||
          (a.role || "").localeCompare(b.role || "", "ja") ||
          (a.name || "").localeCompare(b.name || "", "ja")
      );
    const selected = new Set(state.meetingParticipants);
    const chair = state.meetingChair || null;

    let animaListHtml = "";
    let prevGroupKey = null;
    for (const a of animas) {
      // 役職は個人ごとにほぼ一意なので改行キーに含めると一人一行になってしまう。
      // 改行は部門の変わり目のみとし、同部門は横に連ねる。
      const groupKey = (a.department || "").trim();
      if (prevGroupKey !== null && groupKey !== prevGroupKey) {
        animaListHtml += `<span class="meeting-setup-anima-break" aria-hidden="true"></span>`;
      }
      prevGroupKey = groupKey;
      const isSelected = selected.has(a.name);
      const isChair = chair === a.name;
      const meta = _animaMeta(a);
      animaListHtml += `
        <label class="meeting-setup-anima ${isSelected ? "selected" : ""}" data-anima="${escapeHtml(a.name)}">
          <input type="checkbox" ${isSelected ? "checked" : ""} data-anima="${escapeHtml(a.name)}">
          <input type="radio" name="meeting-chair" value="${escapeHtml(a.name)}" ${isChair ? "checked" : ""} ${!isSelected ? "disabled" : ""}>
          ${_avatarHtml(a.name)}
          <span class="meeting-setup-anima-info">
            <span class="meeting-setup-anima-name">${escapeHtml(a.name)}${isChair ? " 👑" : ""}</span>
            ${meta ? `<span class="meeting-setup-anima-meta">${escapeHtml(meta)}</span>` : ""}
          </span>
        </label>`;
    }

    for (const a of animas) {
      ctx.controllers.anima?.ensureAnimaTabAvatar?.(a.name)?.then(() => {
        const avatarEl = panel.querySelector(`.meeting-setup-anima[data-anima="${a.name}"] .chip-avatar`);
        if (avatarEl) {
          const url = state.animaTabAvatarUrls?.[a.name];
          if (url) avatarEl.outerHTML = `<img class="chip-avatar chip-avatar-img" src="${escapeHtml(url)}" alt="${escapeHtml(a.name)}">`;
        }
      });
    }

    panel.innerHTML = `
      <div class="meeting-setup">
        <div class="meeting-setup-label">${t("meeting.select_participants")}</div>
        ${_renderProjectSelectors()}
        <div class="meeting-setup-anima-list">${animaListHtml || t("meeting.no_animas")}</div>
        <div class="meeting-setup-actions">
          <button type="button" class="meeting-start-btn" data-chat-id="meetingStartBtn" disabled>
            ${t("meeting.start")}
          </button>
        </div>
        <div class="meeting-session-list">
          <div class="meeting-session-list-head">
            <span>${_label("meeting.sessions", "ミーティングセッション")}</span>
            <div class="meeting-session-head-actions">
              <label class="meeting-session-archived-toggle" title="${_label("meeting.show_archived", "アーカイブを表示")}">
                <input type="checkbox" data-chat-id="meetingShowArchivedToggle" ${state.meetingShowArchived ? "checked" : ""}>
                <span>${_label("meeting.show_archived", "アーカイブを表示")}</span>
              </label>
              <button type="button" class="meeting-session-refresh" data-chat-id="meetingRefreshSessionsBtn" title="${_label("meeting.refresh", "再読み込み")}">↻</button>
            </div>
          </div>
          ${_renderRoomList()}
        </div>
      </div>`;

    panel.querySelectorAll(".meeting-session-item").forEach((btn) => {
      btn.addEventListener("click", () => loadRoom(btn.dataset.roomId));
    });

    panel.querySelectorAll(".meeting-session-rename").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        renameRoom(btn.dataset.roomId);
      });
    });

    panel.querySelectorAll(".meeting-session-archive").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        archiveRoom(btn.dataset.roomId, btn.dataset.archived !== "1");
      });
    });

    panel.querySelectorAll(".meeting-session-delete").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteRoom(btn.dataset.roomId);
      });
    });

    const archivedToggle = panel.querySelector('[data-chat-id="meetingShowArchivedToggle"]');
    if (archivedToggle) {
      archivedToggle.addEventListener("change", (e) => {
        state.meetingShowArchived = e.target.checked;
        refreshMeetingRooms();
      });
    }

    const refreshBtn = panel.querySelector('[data-chat-id="meetingRefreshSessionsBtn"]');
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        refreshMeetingRooms();
        refreshProjectTasks();
      });
    }

    const departmentSelect = panel.querySelector('[data-chat-id="meetingProjectDepartmentSelect"]');
    if (departmentSelect) {
      departmentSelect.addEventListener("change", (e) => {
        state.meetingSelectedDepartment = e.target.value || "";
        state.meetingSelectedTaskCode = "";
        _selectDepartmentMembers(state.meetingSelectedDepartment);
        _updateMeetingPanel();
      });
    }

    const taskSelect = panel.querySelector('[data-chat-id="meetingProjectTaskSelect"]');
    if (taskSelect) {
      taskSelect.addEventListener("change", (e) => {
        state.meetingSelectedTaskCode = e.target.value || "";
        _updateMeetingPanel();
      });
    }

    panel.querySelectorAll(".meeting-setup-anima").forEach((el) => {
      el.addEventListener("click", (e) => {
        const anima = el.dataset.anima;
        if (!anima) return;
        const checkbox = el.querySelector('input[type="checkbox"]');
        if (e.target === checkbox) return;
        const wasSelected = selected.has(anima);
        if (wasSelected) {
          selected.delete(anima);
          if (chair === anima) state.meetingChair = null;
        } else {
          selected.add(anima);
          if (!chair && selected.size > 0) state.meetingChair = anima;
        }
        state.meetingParticipants = [...selected];
        _updateMeetingPanel();
      });
    });

    panel.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", (e) => {
        e.stopPropagation();
        const anima = cb.dataset.anima;
        if (!anima) return;
        if (cb.checked) {
          selected.add(anima);
          if (!chair) state.meetingChair = anima;
        } else {
          selected.delete(anima);
          if (chair === anima) state.meetingChair = null;
        }
        state.meetingParticipants = [...selected];
        panel.querySelectorAll('input[type="radio"]').forEach((r) => {
          r.disabled = !selected.has(r.value);
          if (r.value === chair && !selected.has(r.value)) state.meetingChair = null;
        });
        _updateMeetingPanel();
      });
    });

    panel.querySelectorAll('input[type="radio"]').forEach((r) => {
      r.addEventListener("change", (e) => {
        state.meetingChair = e.target.value;
        _updateMeetingPanel();
      });
    });

    const startBtn = panel.querySelector('[data-chat-id="meetingStartBtn"]');
    if (startBtn) {
      startBtn.disabled = selected.size < 2 || !chair;
      startBtn.addEventListener("click", () => createRoom());
    }
  }

  function _syncActionDraft(room) {
    if (state.meetingActionRoomId !== room.room_id) {
      state.meetingActionRoomId = room.room_id;
      state.meetingActionItems = (room.action_items || []).map((it) => ({
        assignee: it.assignee || "",
        text: it.text || "",
        status: it.status || "draft",
      }));
    }
  }

  function _renderActionItemsHtml(room) {
    const open = state.meetingActionPanelOpen;
    const toggleLabel = open
      ? _label("meeting.action_items_hide", "決定事項を閉じる")
      : _label("meeting.action_items", "決定事項を配信");
    const toggleBtn = `<button type="button" class="meeting-action-toggle" data-chat-id="meetingActionToggle">${escapeHtml(toggleLabel)}</button>`;
    if (!open) {
      return `<div class="meeting-action-items">${toggleBtn}</div>`;
    }
    _syncActionDraft(room);
    const participants = room.participants || [];
    const items = state.meetingActionItems || [];
    const rowsHtml = items
      .map((it, idx) => {
        const sent = it.status === "sent";
        const opts = participants
          .map(
            (p) =>
              `<option value="${escapeHtml(p)}" ${p === it.assignee ? "selected" : ""}>${escapeHtml(p)}</option>`
          )
          .join("");
        return `
          <div class="meeting-action-row ${sent ? "is-sent" : ""}" data-idx="${idx}">
            <select class="meeting-action-assignee" data-idx="${idx}" ${sent ? "disabled" : ""}>
              <option value="">${_label("meeting.action_assignee", "担当")}</option>
              ${opts}
            </select>
            <textarea class="meeting-action-text" data-idx="${idx}" rows="2" ${sent ? "disabled" : ""} placeholder="${_label("meeting.action_text_placeholder", "やること")}">${escapeHtml(it.text)}</textarea>
            ${
              sent
                ? `<span class="meeting-action-sent-badge">${_label("meeting.action_sent", "配信済み")}</span>`
                : `<button type="button" class="meeting-action-remove" data-idx="${idx}" title="${_label("meeting.action_remove", "削除")}">✕</button>`
            }
          </div>`;
      })
      .join("");
    const emptyHtml = `<div class="meeting-action-empty">${_label("meeting.action_empty", "アクションアイテムはまだありません。AIで抽出するか、行を追加してください。")}</div>`;
    return `
      <div class="meeting-action-items is-open">
        <div class="meeting-action-head">${toggleBtn}</div>
        <div class="meeting-action-rows">${rowsHtml || emptyHtml}</div>
        <div class="meeting-action-actions">
          <button type="button" class="meeting-action-extract" data-chat-id="meetingActionExtract">${_label("meeting.action_extract", "AIで抽出")}</button>
          <button type="button" class="meeting-action-add" data-chat-id="meetingActionAdd">${_label("meeting.action_add", "行を追加")}</button>
          <button type="button" class="meeting-action-save" data-chat-id="meetingActionSave">${_label("meeting.action_save", "保存")}</button>
          <button type="button" class="meeting-action-dispatch" data-chat-id="meetingActionDispatch">${_label("meeting.action_dispatch", "配信")}</button>
        </div>
      </div>`;
  }

  function _wireActionItems(panel, room) {
    const toggle = panel.querySelector('[data-chat-id="meetingActionToggle"]');
    if (toggle) {
      toggle.addEventListener("click", () => {
        state.meetingActionPanelOpen = !state.meetingActionPanelOpen;
        if (state.meetingActionPanelOpen) {
          state.meetingActionRoomId = "";
          _syncActionDraft(room);
        }
        _renderActiveRoomPanel(panel);
      });
    }
    if (!state.meetingActionPanelOpen) return;

    panel.querySelectorAll(".meeting-action-assignee").forEach((sel) => {
      sel.addEventListener("change", () => {
        const idx = Number(sel.dataset.idx);
        if (state.meetingActionItems[idx]) {
          state.meetingActionItems[idx].assignee = sel.value;
        }
      });
    });
    panel.querySelectorAll(".meeting-action-text").forEach((area) => {
      area.addEventListener("input", () => {
        const idx = Number(area.dataset.idx);
        if (state.meetingActionItems[idx]) {
          state.meetingActionItems[idx].text = area.value;
        }
      });
    });
    panel.querySelectorAll(".meeting-action-remove").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.idx);
        state.meetingActionItems.splice(idx, 1);
        _renderActiveRoomPanel(panel);
      });
    });

    const extractBtn = panel.querySelector('[data-chat-id="meetingActionExtract"]');
    if (extractBtn) {
      extractBtn.addEventListener("click", () => _extractActionItems(panel, room, extractBtn));
    }
    const addBtn = panel.querySelector('[data-chat-id="meetingActionAdd"]');
    if (addBtn) {
      addBtn.addEventListener("click", () => {
        state.meetingActionItems.push({ assignee: "", text: "", status: "draft" });
        _renderActiveRoomPanel(panel);
      });
    }
    const saveBtn = panel.querySelector('[data-chat-id="meetingActionSave"]');
    if (saveBtn) {
      saveBtn.addEventListener("click", () => _saveActionItems(room));
    }
    const dispatchBtn = panel.querySelector('[data-chat-id="meetingActionDispatch"]');
    if (dispatchBtn) {
      dispatchBtn.addEventListener("click", () => _dispatchActionItems(panel, room, dispatchBtn));
    }
  }

  async function _extractActionItems(panel, room, btn) {
    btn.disabled = true;
    btn.textContent = _label("meeting.action_extracting", "抽出中…");
    try {
      const res = await api(`/api/rooms/${encodeURIComponent(room.room_id)}/action-items/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const sent = (state.meetingActionItems || []).filter((it) => it.status === "sent");
      const drafts = (res.items || []).map((it) => ({
        assignee: it.assignee || "",
        text: it.text || "",
        status: "draft",
      }));
      state.meetingActionItems = [...sent, ...drafts];
      if (!drafts.length) {
        window.alert(_label("meeting.action_extract_none", "抽出できる行動項目が見つかりませんでした"));
      }
    } catch (err) {
      deps.logger?.error?.("Failed to extract action items", err);
      window.alert(_label("meeting.action_extract_failed", "抽出に失敗しました"));
    } finally {
      _renderActiveRoomPanel(panel);
    }
  }

  function _collectDraftItems() {
    return (state.meetingActionItems || [])
      .map((it) => ({ assignee: (it.assignee || "").trim(), text: (it.text || "").trim() }))
      .filter((it) => it.text);
  }

  async function _saveActionItems(room) {
    try {
      const updated = await api(`/api/rooms/${encodeURIComponent(room.room_id)}/action-items`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: _collectDraftItems() }),
      });
      if (state.meetingRoom?.room_id === room.room_id) {
        state.meetingRoom = updated;
      }
      state.meetingActionRoomId = "";
      return true;
    } catch (err) {
      deps.logger?.error?.("Failed to save action items", err);
      window.alert(_label("meeting.action_save_failed", "保存に失敗しました"));
      return false;
    }
  }

  async function _dispatchActionItems(panel, room, btn) {
    const saved = await _saveActionItems(room);
    if (!saved) {
      _renderActiveRoomPanel(panel);
      return;
    }
    btn.disabled = true;
    try {
      const res = await api(`/api/rooms/${encodeURIComponent(room.room_id)}/action-items/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      await _refetchRoom(room.room_id);
      state.meetingActionRoomId = "";
      window.alert(
        _label("meeting.action_dispatched", "配信しました") + ` (${res.delivered ?? 0})`
      );
    } catch (err) {
      deps.logger?.error?.("Failed to dispatch action items", err);
      window.alert(_label("meeting.action_dispatch_failed", "配信に失敗しました"));
    } finally {
      _renderActiveRoomPanel(panel);
    }
  }

  function _renderActiveRoomPanel(panel) {
    const room = state.meetingRoom;
    if (!room) return;

    const participants = room.participants || [];
    const chair = room.chair || "";
    const projectTitle = _projectTaskTitle(room);

    let chipsHtml = participants
      .map((p) => {
        const name = typeof p === "string" ? p : p.name || p;
        const isChair = name === chair;
        return `
          <span class="meeting-participant-chip ${isChair ? "is-chair" : ""}" data-name="${escapeHtml(name)}">
            ${_avatarHtml(name)}
            <span>${escapeHtml(name)}</span>
            ${isChair ? " 👑" : ""}
            ${!isChair ? `<button type="button" class="chip-remove" data-name="${escapeHtml(name)}" title="${t("meeting.remove")}">✕</button>` : ""}
          </span>`;
      })
      .join("");

    panel.innerHTML = `
      <div class="meeting-session-active">
        <button type="button" class="meeting-title-btn" data-chat-id="meetingRenameBtn" title="${_label("meeting.rename", "ミーティング名を変更")}">
          ${escapeHtml(_roomTitle(room))}
        </button>
        ${room.closed ? `<span class="meeting-closed-badge">${_label("meeting.closed", "終了")}</span>` : ""}
        <button type="button" class="meeting-session-switch" data-chat-id="meetingSwitchBtn" title="${_label("meeting.sessions", "ミーティングセッション")}">▾</button>
      </div>
      ${projectTitle ? `<span class="meeting-project-chip">${escapeHtml(projectTitle)}</span>` : ""}
      ${_meetingRoundStatusHtml()}
      ${chipsHtml}
      ${room.closed ? "" : `<button type="button" class="meeting-add-btn" data-chat-id="meetingAddBtn">${t("meeting.add")} +</button>
      <button type="button" class="meeting-end-btn" data-chat-id="meetingEndBtn">${t("meeting.end")}</button>`}
      ${_renderActionItemsHtml(room)}`;

    _wireActionItems(panel, room);

    const renameBtn = panel.querySelector('[data-chat-id="meetingRenameBtn"]');
    if (renameBtn) {
      renameBtn.addEventListener("click", () => renameRoom());
    }

    const switchBtn = panel.querySelector('[data-chat-id="meetingSwitchBtn"]');
    if (switchBtn) {
      switchBtn.addEventListener("click", async () => {
        state.meetingRoom = null;
        await refreshMeetingRooms();
        _updateMeetingPanel();
        ctx.controllers.renderer?.renderChat();
        ctx.controllers.streaming?.updateSendButton?.();
      });
    }

    panel.querySelectorAll(".chip-remove").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const name = btn.dataset.name;
        if (name) removeParticipant(name);
      });
    });

    const addBtn = panel.querySelector('[data-chat-id="meetingAddBtn"]');
    if (addBtn) {
      addBtn.addEventListener("click", () => _showAddParticipantMenu(panel));
    }

    const endBtn = panel.querySelector('[data-chat-id="meetingEndBtn"]');
    if (endBtn) {
      endBtn.addEventListener("click", () => endMeeting());
    }
  }

  function _showAddParticipantMenu(panel) {
    const room = state.meetingRoom;
    if (!room) return;

    const current = new Set((room.participants || []).map((p) => (typeof p === "string" ? p : p.name || p)));
    const available = state.animas.filter(
      (a) =>
        (a.status === "running" || a.status === "idle") && !current.has(a.name)
    );

    if (available.length === 0) {
      return;
    }

    const menu = document.createElement("div");
    menu.className = "meeting-add-menu";
    menu.innerHTML = available
      .map(
        (a) =>
          `<button type="button" class="meeting-add-item" data-name="${escapeHtml(a.name)}">${_avatarHtml(a.name)} ${escapeHtml(a.name)}</button>`
      )
      .join("");

    menu.querySelectorAll(".meeting-add-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        addParticipant(btn.dataset.name);
        menu.remove();
      });
    });

    const addBtn = panel.querySelector('[data-chat-id="meetingAddBtn"]');
    if (addBtn) {
      const existing = panel.querySelector(".meeting-add-menu");
      if (existing) existing.remove();
      addBtn.after(menu);
    }
  }

  async function createRoom() {
    const participants = [...state.meetingParticipants];
    const chair = state.meetingChair;
    if (participants.length < 2 || !chair) return;

    const task = _selectedProjectTask();
    const department = state.meetingSelectedDepartment || "";
    const defaultTitle = task
      ? `${task.task_code} ${task.title}`.trim()
      : department || t("meeting.default_title");

    try {
      const res = await api("/api/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          participants,
          chair,
          title: state.meetingRoomTitle || defaultTitle || t("meeting.default_title"),
          project_department: task ? task.department : department,
          project_task_code: task ? task.task_code : "",
          project_note_path: task ? task.note_path : "",
          project_task_title: task ? task.title : "",
        }),
      });
      state.meetingRoom = res;
      await refreshMeetingRooms();
      _updateMeetingPanel();
      const input = $("chatPageInput");
      if (input) input.placeholder = t("meeting.placeholder");
      ctx.controllers.streaming?.updateSendButton?.();
      ctx.controllers.renderer?.renderChat();
    } catch (err) {
      deps.logger?.error?.("Failed to create meeting room", err);
    }
  }

  async function _refetchRoom(roomId) {
    try {
      const room = await api(`/api/rooms/${encodeURIComponent(roomId)}`);
      state.meetingRoom = room;
    } catch (err) {
      deps.logger?.error?.("Failed to refetch room", err);
    }
  }

  async function loadRoom(roomId) {
    if (!roomId) return;
    try {
      const room = await api(`/api/rooms/${encodeURIComponent(roomId)}`);
      state.meetingMode = true;
      state.meetingRoom = room;
      state.meetingParticipants = room.participants || [];
      state.meetingChair = room.chair || null;
      state.meetingSelectedDepartment = room.project_department || "";
      state.meetingSelectedTaskCode = room.project_task_code || "";
      const serverMessages = _conversationToMessages(room);
      state.manager.setMessages("meeting", room.room_id, _mergeLocalMeetingMessages(room, serverMessages));
      _updateToggleUI();
      _updateMeetingPanel();
      _updateAnimaTabsVisibility();
      const input = $("chatPageInput");
      if (input) input.placeholder = room.closed ? _label("meeting.closed_placeholder", "このミーティングは終了済みです") : t("meeting.placeholder");
      ctx.controllers.renderer?.renderChat();
      ctx.controllers.streaming?.updateSendButton?.();
    } catch (err) {
      deps.logger?.error?.("Failed to load meeting room", err);
    }
  }

  async function renameRoom(targetRoomId) {
    const activeRoom = state.meetingRoom;
    const roomId = targetRoomId || activeRoom?.room_id;
    if (!roomId) return;
    const listed = (state.meetingRooms || []).find((r) => r.room_id === roomId);
    const currentRoom = activeRoom?.room_id === roomId ? activeRoom : listed;
    const nextTitle = window.prompt(
      _label("meeting.rename_prompt", "ミーティング名"),
      _roomTitle(currentRoom)
    );
    if (nextTitle == null) return;
    try {
      const updated = await api(`/api/rooms/${encodeURIComponent(roomId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: nextTitle }),
      });
      if (activeRoom?.room_id === roomId) {
        state.meetingRoom = updated;
      }
      await refreshMeetingRooms();
      _updateMeetingPanel();
    } catch (err) {
      deps.logger?.error?.("Failed to rename meeting room", err);
    }
  }

  async function archiveRoom(roomId, archived) {
    if (!roomId) return;
    try {
      await api(`/api/rooms/${encodeURIComponent(roomId)}/archive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: Boolean(archived) }),
      });
      if (archived && state.meetingRoom?.room_id === roomId) {
        state.meetingRoom = null;
      }
      await refreshMeetingRooms();
      _updateMeetingPanel();
    } catch (err) {
      deps.logger?.error?.("Failed to archive meeting room", err);
    }
  }

  async function deleteRoom(roomId) {
    if (!roomId) return;
    const confirmed = window.confirm(
      _label("meeting.delete_confirm", "このミーティングセッションを完全に削除しますか？この操作は取り消せません。")
    );
    if (!confirmed) return;
    try {
      await api(`/api/rooms/${encodeURIComponent(roomId)}`, { method: "DELETE" });
      if (state.meetingRoom?.room_id === roomId) {
        state.meetingRoom = null;
      }
      await refreshMeetingRooms();
      _updateMeetingPanel();
    } catch (err) {
      deps.logger?.error?.("Failed to delete meeting room", err);
    }
  }

  async function addParticipant(name) {
    const room = state.meetingRoom;
    if (!room?.room_id) return;

    try {
      await api(`/api/rooms/${encodeURIComponent(room.room_id)}/participants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      await _refetchRoom(room.room_id);
      await refreshMeetingRooms();
      _updateMeetingPanel();
    } catch (err) {
      deps.logger?.error?.("Failed to add participant", err);
    }
  }

  async function removeParticipant(name) {
    const room = state.meetingRoom;
    if (!room?.room_id) return;

    try {
      await api(
        `/api/rooms/${encodeURIComponent(room.room_id)}/participants/${encodeURIComponent(name)}`,
        { method: "DELETE" }
      );
      await _refetchRoom(room.room_id);
      await refreshMeetingRooms();
      _updateMeetingPanel();
    } catch (err) {
      deps.logger?.error?.("Failed to remove participant", err);
    }
  }

  async function endMeeting() {
    const room = state.meetingRoom;
    if (!room?.room_id) return;

    try {
      await api(`/api/rooms/${encodeURIComponent(room.room_id)}/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
    } catch (err) {
      deps.logger?.error?.("Failed to close meeting", err);
    }
    state.meetingRoom = null;
    state.meetingMode = state.meetingStandalone ? true : false;
    await refreshMeetingRooms();
    _updateToggleUI();
    _updateMeetingPanel();
    _updateAnimaTabsVisibility();
    ctx.controllers.renderer?.renderChat();
    ctx.controllers.streaming?.updateSendButton?.();
  }

  return {
    init,
    toggleMeetingMode,
    createRoom,
    loadRoom,
    refreshMeetingRooms,
    renameRoom,
    archiveRoom,
    deleteRoom,
    addParticipant,
    removeParticipant,
    endMeeting,
    isActive: () => Boolean(state.meetingMode && state.meetingRoom != null && !state.meetingRoom.closed),
    getRoom: () => state.meetingRoom,
    updatePanel: _updateMeetingPanel,
  };
}
