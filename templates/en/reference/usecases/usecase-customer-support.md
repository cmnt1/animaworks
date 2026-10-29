# Use case: Customer support

This use case automates handling of customer inquiries, escalation management, and maintaining response quality.

---

## Problems this can solve

- Slow initial responses to inquiries
- Missed responses
- Repeatedly answering the same questions
- Inability to handle inquiries outside business hours
- Unorganized response history

---

## Pattern 1: Automating first-line response

### What to do
When an inquiry is received from a customer, automatically send an initial acknowledgment and classify the inquiry.

### How it works
1. Monitor inquiry channels (email, chat, forms, etc.)
2. Detect new inquiries
3. Immediately send an acknowledgment message ("Thank you for your inquiry. We will review and get back to you.")
4. Classify the inquiry:
   - Technical questions
   - Billing and contract questions
   - Bug reports
   - Requests and feedback
   - Other
5. Route to the appropriate response flow based on classification

### Examples
- Inquiry via form → send acknowledgment email within 30 seconds
- "Can't log in" → provide FAQ password reset procedure
- "Invoice not received" → escalate to accounting

---

### Notes
- Expand the scope of automated responses gradually
- Start with "acknowledgment + FAQ guidance" to be safe
- Always route sensitive content (complaints, legal issues) to a human

---

## Pattern 2: FAQ-based automated responses

### What to do
Search past response history and the FAQ database for similar questions and present answers.

### How it works
1. Analyze the inquiry content
2. Search the FAQ database for similar questions
3. If a highly matching answer is found:
   - Draft a response
   - High confidence → send automatically (no human review)
   - Medium confidence → present the draft to a human (send after approval)
   - Low confidence → escalate to a human
4. Log the response result

### Examples
- "Please tell me about pricing plans" → automatically respond with the pricing table from the FAQ
- "Do you have feature X?" → present the relevant answer from the feature list
- "How do I cancel?" → provide the cancellation procedure (but let a human decide on retention offers)

---

## Pattern 3: Escalation management

### What to do
Escalate inquiries that cannot be resolved through automated responses to the appropriate person and track the status.

### How it works
1. Determine that the inquiry is outside the scope of automated response
2. Decide the escalation destination based on content:
   - Technical issues → development team
   - Contracts and billing → sales/accounting team
   - Complaints → manager/human
3. Attach a summary and background when escalating
4. Set a response deadline and track progress
5. Send a reminder if no response within a certain time

### Examples
- "Reporting a bug" → send to development team: "Bug report for X. Reproduction conditions: X. Priority: medium"
- 2 hours after escalation → send reminder "This inquiry has not been addressed"
- After completion → send the answer to the customer

---

## Pattern 4: Managing and analyzing response history

### What to do
Record all inquiries and responses, and use them for trend analysis and service improvement.

### How it works
1. Accumulate records of all inquiries:
   - Receipt date/time, content, classification
   - Response content, responder
   - Time to resolution
   - Customer satisfaction (when available)
2. Analyze trends regularly:
   - Top 10 most frequent questions
   - Average response time trends
   - Number of unresolved cases
3. Report the analysis results

### Examples
- "50 inquiries this month. The most common was about X (15 inquiries)"
- "Average first response time: 5 minutes (last month: 30 minutes)"
- "Bug reports about feature X are increasing. Recommend sharing with the development team"

---

## Pattern 5: Proactive support

### What to do
Instead of waiting for customer inquiries, detect and address issues in advance.

### How it works
1. Monitor service status
2. Detect issues affecting customers:
   - Service outages
   - Scheduled maintenance
   - Pricing plan changes
3. Notify affected customers in advance

### Examples
- Service outage → identify affected scope → notify affected customers: "An outage is currently occurring on X. Please wait until service is restored."
- Planned maintenance → notify in advance: "Maintenance will be performed on [date] from [time] to [time]."
- Customers with upcoming contract renewal → "Your contract renewal date is approaching. For renewal procedures, see here."

---

## Configuration tips

### Minimal configuration (1 Anima)
- One agent handles all support tasks
- Acknowledgment + FAQ auto-response + escalation
- Sufficient for up to 50 inquiries per month

### Recommended configuration (2–3 Anima)
- **Frontline agent**: Receives, classifies, and answers FAQs
- **Escalation agent**: Routes to humans and tracks progress
- **Analytics agent**: Analyzes response history and generates reports

### Tips for quality improvement
- Start automated responses with "draft → human review → send"
- Set the tone for customer communication (level of politeness) in advance
- Build out response templates (greetings, apologies, thanks, closing, etc.)
- Have humans regularly sample-check the accuracy of automated responses
- Add new FAQ items as soon as you notice they are needed
