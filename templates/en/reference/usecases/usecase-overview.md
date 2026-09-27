# AnimaWorks Use Case Guide

This guide organizes what you can do with AnimaWorks by theme.
It is structured to help first-time AnimaWorks users easily imagine how it can be applied to their own work.

---

## What is AnimaWorks

AnimaWorks is a framework that organizes AI agents (Anima) as "employees" and keeps them running 24 hours a day, 365 days a year.

Even while humans are asleep, Anima can:
- Monitor messages and respond as needed
- Detect and report server or service anomalies
- Generate periodic reports
- Execute code reviews and tests

These tasks are handled autonomously.

---

## Features of Anima

### 1. Memory
Anima has short-term memory and long-term memory. It accumulates past response history, lessons learned, and established procedures, improving response quality with each iteration. The experience of "this is how we solved this problem last time" is accumulated within the organization.

### 2. Roles
Each Anima is assigned a specialized role. By giving them areas of expertise—such as secretary, engineer, monitoring specialist, or customer support—you can build a division of labor just like in a human organization.

### 3. Collaboration as an Organization
Anima exchange messages with each other and delegate tasks. A hierarchical organizational structure is possible, where a supervisor coordinates the overall picture and specialized staff handle the actual work.

### 4. Regular Autonomous Actions
You can configure scheduled execution, such as "generate a report every morning at 9 AM" or "check messages every 30 minutes." Even without human instruction, Anima continues to execute the defined routines.

### 5. Integration with External Services
Anima can connect to various external services, including chat tools, email, calendars, cloud services, and social media. As long as a service has a public API, Anima can operate it directly.

---

## Use Case List

The following theme-based guides introduce specific usage patterns.

| Guide | Theme | Who It's For |
|--------|--------|-------------|
| [Communication Automation](usecase-communication.md) | Automating chat and email responses | People with many external contacts who worry about missed responses |
| [Software Development Support](usecase-development.md) | Code review, PR management, bug investigation | People with development teams, solo developers |
| [Infrastructure and Service Monitoring](usecase-monitoring.md) | 24/7 monitoring, alerts, incident response | People operating servers or web services |
| [Secretary and Administrative Support](usecase-secretary.md) | Schedule management, coordination, reminders | Busy people who can't keep up with administrative work |
| [Research and Investigation](usecase-research.md) | Web research, market analysis, report creation | People who regularly gather and analyze information |
| [Knowledge Management](usecase-knowledge.md) | Procedure documentation, FAQs, structured information | People who want to systematize their team's knowledge |
| [Customer Support](usecase-customer-support.md) | Inquiry handling, escalation | People with customer-facing responsibilities |

---

## Getting Started

You don't need to "do everything at once." We recommend starting with one or two Anima and gradually increasing as you become more comfortable.

### Examples of a Small Start

**Pattern 1: Start with just one**
- Deploy one secretary Anima
- Assign only message monitoring and reminders
- Expand the scope of responsibilities once you're comfortable

**Pattern 2: Division of labor with two**
- Secretary Anima (communication and schedule management)
- Monitoring Anima (checking server and service status)
- Even with just these two, you get peace of mind with 24-hour coverage

**Pattern 3: Team structure**
- Supervisor Anima (overall coordination and decision-making)
- Several operational Anima (development, monitoring, secretarial, etc.)
- Humans only interact with the supervisor Anima, and the supervisor delegates the actual work to its subordinates

---

## Notes

### Situations Requiring Human Judgment
Anima operates autonomously, but it will seek human judgment in the following situations:
- Decisions involving money
- Important external communications (contracts, negotiations, etc.)
- Irreversible operations (data deletion, production deployment, etc.)
- New situations where the criteria for judgment are unclear

### Cost Awareness
Each Anima operates using LLM (large language model) APIs, so costs are incurred based on the volume of activity. It's important to run them only as needed and at the necessary frequency.

### Security
- Clearly define rules for handling confidential information
- Centrally manage authentication credentials for external services
- Set Anima permissions to the minimum required (only allow access to necessary tools)