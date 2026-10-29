"""Structural host protocols for the compositional mixins."""

from __future__ import annotations

from typing import Any, Protocol


class _MessagingHost(Protocol):
    """Structural host members used by MessagingMixin."""

    _active_chat_conversations: Any
    _activity: Any
    _delivery_via_label: Any
    _get_interrupt_event: Any
    _get_thread_lock: Any
    _interrupt_events: Any
    _last_activity: Any
    _log_human_conversation: Any
    _mark_busy_start: Any
    _notify_lock_released: Any
    _resolve_chat_external_recipient: Any
    _schedule_live_fact_extraction: Any
    _send_chat_reply_via_resolved: Any
    _session_compactor: Any
    _status_slots: Any
    _sync_interactive_bootstrap_state: Any
    _task_slots: Any
    _validate_thread_id: Any
    agent: Any
    anima_dir: Any
    memory: Any
    model_config: Any
    name: Any
    needs_bootstrap: Any
    primary_status: Any
    primary_task: Any
    process_message_stream: Any


class _InboxHost(Protocol):
    """Structural host members used by InboxMixin."""

    _activity: Any
    _agent_for_lane: Any
    _agent_session_context: Any
    _archive_processed_messages: Any
    _get_interrupt_event: Any
    _inbox_lock: Any
    _last_activity: Any
    _mark_busy_start: Any
    _notify_lock_released: Any
    _process_inbox_messages: Any
    _resolve_background_config: Any
    _schedule_live_fact_extraction: Any
    _status_slots: Any
    _task_slots: Any
    _undo_failed_inbox_presentation: Any
    agent: Any
    anima_dir: Any
    memory: Any
    messenger: Any
    name: Any


class _HeartbeatHost(Protocol):
    """Structural host members used by HeartbeatMixin."""

    _HEARTBEAT_HISTORY_N: Any
    _PLAN_OUTCOME_MAX_CHARS: Any
    _RECENT_REFLECTIONS_N: Any
    _activity: Any
    _agent_for_lane: Any
    _archive_heartbeat_md_before_cleanup: Any
    _build_background_context_parts: Any
    _build_heartbeat_md_cleanup_instruction: Any
    _build_state_cleanup_instruction: Any
    _dialogue_is_recent: Any
    _enforce_state_size_limit: Any
    _get_current_state_cleanup_chars: Any
    _get_current_state_max_chars: Any
    _get_heartbeat_md_max_bytes: Any
    _get_recent_dialogue_max_age_hours: Any
    _last_activity: Any
    _load_heartbeat_history: Any
    _load_recent_reflections: Any
    _resolve_background_config: Any
    agent: Any
    anima_dir: Any
    drain_background_notifications: Any
    memory: Any
    model_config: Any
    name: Any


class _LifecycleHost(Protocol):
    """Structural host members used by LifecycleMixin."""

    _active_cron_commands: Any
    _activity: Any
    _background_lock: Any
    _build_cron_prompt: Any
    _build_heartbeat_prompt: Any
    _build_prior_messages: Any
    _enforce_state_size_limit: Any
    _execute_heartbeat_cycle: Any
    _finalize_session_if_ended: Any
    _get_interrupt_event: Any
    _handle_hard_timeout: Any
    _handle_heartbeat_failure: Any
    _keepalive_while_busy: Any
    _last_activity: Any
    _last_heartbeat: Any
    _last_progress_at: Any
    _mark_busy_progress: Any
    _mark_busy_start: Any
    _notify_lock_released: Any
    _resolve_background_config: Any
    _run_autonomous_skill_learning: Any
    _run_daily_consolidation: Any
    _run_heartbeat_agent_session: Any
    _run_weekly_consolidation: Any
    _status_slots: Any
    _task_slots: Any
    _trigger_pending_task_execution: Any
    _write_busy_status_sidecar: Any
    anima_dir: Any
    memory: Any
    messenger: Any
    model_config: Any
    name: Any
