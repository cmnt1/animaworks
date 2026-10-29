# Use case: Secretary and administrative support

This use case automates daily administrative work such as schedule management, coordination, reminders, and information organization.

---

## Problems this can solve

- Can't keep up with schedule management
- Forgetting meetings and deadlines
- Time spent on contacting and coordinating with stakeholders
- Creating daily and weekly reports is tedious
- Can't keep track of progress across multiple projects

---

## Pattern 1: Schedule management and reminders

### What it does
Monitors the calendar and handles appointment reminders and free-time management.

### How it works
1. Every morning, retrieves the schedule for the current day and the next day
2. Sends the human a "today's schedule summary"
3. Sends a reminder before each appointment (e.g., 30 minutes before)
4. Detects scheduling conflicts or insufficient free time and issues a warning

### Example uses
- Every morning at 8:00: "You have 3 appointments today. 10:00: ○○ meeting, 14:00: ○○ interview, 16:00: ○○ deadline"
- 30 minutes before a meeting: "Your ○○ meeting is coming up soon. Materials are here"
- "You have no free time tomorrow morning. Would you like to move the ○○ appointment?"

### Extensions
- When a new appointment is added to the calendar, prepare related materials in advance
- Before recurring meetings, organize the previous minutes and this session's agenda and send them out
- Propose realistic schedules that account for travel time

---

## Pattern 2: Automating coordination

### What it does
Handles scheduling with multiple stakeholders and relays messages on your behalf.

### How it works
1. Receives an instruction from the human: "Set up a meeting with ○○ next week"
2. Extracts available time slots from the human's calendar
3. Sends candidate dates and times to the stakeholders
4. Collects responses and proposes the best time
5. Registers the confirmed time in the calendar

### Example uses
- "Set up a meeting with the ○○ team sometime next week" → Presents 3 candidates
- Emails an external partner: "We'd like to confirm the date for the next regular meeting"
- Automatically coordinates scheduling for meetings with many participants, then notifies everyone once confirmed

### Notes
- It's safer to send external communications only after human confirmation
- For important business meetings, ask the human to do a final confirmation

---

## Pattern 3: Automatic daily and progress report creation

### What it does
Collects the day's activity logs and results, and automatically generates standard reports.

### How it works
1. At a specified time (e.g., 5:00 PM daily), collects the day's activity data
2. Compiles sent and received messages, completed tasks, and events that occurred
3. Creates a report following a template
4. Sends it to the human for review (or posts it automatically)

### Example uses
- Automatically generates daily work reports
- Creates weekly project progress summaries
- Generates a monthly activity statistics report at the end of the month

### Template example
```
== 本日の活動サマリー ==
■ 完了タスク: 5件
  - タスクA（完了）
  - タスクB（完了）
  ...
■ 受信メッセージ: 12件（対応済み10件、保留2件）
■ 発生イベント: 特になし
■ 明日の予定: 3件
```

---

## Pattern 4: Information gathering and briefing

### What it does
Collects the necessary information first thing in the morning and delivers it as a concise briefing.

### How it works
1. At a specified morning time, collects various information:
   - Summary of unread messages
   - Today's schedule
   - Status of ongoing tasks
   - News and market data (if configured)
2. Organizes by priority
3. Sends it as "Good morning. Here is today's briefing"

### Example uses
- "You have 2 important messages that arrived overnight"
- "Your top priority task today is the ○○ deadline"
- "Yesterday's sales were ○○ yen. Up 5% from the previous week"

---

## Pattern 5: Task management and progress tracking

### What it does
Centrally manages task registration, progress tracking, and reminders.

### How it works
1. Extracts and registers tasks from the human's instructions and messages
2. Sets reminders based on deadlines
3. Periodically checks and reports on progress
4. Flags tasks that have passed their deadline

### Example uses
- "Send the quote by next Friday" → Task registration + reminder on Friday morning
- "Check the progress of ○○ weekly" → Status check and report every Monday
- Sends reminders 3 days before, 1 day before, and on the day of the deadline

---

## Pattern 6: Expense and invoice management support

### What it does
Supports organizing invoices and expense reports, and sends reminders.

### How it works
1. Detects invoices received via email or chat
2. Extracts the amount, payment deadline, and sender, and compiles a list
3. Sends a reminder before the payment deadline
4. Reports a list of unpaid invoices at the end of the month

### Example uses
- "You have 3 unpaid invoices this month, totaling ○○ yen"
- "The payment deadline for the invoice from ○○ company is in 3 days"
- Automatically creates a monthly expense list

---

## Configuration tips

### Minimal configuration (one Anima)
- A single "secretary Anima" handles everything
- Schedule management + message monitoring + reminders as the basic set
- Even this alone provides "the peace of mind that someone is always watching over you"

### Recommended configuration
- **Secretary Anima**: Schedule, communication, and reminders
- **Report Anima**: Automatic generation of daily reports, weekly reports, and progress reports
- Dividing the work between two Animas distributes the secretary's workload

### Tips for effective operation
- Even reminders alone are effective to start with
- Start by automating "the things humans tend to forget"
- For important communications, start with a "draft → human confirmation → send" flow
- Gradually expand the scope of automation as you become more comfortable
