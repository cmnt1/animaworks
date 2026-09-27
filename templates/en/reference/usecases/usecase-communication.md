# Use case: Communication automation

This use case automates the monitoring and handling of external chat tools and email.

---

## Problems this can solve

- Replies to chat or email tend to be delayed
- Cannot monitor multiple channels at the same time
- Important messages get overlooked
- Cannot respond to contact at night or on holidays
- Regular updates to external partners are forgotten

---

## Pattern 1: Periodic monitoring of chat tools

### What it does
Anima checks for new messages in chat tools at fixed intervals (e.g., every 30 minutes) and responds according to the content.

### How it works
1. Retrieve new messages from the specified channel during periodic checks
2. Analyze the message content (assess urgency and whether a response is needed)
3. Branch processing based on the response pattern:
   - **Content you can handle yourself** → Reply directly
   - **Requires human judgment** → Notify a human and ask for their decision
   - **Intended for another person in charge** → Forward to the appropriate internal Anima
   - **No response needed** → Record in the log and move on

### Example uses
- Immediately reply "We'll check and get back to you" to a client's delivery date confirmation
- Detect urgent contact from a customer and send an alert notification to a human
- Automatically send template responses to frequently asked questions

### What you need to get started
- API integration configuration for the chat tool
- Specification of the channels or groups to monitor
- Response rules (what to auto-reply to and what to escalate)

---

## Pattern 2: Email handling automation

### What it does
Periodically checks incoming email and automates classification, replies, and forwarding.

### How it works
1. Periodically check the mailbox
2. Classify content based on subject, sender, and body:
   - Invoices and receipts → Forward to the accounting person in charge
   - Inquiries → Forward to the customer support person in charge
   - Sales emails and spam → Ignore (log only)
   - Important contact → Notify a human
3. Automatically send acknowledgment emails as needed

### Example uses
- Receive a "quote request" email → Notify a human that "a quote request has arrived"
- Alert emails from external services → Summarize the content and forward to the monitoring person in charge
- Standard inquiries → Save a draft template reply (a human reviews it before sending)

### Points to note
- Set the scope of emails to send automatically with care
- Starting with "draft only" and having a human confirm before sending is safer
- Always notify a human for emails from important business partners

---

## Pattern 3: Escalation automation

### What it does
Monitors multiple channels (chat, email, SNS, etc.) across the board and escalates to the appropriate person based on importance.

### How it works
1. Periodically monitor each channel
2. Determine the importance of the message:
   - **Urgent** (service outage, complaints, etc.) → Notify a human immediately
   - **Important** (content related to contracts or money) → Report to a human at the next check
   - **Normal** (everyday inquiries) → Anima attempts to handle it
   - **Low** (information sharing only) → Record in the log
3. When escalating, include a summary and recommended action

### Example uses
- A server outage alert arrives late at night → Send an urgent notification to a human's smartphone
- A business partner sends a contract change notice → Present a summary when the human arrives at work the next morning
- An employee submits a paid leave request → Tentatively register it in the calendar and request approval from a human

---

## Pattern 4: Regular contact automation

### What it does
Automatically sends standard messages to specified recipients at fixed times.

### How it works
1. Configure the schedule (daily, weekly, monthly, etc.)
2. Create the message when the specified time arrives
3. Send it to the specified channel or recipient
4. Record the send result in the log

### Example uses
- Post a "today's schedule summary" to chat every morning at 9:00
- Send a "weekly activity report" to stakeholders every Friday
- Notify the accounting person in charge of an "invoice sending reminder" at the end of each month
- Automatically report project progress to stakeholders on a weekly basis

---

## Pattern 5: Multilingual communication support

### What it does
Automatically translates and summarizes messages received in foreign languages.

### How it works
1. Detect a foreign language message
2. Translate and summarize the content
3. Report to a human in their native language that "a message with this content has arrived"
4. Create a draft reply in the foreign language as needed

### Example uses
- English email from an overseas business partner → Summarize and report in Japanese
- Mentions of your company on overseas SNS → Translate and share
- Inquiries in multiple languages → Create reply drafts in each language

---

## Configuration tips

### Minimum configuration (1 Anima)
- Monitor multiple channels with a single instance
- Branch responses using simple rule-based logic
- Escalate everything to a human when uncertain

### Recommended configuration (2–3 Anima)
- **Monitoring and routing role**: Monitors all channels and classifies content
- **Response role**: Executes replies and processing for classified messages
- Dividing roles ensures both monitoring coverage and response quality

### Large-scale configuration
- Assign a dedicated monitoring Anima to each channel
- A coordinating Anima manages the overall picture
- Humans only need to check the summary from the coordinating Anima