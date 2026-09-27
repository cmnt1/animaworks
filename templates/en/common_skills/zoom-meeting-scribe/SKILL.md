---
name: zoom-meeting-scribe
description: >-
  Zoom meeting listening workflow. Silently understand and record meeting transcripts received via RTMS, escalate only urgent matters to the supervisor, and post a report after obtaining human approval once the meeting ends.
  Use when: Use when: receiving an inbox message from source=zoom (with a "[Zoom meeting live chunk #N …]" or "[Zoom meeting ended …]" header).
tags: [zoom, meeting, transcript, report, workflow]
---
Understood. Please provide the Japanese content you’d like me to translate, and I’ll follow all the specified rules.# Skill: Zoom Meeting Scribe (Transcription, Summary, and Report with Approval)

The Zoom RTMS gateway injects meeting transcripts into your inbox in chunks of a few minutes each. Your role is to understand and organize the content as a **listening-only participant**, compile a report after the meeting ends, and **post it only after receiving human approval**.## Format of Incoming Messages

| Type | Header | Meaning |
|------|--------|---------|
| Live chunk | `[Zoom会議実況 チャンク#N \| 会議: {題名} ({会議ID}) \| {開始時刻}〜]` | Speech during the meeting (followed by lines of speaker name: utterance) |
| End notification | `[Zoom会議終了 \| 会議: {題名} ({会議ID}) \| 全Nチャンク配信済み]` | Meeting ended. Signal to create the report |

- Chunks from the same meeting arrive in the same thread (`zoom-{会議UUID}`)
- If `[接続断により一部欠落]` appears at the start of a chunk, the immediately preceding utterance may be lost. Note the possibility of missing content in the report
- Speaker names are Zoom display names. "Unknown" refers to utterances where the speaker could not be identified## Workflow### 1. When receiving a live chunk — stay silent and take it in

- Read the content and organize it step by step into your own notes (working memory or notes):
  - **Decisions** (who decided what)
  - **Action items** (owner and deadline)
  - **Open questions or carry-over items**
  - Key points of the meeting flow
- **Do not reply, post to the channel, or intervene in the meeting at all**. You are the listener
- If you notice a missing chunk number, treat it as a gap in the sequence### 2. Immediate Escalation of Urgent Matters (Exceptions)

Even during a meeting, if you detect any of the following, report the key points to your supervisor (the supervisor shown in your organization context) via `send_message` **at that moment**:

- Reports of incidents, accidents, or security issues
- Decisions or requests with deadlines falling on the current day or the next business day
- Explicit action requests addressed to you or your team
- Mentions of significant legal or financial risks

If you have no supervisor (i.e., you are at the top), notify a human directly via `call_human`. Record the fact of the escalation in your notes and include it in the final report.### 3. Meeting End — Report Creation

Upon receiving the end notification, create a report from the accumulated notes and conversation history using the following structure:

```
# 会議レポート: {会議名}
- 日時: {開始〜終了}
- 参加者: {発話者一覧}

## 決定事項
- …

## アクションアイテム
| 項目 | 担当 | 期限 |

## 議論の要点
- …

## エスカレーション済み事項
- …（なければ「なし」）

## 備考
- （トランスクリプト欠落の可能性等）
```

If there is little speech or only casual conversation and the content is not worth reporting, you may briefly record that fact and end the process (no approval flow is required).### 4. Human Approval — Do Not Post Before Approval

Present the report text to a human via `call_human` and request approval:

```
call_human(
  subject="会議レポート承認依頼: {会議名}",
  body="{レポート全文}",
  interactive=true,
  options=["approve", "reject", "comment"]
)
```

- **Do not post the report anywhere until approval is received**
- call_human does not require waiting (fire-and-resume). Once the approval request is sent, this turn may end. The human's decision will arrive later as a new inbox message
- **If reject / comment is returned**: revise the report to address the feedback, then request approval again via call_human### 5. After Approval — Posting

Once approval is received, post the report to the **Board channel specified in the operational instructions (e.g., injection)** using `post_channel`:

```
post_channel(channel="{指定されたBoard名}", content="{承認済みレポート}")
```

If no target Board is specified in the instructions, do not post; instead, inform the supervisor (or a human, if none) that the approved report is ready and ask for further instruction.## Prohibited Actions

- Posting replies, live commentary, or progress updates on chunks during a meeting
- Posting or externally sharing reports before approval
- Reposting transcript content to unrelated channels (meeting content includes participants' privacy)## Operational Configuration (Reference)

This skill itself does not fix the posting destination or the person in charge. The following is determined by each Anima's operational configuration:

- Which meetings reach which Anima: server configuration `external_messaging.zoom.meeting_mapping`
- Report posting destination Board: specified by operational instruction (injection, etc.) to each Anima
- Escalation destination: follows the organization structure (supervisor)