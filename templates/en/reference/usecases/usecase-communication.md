# Use case: Communication automation

This use case automates the monitoring and handling of external chat tools and email.

---

## Problems this can solve

- Replies to chat or email tend to be delayed
- Cannot monitor multiple channels at the same time
- Important messages get overlooked
- Cannot respond to contacts at night or on holidays
- Forgetting regular updates to external partners

---

## Pattern 1: Periodic monitoring of chat tools

### What it does
Anima checks for new messages in chat tools at set intervals (e.g., every 30 minutes) and responds based on the content.

### How it works
1. Periodically fetch new messages from the specified channel
2. Analyze the message content (assess urgency and whether a response is needed)
3. Branch processing based on the response pattern:
   - **Content you can handle yourself** → Reply directly
   - **Requires human judgment** → Notify a human and ask for their decision
   - **Intended for another person in charge** → Forward to the appropriate internal Anima
   - **No response needed** → Record in the log and move on

### Example uses
- Instantly reply to a client's delivery date confirmation with "We'll check and get back to you"
- Detect urgent customer messages and send an alert notification to a human
- Automatically send template answers for frequently asked questions

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
   - Important communications → Notify a human
3. Automatically send acknowledgment emails as needed

### Example uses
- Receive a "quote request" email → Notify a human that "a quote request has arrived"
- External service alert emails → Summarize the content and forward to the monitoring person in charge
- Standard inquiries → Save a draft template reply (a human reviews it before sending)

### Points to note
- Set the scope of emails to auto-send carefully
- Starting with "draft only" and having a human review before sending is safer
- Always notify a human for emails from important clients

---

## Pattern 3: Escalation automation

### What it does
Monitors multiple channels (chat, email, SNS, etc.) across the board and escalates to the appropriate person based on importance.

### How it works
1. Periodically monitor each channel
2. Assess the importance of messages:
   - **Urgent** (service outages, complaints, etc.) → Notify a human immediately
   - **Important** (content related to contracts or money) → Report to a human at the next check
   - **Normal** (everyday inquiries) → Anima attempts to handle it
   - **Low** (information sharing only) → Record in the log
3. When escalating, include a summary and recommended action

### Example uses
- A server outage alert arrives late at night → Send an urgent notification to a human's smartphone
- A client sends a contract change notice → Present a summary when the human comes to work the next morning
- An employee submits a paid leave request → Tentatively register it in the calendar and request approval from a human

---

## Pattern 4: Regular communication automation

### What it does
Automatically sends standard communications to the right people at set times.

### How it works
1. Configure the schedule (daily, weekly, monthly, etc.)
2. Create the message when the specified time arrives
3. Send it to the specified channel or recipient
4. Record the send result in the log

### Example uses
- Post a "today's schedule summary" to chat every morning at 9:00
- Send a "weekly activity report" to stakeholders every Friday
- Notify the accounting person in charge with an "invoice reminder" at the end of each month
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
- English emails from overseas clients → Summarize and report in Japanese
- Mentions of your company on overseas SNS → Translate and share
- Multilingual inquiries → Create reply drafts in each language

---

## Configuration tips

### Minimal configuration (1 Anima)
- Monitor multiple channels with a single instance
- Branch responses using simple rule-based logic
- Escalate everything to a human when uncertain

### Recommended configuration (2–3 Anima)
- **Monitoring and routing role**: Monitors all channels and classifies content
- **Response role**: Executes replies and processing for classified messages
- Dividing roles ensures both monitoring coverage and response quality

### Large-scale configuration
- Assign a dedicated monitoring Anima to each channel
- A coordinating Anima manages the overall flow
- Humans only need to check summaries from the coordinating Anima
