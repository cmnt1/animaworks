# Use Case: Software Development Support

This use case automates and supports software development workflows, including code review, PR management, test execution, and bug investigation.

---

## Problems This Can Solve

- PRs pile up and reviews fall behind
- CI failures are noticed too late
- It takes too long from bug report to investigation start
- Tests are often forgotten
- Code quality standards rely on individual knowledge

---

## Pattern 1: Automated Code Review

### What It Does
When a PR is created, it automatically reads the code and comments on issues and improvement suggestions.

### How It Works
1. Detect new PR creation (via webhook or periodic checks)
2. Fetch and analyze the diff
3. Review from the following perspectives:
   - Security issues (SQL injection, hardcoded secrets, etc.)
   - Performance concerns
   - Consistency with existing code
   - Test presence and coverage
4. Post review results as a comment on the PR

### Example Uses
- Automatically run basic quality checks on PRs from junior engineers
- Automatically apply security checklists
- Check compliance with coding standards

### Key Points
- Position this as "supporting" human review, not "replacing" it
- Automated review handles basic issues, letting humans focus on design decisions
- Review criteria are customizable (strict/lenient)

---

## Pattern 2: Monitoring and Response to CI/CD Results

### What It Does
Monitors CI (continuous integration) execution results and provides root cause analysis and fix suggestions when failures occur.

### How It Works
1. Detect CI execution completion
2. If the result is a failure:
   - Fetch and analyze error logs
   - Identify the failure cause (test failure, build error, environment issue, etc.)
   - Create a fix proposal
   - Notify the responsible person
3. If the result is a success:
   - Check merge conditions
   - If all conditions are met, request human approval

### Example Uses
- On test failure, show "These 3 file changes are the cause. Here is the fix proposal."
- Detect environment-dependent failures (flaky tests) and automatically retry
- On CI success, report "Ready to merge. Here is the change summary."

---

## Pattern 3: From Issue Creation to Implementation

### What It Does
Automates the entire flow from bug reports or feature requests: issue creation → branch creation → implementation → PR creation.

### How It Works
1. Create an issue based on human instruction (requirements definition)
2. Automatically create a working branch
3. Implement code based on the instruction
4. Run tests to verify behavior
5. Create a PR and request review

### Example Uses
- "Add validation to the login screen" → Automates issue creation → implementation → PR creation
- "Investigate and fix this bug" → Root cause investigation → fix → tests → PR creation

### Notes
- Fully automated merging is not recommended (human final confirmation is essential)
- Consult a human before starting large design changes
- Always validate implementation results with tests

---

## Pattern 4: Bug Investigation and Root Cause Analysis

### What It Does
Receives bug reports, analyzes logs and code, and identifies root causes while proposing fix strategies.

### How It Works
1. Analyze the bug report (reproduction conditions, impact scope)
2. Search and analyze related code
3. Investigate logs and error traces
4. Form hypotheses about the root cause
5. Report the fix strategy and impact scope

### Example Uses
- "○○ doesn't work in production" → Analyze logs and report the cause and fix strategy
- "Performance has degraded recently" → Analyze recent commits and identify likely causes
- "Tests are unstable" → Analyze flaky test patterns and propose stabilization measures

---

## Pattern 5: Automated Documentation Generation

### What It Does
Automatically generates changelogs and release notes from code changes.

### How It Works
1. Fetch commit history for the specified period
2. Categorize changes (new features, bug fixes, improvements, etc.)
3. Generate user-facing descriptions
4. Create documentation in the required format

### Example Uses
- Automatically generate a changelog before release
- Automatically create monthly development progress reports
- Generate documentation summarizing the impact scope of API changes

---

## Configuration Tips

### Minimal Setup (1 Anima)
- A single Anima handles PR monitoring, review, and CI checks
- Sufficient for small projects (around 10 PRs per month)

### Recommended Setup (3–5 Anima)
- **Development Lead**: Overall progress management, task assignment
- **Implementation**: Issue handling, code implementation
- **Review**: Code review, quality checks
- **Testing**: Test execution, CI monitoring
- The lead receives tasks and assigns them to the appropriate role

### Tips for Maintaining Quality
- Always route automated implementation results through review (Anima review is acceptable)
- Check test diffs (to prevent cases where tests are rewritten just to pass)
- If AI/GAS/ automated tasks may touch personal information, refer to the Personal Information Protection Commission (PPC) official page (https://www.ppc.go.jp/personalinfo/legal/）を確認し、必要なら取り扱い方針（取得・保存・ログ・第三者提供等）をドキュメントに明記する
- Prohibit direct commits to the main branch and enforce merging via PRs
