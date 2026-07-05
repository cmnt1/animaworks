from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CI auto-fix runner page template used by the 8787 dashboard."""


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
.job-detail{padding:10px 12px;border-bottom:1px solid #eceee8;font-size:13px;line-height:1.55}
.detail-grid{display:grid;grid-template-columns:110px 1fr;gap:3px 10px;margin-top:8px}
.events{padding:10px 12px;font-family:Consolas,monospace;font-size:12px;white-space:pre-wrap;min-height:320px;max-height:62vh;overflow:auto}
.muted{color:#6b7280}
.pill{display:inline-block;border:1px solid #b9c2b1;border-radius:999px;padding:1px 7px;font-size:12px;background:#f7faf4}
.phase{display:inline-block;border:1px solid #b9c2b1;border-radius:6px;padding:3px 7px;font-weight:700;background:#f7faf4}
.phase-resolved{border-color:#86b88b;background:#ecf8ee;color:#166534}
.phase-ci_waiting,.phase-llm_running,.phase-starting{border-color:#8fb7dc;background:#eef6ff;color:#1d4e89}
.phase-needs_start{border-color:#d2b36d;background:#fff8e6;color:#8a5a00}
.phase-needs_attention,.phase-exhausted{border-color:#df9a9a;background:#fff1f1;color:#991b1b}
.phase-dismissed{border-color:#c4c4c4;background:#f4f4f4;color:#525252}
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
    <div id="jobDetail" class="job-detail muted">Select a job.</div>
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
    <td>${esc(j.id)}</td><td>${renderRunCell(j)}</td>
    <td>${renderStateCell(j)}</td>
    <td>${esc(j.subject||'')}</td><td>${esc(j.updated_at)}</td></tr>`).join('');
  body.querySelectorAll('tr').forEach(row=>row.addEventListener('click',()=>selectJob(row.dataset.id)));
}
function renderRunCell(j){
  const current=j.last_run_id||j.run_id;
  const root=j.root_run_id||j.run_id;
  const url=j.run_url || `https://github.com/${j.repo}/actions/runs/${current}`;
  return `<a href="${esc(url)}" target="_blank">current ${esc(current)}</a><br><span class="muted">root ${esc(root)}</span>${j.last_commit?`<br><span class="muted">commit ${esc(String(j.last_commit).slice(0,12))}</span>`:''}`;
}
function renderStateCell(j){
  const phase=j.phase||'needs_start';
  return `<span class="phase phase-${esc(phase)}">${esc(j.phase_label||j.status)}</span>${j.automation_enabled?' <span class="pill">auto</span>':''}${j.dry_run?' <span class="pill">dry</span>':''}<br><span class="muted">${esc(j.phase_detail||'')}</span><br><span class="muted">status ${esc(j.status)} / attempt ${esc(j.attempt_count||0)}/${esc(j.max_attempts||5)}</span><br><span class="muted">${esc(j.llm_provider||'')} ${esc(j.llm_model||'')}</span>`;
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
  const phaseCounts=s.phase_counts||{};
  const parts=[
    `active ${s.active_count||0}`,
    `waiting ${phaseCounts.ci_waiting||0}`,
    `running ${(phaseCounts.llm_running||0)+(phaseCounts.starting||0)}`,
    `completed ${s.completed_count||0}`,
    `dismissed ${s.dismissed_count||0}`,
    `exhausted ${s.exhausted_count||0}`,
    `total ${s.total_count||0}`
  ];
  let detail='';
  if(latestCompleted){
    detail=`Latest completed: #${esc(latestCompleted.id)} ${esc(latestCompleted.phase_label||latestCompleted.status)} / run ${esc(latestCompleted.last_run_id||latestCompleted.run_id)} / ${esc(latestCompleted.last_commit||'no commit')} / ${esc(latestCompleted.updated_at||'')}`;
  }else if(latest){
    detail=`Latest: #${esc(latest.id)} ${esc(latest.phase_label||latest.status)} / ${esc(latest.phase_detail||'')} / ${esc(latest.updated_at||'')}`;
  }else{
    detail='No CI autofix jobs yet.';
  }
  document.getElementById('summary').innerHTML=`<div>${parts.map(p=>`<span class="pill">${esc(p)}</span>`).join(' ')}</div><div class="muted">${detail}</div>`;
}
function renderJobDetail(j){
  if(!j){document.getElementById('jobDetail').textContent='Select a job.';return;}
  const current=j.last_run_id||j.run_id;
  const root=j.root_run_id||j.run_id;
  const repo=j.repo||'cmnt1/animaworks';
  const currentUrl=j.run_url || `https://github.com/${repo}/actions/runs/${current}`;
  const rootUrl=`https://github.com/${repo}/actions/runs/${root}`;
  document.getElementById('jobDetail').className='job-detail';
  document.getElementById('jobDetail').innerHTML=`
    <div><span class="phase phase-${esc(j.phase||'needs_start')}">${esc(j.phase_label||j.status)}</span> <span class="muted">${esc(j.phase_detail||'')}</span></div>
    <div class="detail-grid">
      <div class="muted">current run</div><div><a href="${esc(currentUrl)}" target="_blank">${esc(current)}</a></div>
      <div class="muted">root run</div><div><a href="${esc(rootUrl)}" target="_blank">${esc(root)}</a></div>
      <div class="muted">commit</div><div>${esc(j.last_commit||'not recorded')}</div>
      <div class="muted">attempt</div><div>${esc(j.attempt_count||0)} / ${esc(j.max_attempts||5)} ${j.automation_enabled?'<span class="pill">auto</span>':''} ${j.dry_run?'<span class="pill">dry</span>':''}</div>
      <div class="muted">LLM</div><div>${esc(j.llm_provider||'')} ${esc(j.llm_model||'')}</div>
      <div class="muted">mail date</div><div>${esc(j.source_date||'not recorded')}</div>
      <div class="muted">updated</div><div>${esc(j.updated_at||'')}</div>
    </div>`;
}
async function selectJob(id){
  selectedJobId=id;renderJobs();
  try{
    const [jobData,d]=await Promise.all([
      api(`/api/ci-autofix/jobs/${id}`),
      api(`/api/ci-autofix/jobs/${id}/events`)
    ]);
    renderJobDetail(jobData.job);
    const lines=(d.events||[]).map(ev=>`${ev.ts} [${ev.level}] ${ev.message} ${JSON.stringify(ev.data)}`);
    document.getElementById('events').textContent=lines.join('\\n')||'No events.';
    document.getElementById('events').className='events';
  }catch(e){document.getElementById('jobDetail').textContent=String(e);document.getElementById('events').textContent=String(e);}
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
loadModels();
loadJobs();
setInterval(()=>pollGmail(null),120000);
setInterval(async()=>{await loadJobs();if(selectedJobId)await selectJob(selectedJobId);},30000);
</script>
</body>
</html>
"""
