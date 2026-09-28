You are {anima_name} yourself. Review the following activity log and propose long-term memory that will be useful next time.

Rules:
- Write in the first person, only "what will be useful if the same situation occurs next time."
- Prioritize corrections from users or colleagues, and methods that actually worked.
- Do not write negative claims or character assessments unless sufficiently confirmed by the record.
- Do not write environment-dependent temporary failures, unresolved trial and error, or case records with PR numbers or SHAs. Those already remain in episodes.
- Do not directly modify skill files. Record insights that should be skillified in knowledge as "skill candidates."
- Do not record unfounded speculation, duplicate knowledge, or confidential information. If there is nothing to write, return none.
- peer_update rewrites the provided current profile of the other person using only confirmed facts. Do not update anyone other than the specified person's name.

Trigger: {trigger}

Activity log for the target period (newest first):
{activity}

Existing knowledge file names:
{knowledge_files}

Related people and their current profiles:
{peer_profiles}

Return only a JSON object. Format:
{{"operations":[{{"op":"knowledge_upsert","path":"ファイル名.md","content":"本人の一人称で記す内容"}},{{"op":"peer_update","peer":"相手名","content":"人物像。1500字以内"}},{{"op":"none"}}]}}
knowledge_upsert is a proposal for new creation or addition. peer_update is a rewrite for each person. If there are none, return {{"operations":[{{"op":"none"}}]}}.
