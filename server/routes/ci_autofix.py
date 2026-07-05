from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CI auto-fix intake API and runner page."""

import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from core.paths import get_data_dir
from swe.ci_autofix_intake import CIAutofixIntakeStore, IntakeRule, poll_gmail_for_candidates, utc_now


def default_store_path() -> Path:
    return get_data_dir() / "run" / "ci_autofix_intake.sqlite3"


def default_store() -> CIAutofixIntakeStore:
    return CIAutofixIntakeStore(default_store_path())


class PollGmailRequest(BaseModel):
    repo: str = Field(default="cmnt1/animaworks", pattern=r"^[^/\s]+/[^/\s]+$")
    branch: str = "main"
    actor: str = "cmnt1"
    query: str = ""
    max_results: int = Field(default=20, ge=1, le=100)
    dry_run: bool = True
    llm_provider: str = "claude_code"
    llm_model: str = ""


class CandidateRequest(BaseModel):
    run_id: str = Field(pattern=r"^\d+$")
    repo: str = Field(default="cmnt1/animaworks", pattern=r"^[^/\s]+/[^/\s]+$")
    branch: str = "main"
    actor: str = "cmnt1"
    run_url: str = ""
    dry_run: bool = True
    llm_provider: str = "claude_code"
    llm_model: str = ""


class AutoStartRequest(BaseModel):
    max_attempts: int = Field(default=5, ge=1, le=20)
    dry_run: bool = False


def _agent_script_path() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "ci_autofix_agent_attempt.py"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _start_agent(store: CIAutofixIntakeStore, job_id: int, store_path: Path) -> dict[str, object]:
    job = store.get_job(job_id)
    if job.status == "running":
        return {"ok": True, "already_running": True, "job": job.to_dict()}
    if job.attempt_count >= job.max_attempts:
        job = store.update_job_state(
            job.id,
            status="exhausted",
            terminal_reason=f"attempt limit reached ({job.attempt_count}/{job.max_attempts})",
        )
        return {"ok": False, "error": "attempt limit reached", "job": job.to_dict()}
    job = store.update_job_state(job.id, status="queued", automation_enabled=True)
    log_dir = store_path.parent / "ci_autofix_runs" / "launcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    out_path = log_dir / f"job_{job.id}_{stamp}.out.log"
    err_path = log_dir / f"job_{job.id}_{stamp}.err.log"
    cmd = [
        sys.executable,
        str(_agent_script_path()),
        "--db",
        str(store_path),
        "--job-id",
        str(job.id),
        "--repo-root",
        str(_repo_root()),
    ]
    out = out_path.open("w", encoding="utf-8", errors="replace")
    err = err_path.open("w", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(_repo_root()),
            stdout=out,
            stderr=err,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        out.close()
        err.close()
    store.add_event(
        job.id,
        "info",
        "auto-fix agent launched",
        {"pid": proc.pid, "launcher_stdout": str(out_path), "launcher_stderr": str(err_path)},
    )
    return {"ok": True, "pid": proc.pid, "job": job.to_dict()}


def _gh_run_view(repo: str, run_id: str) -> dict[str, object]:
    result = subprocess.run(
        [
            "gh",
            "run",
            "view",
            str(run_id),
            "--repo",
            repo,
            "--json",
            "status,conclusion,url,headSha,headBranch,workflowName,createdAt,updatedAt",
        ],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "gh run view failed").strip())
    data = json.loads(result.stdout)
    return data if isinstance(data, dict) else {}


def _gh_latest_run_for_commit(repo: str, commit: str) -> dict[str, object] | None:
    if not commit:
        return None
    result = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--commit",
            commit,
            "--json",
            "databaseId,status,conclusion,url,headSha,headBranch,workflowName,createdAt,updatedAt,displayTitle",
            "--limit",
            "5",
        ],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    return first if isinstance(first, dict) else None


def create_ci_autofix_api_router(
    store_factory: Callable[[], CIAutofixIntakeStore] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/ci-autofix", tags=["ci-autofix"])
    get_store = store_factory or default_store

    @router.get("/rules/default")
    async def default_rule():
        return {"ok": True, "rule": IntakeRule().to_dict()}

    @router.get("/jobs")
    async def list_jobs(limit: int = 50, include_terminal: bool = False):
        store = get_store()
        return {
            "ok": True,
            "jobs": [job.to_dict() for job in store.list_jobs(limit=limit, include_terminal=include_terminal)],
        }

    @router.get("/summary")
    async def summary():
        return {"ok": True, **get_store().summary()}

    @router.post("/jobs/candidate")
    async def create_candidate(body: CandidateRequest):
        store = get_store()
        job, created = store.upsert_candidate(
            run_id=body.run_id,
            repo=body.repo,
            branch=body.branch,
            actor=body.actor,
            run_url=body.run_url or f"https://github.com/{body.repo}/actions/runs/{body.run_id}",
            dry_run=body.dry_run,
            llm_provider=body.llm_provider,
            llm_model=body.llm_model,
        )
        store.add_event(job.id, "info", "manual candidate registered", {"created": created})
        return {"ok": True, "created": created, "job": job.to_dict()}

    @router.post("/jobs/{job_id}/auto-start")
    async def auto_start(job_id: int, body: AutoStartRequest):
        store = get_store()
        try:
            job = store.update_job_state(
                job_id,
                max_attempts=body.max_attempts,
                dry_run=body.dry_run,
                automation_enabled=True,
            )
        except KeyError as exc:
            raise HTTPException(404, "CI auto-fix job not found") from exc
        return _start_agent(store, job.id, default_store_path())

    @router.post("/jobs/{job_id}/check-run")
    async def check_run(job_id: int):
        store = get_store()
        try:
            job = store.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(404, "CI auto-fix job not found") from exc
        try:
            run = _gh_latest_run_for_commit(job.repo, job.last_commit) or _gh_run_view(job.repo, job.last_run_id)
        except Exception as exc:
            store.add_event(
                job.id, "error", "failed to inspect GitHub Actions run", {"run_id": job.last_run_id, "error": str(exc)}
            )
            raise HTTPException(502, str(exc)) from exc
        status = str(run.get("status") or "")
        conclusion = str(run.get("conclusion") or "")
        inspected_run_id = str(run.get("databaseId") or job.last_run_id)
        inspected_url = str(run.get("url") or job.run_url)
        store.add_event(
            job.id,
            "info",
            "GitHub Actions run inspected",
            {"run_id": inspected_run_id, "status": status, "conclusion": conclusion, "url": inspected_url},
        )
        if status != "completed":
            return {
                "ok": True,
                "run": run,
                "job": store.update_job_state(
                    job.id,
                    status="waiting_ci",
                    last_run_id=inspected_run_id,
                    run_url=inspected_url,
                    last_conclusion=conclusion,
                    next_poll_at=utc_now(),
                ).to_dict(),
                "started": None,
            }
        if conclusion == "success":
            updated = store.update_job_state(
                job.id,
                status="completed",
                automation_enabled=False,
                last_run_id=inspected_run_id,
                run_url=inspected_url,
                last_conclusion=conclusion,
                terminal_reason="CI passed",
            )
            store.add_event(job.id, "info", "CI passed; auto-fix job completed", {"run_id": inspected_run_id})
            return {"ok": True, "run": run, "job": updated.to_dict(), "started": None}
        terminal = job.attempt_count >= job.max_attempts
        updated = store.update_job_state(
            job.id,
            status="exhausted" if terminal else "ci_failed",
            last_conclusion=conclusion or "failure",
            terminal_reason=f"CI conclusion: {conclusion or 'unknown'}" if terminal else "",
        )
        started = None
        if updated.automation_enabled and not terminal:
            started = _start_agent(store, updated.id, default_store_path())
        return {"ok": True, "run": run, "job": store.get_job(job.id).to_dict(), "started": started}

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: int):
        store = get_store()
        try:
            job = store.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(404, "CI auto-fix job not found") from exc
        return {"ok": True, "job": job.to_dict()}

    @router.get("/jobs/{job_id}/events")
    async def list_events(job_id: int, limit: int = 200):
        store = get_store()
        try:
            store.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(404, "CI auto-fix job not found") from exc
        return {"ok": True, "events": [event.to_dict() for event in store.list_events(job_id, limit=limit)]}

    @router.post("/poll-gmail")
    async def poll_gmail(body: PollGmailRequest):
        rule = IntakeRule(
            repo=body.repo,
            branch=body.branch,
            actor=body.actor,
            query=body.query,
            max_results=body.max_results,
            dry_run=body.dry_run,
            llm_provider=body.llm_provider,
            llm_model=body.llm_model,
        )
        return poll_gmail_for_candidates(store=get_store(), rule=rule)

    return router


def create_ci_autofix_page_router() -> APIRouter:
    router = APIRouter()

    @router.get("/runner/ci-autofix", include_in_schema=False)
    async def ci_autofix_page():
        return HTMLResponse(_PAGE_HTML, headers={"Cache-Control": "no-store"})

    return router


_PAGE_HTML = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>CI Autofix Intake</title>
<style>
body{font-family:Segoe UI,sans-serif;background:#f7f7f4;color:#1f2933;margin:0;padding:18px}
h3{margin:0 0 12px;font-size:18px}
button{padding:7px 11px;border:1px solid #a7b0a2;background:#fff;color:#1f2933;border-radius:6px;cursor:pointer}
button:hover{background:#eef2ea}
input,select{box-sizing:border-box;padding:7px 8px;border:1px solid #a7b0a2;border-radius:6px;background:#fff;color:#1f2933}
.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.inline-check{display:inline-flex;align-items:center;gap:5px;font-size:13px;color:#52605a}
.inline-check input{width:auto}
.layout{display:grid;grid-template-columns:minmax(420px,1fr) minmax(360px,.8fr);gap:14px}
.settings{display:grid;grid-template-columns:minmax(160px,.4fr) minmax(260px,1fr);gap:10px;margin:0 0 12px}
.settings label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:#52605a}
.panel{border:1px solid #c9cec4;background:#fff;border-radius:8px;overflow:hidden}
.panel h4{margin:0;padding:10px 12px;background:#e9ede4;border-bottom:1px solid #c9cec4;font-size:14px}
table{width:100%;border-collapse:collapse}
th,td{border-bottom:1px solid #eceee8;padding:8px;text-align:left;vertical-align:top;font-size:13px}
th{background:#fafaf8;color:#52605a}
tr{cursor:pointer}
tr:hover{background:#f2f5ef}
tr.selected{background:#e7f0de}
.status{margin:8px 0;color:#52605a;white-space:pre-wrap;font-size:13px}
.summary{margin:0 0 12px;padding:8px 10px;border:1px solid #d8ded2;background:#fcfcfa;border-radius:8px;color:#374151;font-size:13px;line-height:1.45}
.events{padding:10px 12px;font-family:Consolas,monospace;font-size:12px;white-space:pre-wrap;min-height:320px;max-height:62vh;overflow:auto}
.muted{color:#6b7280}
.pill{display:inline-block;border:1px solid #b9c2b1;border-radius:999px;padding:1px 7px;font-size:12px;background:#f7faf4}
@media(max-width:900px){.layout{grid-template-columns:1fr}}
@media(max-width:700px){.settings{grid-template-columns:1fr}}
</style>
</head>
<body>
<h3>CI Autofix Intake</h3>
<div class="toolbar">
  <button onclick="window.close()">Close</button>
  <button onclick="loadJobs()">Reload</button>
  <button onclick="pollGmail(this)">Poll Gmail</button>
  <input id="runId" placeholder="run id" style="width:180px">
  <button onclick="addCandidate()">Add</button>
  <button onclick="startAuto()">Start Auto</button>
  <button onclick="checkRun()">Check Run</button>
  <label class="inline-check"><input id="showHistory" type="checkbox" onchange="loadJobs()">完了履歴</label>
</div>
<div id="status" class="status">loading...</div>
<div id="summary" class="summary muted">Summary loading...</div>
<div class="settings">
  <label>Provider<select id="llmProvider"></select></label>
  <label>Model<select id="llmModel"></select></label>
</div>
<div class="layout">
  <section class="panel">
    <h4>Jobs</h4>
    <table>
      <thead><tr><th>ID</th><th>Run</th><th>Status</th><th>Subject</th><th>Updated</th></tr></thead>
      <tbody id="jobsBody"></tbody>
    </table>
  </section>
  <section class="panel">
    <h4>Events</h4>
    <div id="events" class="events muted">Select a job.</div>
  </section>
</div>
<script>
let jobs=[];
let selectedJobId=null;
let modelsByProvider={};
const FALLBACK_MODELS=[
  {id:'claude-sonnet-4-6',provider:'Anthropic',credential:'anthropic',label:'S: Anthropic/claude-sonnet-4-6'},
  {id:'codex/gpt-5.5',provider:'OpenAI',credential:'codex',label:'C: OpenAI/gpt-5.5'},
  {id:'google/gemini-2.5-pro',provider:'Google',credential:'google',label:'A: Google/gemini-2.5-pro'},
  {id:'nanogpt/deepseek-v4-flash',provider:'nanoGPT',credential:'nanogpt',label:'A: nanoGPT/deepseek-v4-flash'}
];
function esc(v){return String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
function setStatus(text,bad=false){const el=document.getElementById('status');el.textContent=text;el.style.color=bad?'#991b1b':'#52605a';}
async function api(path,opts){const r=await fetch(path,Object.assign({cache:'no-store'},opts||{}));const d=await r.json();if(!r.ok||d.ok===false)throw new Error(d.detail||d.error||JSON.stringify(d));return d;}
function providerKey(m){return m.credential || String(m.provider||'custom').toLowerCase();}
function providerLabel(key, items){return items?.[0]?.provider || key;}
function selectedLlm(){
  return {
    llm_provider: document.getElementById('llmProvider')?.value || 'anthropic',
    llm_model: document.getElementById('llmModel')?.value || ''
  };
}
function renderModelSelectors(models){
  modelsByProvider={};
  for(const m of models){
    const key=providerKey(m);
    (modelsByProvider[key] ||= []).push(m);
  }
  const provider=document.getElementById('llmProvider');
  const model=document.getElementById('llmModel');
  const savedProvider=localStorage.getItem('ciAutofix.llmProvider') || 'anthropic';
  const savedModel=localStorage.getItem('ciAutofix.llmModel') || '';
  const keys=Object.keys(modelsByProvider);
  provider.innerHTML=keys.map(k=>`<option value="${esc(k)}">${esc(providerLabel(k,modelsByProvider[k]))}</option>`).join('');
  provider.value=keys.includes(savedProvider)?savedProvider:keys[0];
  function fillModels(){
    const rows=modelsByProvider[provider.value]||[];
    model.innerHTML=rows.map(m=>`<option value="${esc(m.id)}">${esc(m.label||m.id)}</option>`).join('');
    model.value=rows.some(m=>m.id===savedModel)?savedModel:(rows[0]?.id||'');
    localStorage.setItem('ciAutofix.llmProvider',provider.value);
    localStorage.setItem('ciAutofix.llmModel',model.value);
  }
  provider.addEventListener('change',fillModels);
  model.addEventListener('change',()=>localStorage.setItem('ciAutofix.llmModel',model.value));
  fillModels();
}
async function loadModels(){
  try{const d=await api('/api/system/available-models');renderModelSelectors((d.models&&d.models.length)?d.models:FALLBACK_MODELS);}
  catch{renderModelSelectors(FALLBACK_MODELS);}
}
function renderJobs(){
  const body=document.getElementById('jobsBody');
  body.innerHTML=jobs.map(j=>`<tr data-id="${esc(j.id)}" class="${String(j.id)===String(selectedJobId)?'selected':''}">
    <td>${esc(j.id)}</td><td><a href="${esc(j.run_url)}" target="_blank">${esc(j.last_run_id||j.run_id)}</a><br><span class="muted">root ${esc(j.root_run_id||j.run_id)}</span></td>
    <td><span class="pill">${esc(j.status)}</span>${j.automation_enabled?' <span class="pill">auto</span>':''}${j.dry_run?' <span class="pill">dry</span>':''}<br><span class="muted">attempt ${esc(j.attempt_count||0)}/${esc(j.max_attempts||5)}</span><br><span class="muted">${esc(j.llm_provider||'')} ${esc(j.llm_model||'')}</span></td>
    <td>${esc(j.subject||'')}</td><td>${esc(j.updated_at)}</td></tr>`).join('');
  body.querySelectorAll('tr').forEach(row=>row.addEventListener('click',()=>selectJob(row.dataset.id)));
}
async function loadJobs(){
  try{
    const includeTerminal=document.getElementById('showHistory')?.checked;
    const [d,s]=await Promise.all([
      api(`/api/ci-autofix/jobs?include_terminal=${includeTerminal?'true':'false'}`),
      api('/api/ci-autofix/summary')
    ]);
    jobs=d.jobs||[];
    renderJobs();
    renderSummary(s);
    setStatus(`jobs: ${jobs.length}${includeTerminal?' (history included)':''}`);
  }
  catch(e){setStatus(String(e),true);}
}
function renderSummary(s){
  const latestCompleted=s.latest_completed;
  const latest=s.latest;
  const parts=[
    `active ${s.active_count||0}`,
    `completed ${s.completed_count||0}`,
    `dismissed ${s.dismissed_count||0}`,
    `exhausted ${s.exhausted_count||0}`,
    `total ${s.total_count||0}`
  ];
  let detail='';
  if(latestCompleted){
    detail=`Latest completed: #${esc(latestCompleted.id)} run ${esc(latestCompleted.last_run_id||latestCompleted.run_id)} / ${esc(latestCompleted.last_commit||'no commit')} / ${esc(latestCompleted.updated_at||'')}`;
  }else if(latest){
    detail=`Latest: #${esc(latest.id)} ${esc(latest.status)} run ${esc(latest.last_run_id||latest.run_id)} / ${esc(latest.updated_at||'')}`;
  }else{
    detail='No CI autofix jobs yet.';
  }
  document.getElementById('summary').innerHTML=`<div>${parts.map(p=>`<span class="pill">${esc(p)}</span>`).join(' ')}</div><div class="muted">${detail}</div>`;
}
async function selectJob(id){
  selectedJobId=id;renderJobs();
  try{
    const d=await api(`/api/ci-autofix/jobs/${id}/events`);
    const lines=(d.events||[]).map(ev=>`${ev.ts} [${ev.level}] ${ev.message} ${JSON.stringify(ev.data)}`);
    document.getElementById('events').textContent=lines.join('\\n')||'No events.';
    document.getElementById('events').className='events';
  }catch(e){document.getElementById('events').textContent=String(e);}
}
async function pollGmail(btn){
  const original=btn?.textContent || '';
  if(btn){btn.disabled=true;btn.textContent='Polling...';}
  setStatus('polling Gmail...');
  try{const d=await api('/api/ci-autofix/poll-gmail',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selectedLlm())});setStatus(`checked ${d.checked}; created ${d.created.length}; linked ${(d.linked||[]).length}; existing ${d.existing.length}; stale ${(d.stale||[]).length}; auto ${(d.auto_started||[]).length}`);await loadJobs();}
  catch(e){setStatus(String(e),true);}
  finally{if(btn){btn.disabled=false;btn.textContent=original;}}
}
async function addCandidate(){
  const runId=document.getElementById('runId').value.trim();if(!runId)return;
  try{const d=await api('/api/ci-autofix/jobs/candidate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:runId,...selectedLlm()})});selectedJobId=d.job.id;await loadJobs();await selectJob(selectedJobId);}
  catch(e){setStatus(String(e),true);}
}
async function startAuto(){
  if(!selectedJobId){setStatus('Select a job first.',true);return;}
  try{const d=await api(`/api/ci-autofix/jobs/${selectedJobId}/auto-start`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({max_attempts:5,dry_run:false})});setStatus(d.already_running?'auto already running':`auto launched pid ${d.pid||'-'}`);await loadJobs();await selectJob(selectedJobId);}
  catch(e){setStatus(String(e),true);}
}
async function checkRun(){
  if(!selectedJobId){setStatus('Select a job first.',true);return;}
  try{const d=await api(`/api/ci-autofix/jobs/${selectedJobId}/check-run`,{method:'POST'});setStatus(`run ${d.run?.status||'-'} / ${d.run?.conclusion||'-'}${d.started?' / next attempt started':''}`);await loadJobs();await selectJob(selectedJobId);}
  catch(e){setStatus(String(e),true);}
}
loadModels();
loadJobs();
setInterval(()=>pollGmail(null),120000);
setInterval(loadJobs,30000);
</script>
</body>
</html>
"""
