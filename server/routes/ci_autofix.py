from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CI auto-fix intake API and runner page."""

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from core.paths import get_data_dir
from swe.ci_autofix_intake import CIAutofixIntakeStore, IntakeRule, poll_gmail_for_candidates


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


def create_ci_autofix_api_router(
    store_factory: Callable[[], CIAutofixIntakeStore] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/ci-autofix", tags=["ci-autofix"])
    get_store = store_factory or default_store

    @router.get("/rules/default")
    async def default_rule():
        return {"ok": True, "rule": IntakeRule().to_dict()}

    @router.get("/jobs")
    async def list_jobs(limit: int = 50):
        store = get_store()
        return {"ok": True, "jobs": [job.to_dict() for job in store.list_jobs(limit=limit)]}

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
</div>
<div id="status" class="status">loading...</div>
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
    <td>${esc(j.id)}</td><td><a href="${esc(j.run_url)}" target="_blank">${esc(j.run_id)}</a></td>
    <td><span class="pill">${esc(j.status)}</span>${j.dry_run?' <span class="pill">dry</span>':''}<br><span class="muted">${esc(j.llm_provider||'')} ${esc(j.llm_model||'')}</span></td>
    <td>${esc(j.subject||'')}</td><td>${esc(j.updated_at)}</td></tr>`).join('');
  body.querySelectorAll('tr').forEach(row=>row.addEventListener('click',()=>selectJob(row.dataset.id)));
}
async function loadJobs(){
  try{const d=await api('/api/ci-autofix/jobs');jobs=d.jobs||[];renderJobs();setStatus(`jobs: ${jobs.length}`);}
  catch(e){setStatus(String(e),true);}
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
  const original=btn.textContent;btn.disabled=true;btn.textContent='Polling...';setStatus('polling Gmail...');
  try{const d=await api('/api/ci-autofix/poll-gmail',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selectedLlm())});setStatus(`checked ${d.checked}; created ${d.created.length}; existing ${d.existing.length}`);await loadJobs();}
  catch(e){setStatus(String(e),true);}
  finally{btn.disabled=false;btn.textContent=original;}
}
async function addCandidate(){
  const runId=document.getElementById('runId').value.trim();if(!runId)return;
  try{const d=await api('/api/ci-autofix/jobs/candidate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:runId,...selectedLlm()})});selectedJobId=d.job.id;await loadJobs();await selectJob(selectedJobId);}
  catch(e){setStatus(String(e),true);}
}
loadModels();
loadJobs();
</script>
</body>
</html>
"""
