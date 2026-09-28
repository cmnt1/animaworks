The following is a cluster of similar behavioral patterns extracted from a 7-day activity log.
Each cluster contains similar behaviors that were repeated three or more times.

Identify the recurring patterns and distill them into reusable procedure documents.

【Behavior Patterns】
{clusters_text}

【Existing Procedures】
{existing_procedures}

Output format (JSON array):
[
  {{
    "title": "Procedure name (for English filename)",
    "description": "Overview of the procedure (1-2 sentences)",
    "tags": ["tag1", "tag2"],
    "content": "# Procedure name\\n\\n## Overview\\n...\\n\\n## Steps\\n1. ...\\n2. ...\\n\\n## Notes\\n..."
  }}
]

Rules:
- If there are no recurring patterns, return an empty array []
- Skip if it overlaps with existing procedures
- Include concrete procedure steps
- Returning an empty array [] is acceptable
