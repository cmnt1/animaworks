# Use Case: Secretary and Administrative Support

This use case automates daily administrative tasks such as schedule management, communication coordination, reminders, and information organization.

---

## Problems This Can Solve

- Can't keep up with schedule management
- Forgetting meetings and deadlines
- Time consumed by contacting and coordinating with stakeholders
- Creating daily and weekly reports is tedious
- Can't keep track of progress across multiple projects

---

## Pattern 1: Schedule Management and Reminders

### What It Does
Monitors the calendar and manages reminders for appointments and available time slots.

### How It Works
1. Every morning, retrieves the schedule for today and tomorrow
2. Sends a "daily schedule summary" to the human
3. Sends reminders before each appointment (e.g., 30 minutes prior)
4. Detects scheduling conflicts or insufficient free time and issues warnings

### Example Uses
- Every morning at 8:00: "You have 3 appointments today. 10:00: Meeting with ○○, 14:00: Interview with ○○, 16:00: Deadline for ○○"
- 30 minutes before a meeting: "Your meeting with ○○ starts soon. Materials are here"
- "You have no free time tomorrow morning. Would you like to move the ○○ appointment?"

### Extensions
- When a new appointment is added to the calendar, prepare related materials in advance
- Before recurring meetings, organize and send the previous minutes and the current agenda
- Propose realistic schedules that account for travel time

---

## Pattern 2: Automating Communication Coordination

### What It Does
Handles scheduling with multiple stakeholders and relays messages on behalf of the human.

### How It Works
1. Receives instruction from the human: "Set up a meeting with ○○ next week"
2. Extracts available time slots from the human's calendar
3. Sends candidate dates and times to the relevant parties
4. Collects responses and proposes the best time
5. Registers the confirmed time in the calendar

### Example Uses
- "Set up a meeting with the ○○ team sometime next week" → Presents 3 candidate options
- Sends an email to an external partner: "We'd like to confirm the date for the next regular meeting"
- Automatically coordinates schedules for meetings with many participants, then notifies everyone once confirmed

### Notes
- It's safer to send external communications only after human confirmation
- For important business negotiations, ask the human for final confirmation on the schedule

---

## Pattern 3: Automatic Daily and Progress Reports

### What It Does
Collects daily activity logs and results, and automatically generates standardized reports.

### How It Works
1. At a specified time (e.g., 5:00 PM daily), collects the day's activity data
2. Compiles sent and received messages, completed tasks, and events that occurred
3. Creates a report following a template
4. Sends it to the human for review (or posts it automatically)

### Example Uses
- Automatically generates daily work reports
- Creates weekly project progress summaries
- Generates monthly activity statistics reports at the end of the month

### Template Example
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

## Pattern 4: Information Gathering and Briefing

### What It Does
Collects necessary information first thing in the morning and delivers it as a concise briefing.

### How It Works
1. At the specified morning time, gathers various information:
   - Summary of unread messages
   - Today's schedule
   - Status of ongoing tasks
   - News and market data (if configured)
2. Organizes by priority
3. Sends it as "Good morning. Here is today's briefing"

### Example Uses
- "You have 2 important messages that arrived overnight"
- "Your top priority task today is the deadline for ○○"
- "Yesterday's sales were ○○ yen. Up 5% from the previous week"

---

## Pattern 5: Task Management and Progress Tracking

### What It Does
Centrally manages task registration, progress tracking, and reminders.

### How It Works
1. Extracts and registers tasks from the human's instructions and messages
2. Sets reminders based on deadlines
3. Periodically checks and reports progress
4. Alerts on overdue tasks

### Example Uses
- "Send the quote by next Friday" → Task registered + reminder on Friday morning
- "Check the progress of ○○ weekly" → Status check and report every Monday
- Sends reminders 3 days before, 1 day before, and on the day of the deadline

---

## Pattern 6: Expense and Invoice Management Support

### What It Does
Supports organizing invoices and expense reports, and sending reminders.

### How It Works
1. Detects invoices received via email or chat
2. Extracts the amount, payment deadline, and sender, and compiles a list
3. Sends reminders before the payment deadline
4. Reports a list of unpaid invoices at the end of the month

### Example Uses
- "You have 3 unpaid invoices this month, totaling ○○ yen"
- "The payment deadline for the invoice from ○○ company is in 3 days"
- Automatically creates a monthly expense list

---

## Configuration Tips

### Minimal Setup (One Anima)
- A single "Secretary Anima" handles everything
- Schedule management + message monitoring + reminders as the basic set
- Even this alone provides "the peace of mind that someone is always watching"

### Recommended Setup
- **Secretary Anima**: Schedule, communication, and reminders
- **Report Anima**: Automatic generation of daily reports, weekly reports, and progress reports
- Dividing the work between two Animas distributes the secretary's workload

### Tips for Effective Operation
- Even just reminders alone can be highly effective at first
- Start by automating "things humans tend to forget"
- For important communications, begin with the flow: "draft → human confirmation → send"
- Gradually expand the scope of automation as you become more comfortable