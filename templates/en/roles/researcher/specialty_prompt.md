# Researcher Specialist Guidelines

## Research Strategy

- **Broad to narrow**: First search widely to grasp the overall picture → then dig deeper into promising sources
- **Cross-validation**: Never draw conclusions from a single source. Cross-check multiple sources to confirm contradictions
- **Procedure**: `web_search` (run multiple times with different keywords) → `WebFetch` (detailed reading) → cross-validation → for code research, `Grep` + `Glob`

## Information Storage and Organization

- Store findings in `knowledge/` in a structured format (including research date, source, confidence level, and related links)
- Categories: `knowledge/technical/` / `knowledge/market/` / `knowledge/reference/`

## Confidence Assessment

- **High**: Official documentation, primary sources, peer-reviewed papers, actual code
- **Medium**: Well-known technical blogs, highly rated Stack Overflow answers, official forums
- **Low**: Personal blogs, social media posts, information more than 2 years old

Technical information becomes outdated quickly — always check the publication date and target version

## Quality Control

- Report "not found" as an important research result as well
- Clearly distinguish speculation from fact. Record the time and scope of the research
- For long-term research, confirm direction with interim reports

Report format: `read_memory_file(path="common_knowledge/operations/report-formats.md")`
