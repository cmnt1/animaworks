# Cron: Development Lead (PdM)

## Morning Stand-up
schedule: 0 9 * * *
type: llm
Check the team's status and decide today's task allocation.
- Review newly arrived issues and tasks
- Understand each member's current work status
- Assign tasks based on priority and members' areas of expertise
- Record the situation in state/daily_plan.md

## All PR Review
schedule: */15 * * * *
type: llm
Review all open PRs and determine what is currently missing to reach merge.
- Check each PR's CI status, review status, and whether there are conflicts
- If a PR is stalled, re-delegate or escalate it to the person in charge
- Only PRs that meet the quality gates (review complete and CI green) are merge candidates

## Weekly Progress Review
schedule: 0 17 * * 5
type: llm
Reflect on this week's development results and extract lessons learned.
- Evaluate the quality of completed tasks and record improvement points for the team
- Detect technical debt and recurring issues, and plan countermeasures
- Integrate the results into knowledge/ and send a weekly report to the supervisor
