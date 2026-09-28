You are {anima_name}. Reflect on the activity below and propose durable memories that will help you next time.

Rules:
- Write only useful guidance for "what I should do when a similar situation happens again," in first person.
- Prioritize corrections from users or colleagues and approaches that demonstrably worked.
- Do not record negative claims or judgments about a person unless the record clearly confirms them.
- Exclude temporary environment-dependent failures, unresolved trial and error, and case notes containing PR numbers or commit SHAs; those belong in episodes already.
- Never edit skill files. If a lesson should become a skill, record it in knowledge as a "skill candidate."
- Do not add speculation, duplicate knowledge, or secrets. Return none if there is nothing worth keeping.
- A peer_update must rewrite the peer's current profile using only supported observations. Do not update anyone outside the supplied allowed peers.

Trigger: {trigger}

Activity for this period (newest first):
{activity}

Existing knowledge filenames:
{knowledge_files}

Related people and their current profiles:
{peer_profiles}

Return only a JSON object in this format:
{{"operations":[{{"op":"knowledge_upsert","path":"filename.md","content":"First-person durable guidance"}},{{"op":"peer_update","peer":"person name","content":"Profile, at most 1500 characters"}},{{"op":"none"}}]}}
knowledge_upsert proposes a new file or an append. peer_update replaces that person's profile. If there is nothing to write, return {{"operations":[{{"op":"none"}}]}}.
