const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

async function api(path, opts={}){
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if(!res.ok){
    const detail = await res.json().catch(()=>({detail: res.statusText}));
    throw new Error(detail.detail || res.statusText);
  }
  return res.json();
}

function setNote(el, msg, ok=true){
  el.textContent = msg;
  el.style.color = ok ? '#a5f3d0' : '#ffd0d8';
}

function activateTab(tab){
  $$('.tab').forEach(t=>t.classList.remove('active'));
  $$('.panel').forEach(p=>p.classList.remove('show'));
  tab.classList.add('active');
  $(`#panel-${tab.dataset.tab}`).classList.add('show');
}

async function loadEvents(){
  const list = $('#event-list');
  list.innerHTML = 'Loading...';
  try{
    const events = await api('/events');
    if(events.length===0){ list.innerHTML = '<div class="meta">No events yet.</div>'; return; }
    list.innerHTML = '';
    for(const e of events){
      const item = document.createElement('div');
      item.className = 'item';
      const chipCls = e.is_valid ? 'valid' : 'invalid';
      const conflicts = e.violations && e.violations.length ? ` • Conflicts: ${e.violations.join(', ')}` : '';
      item.innerHTML = `
        <div>
          <div><strong>${e.title}</strong> <span class="meta">(${e.event_id})</span></div>
          <div class="meta">${e.date} • ${e.start_time}–${e.end_time} • ${e.venue}${conflicts}</div>
        </div>
        <div class="chip ${chipCls}">${e.is_valid? 'Valid' : 'Invalid'}</div>
      `;
      list.appendChild(item);
    }
  }catch(err){
    list.innerHTML = `<div class="meta">Error: ${err.message}</div>`;
  }
}

async function loadConflicts(){
  const list = $('#conflict-list');
  list.innerHTML = 'Loading...';
  try{
    const conflicts = await api('/conflicts');
    if(conflicts.length===0){ list.innerHTML = '<div class="meta">No conflicts detected.</div>'; return; }
    list.innerHTML = '';
    for(const [eid, blockers] of conflicts){
      const item = document.createElement('div');
      item.className = 'item';
      item.innerHTML = `<div><strong>${eid}</strong></div><div class="meta">overlaps with ${blockers.join(', ')}</div>`;
      list.appendChild(item);
    }
  }catch(err){
    list.innerHTML = `<div class="meta">Error: ${err.message}</div>`;
  }
}

async function loadRequestSummary(){
  const box = $('#request-summary');
  box.innerHTML = 'Loading...';
  try{
    const rep = await api('/requests/report');
    const c = rep.Counts;
    box.innerHTML = `
      <div class="stat"><div class="value">${c['Open']||0}</div><div class="label">Open</div></div>
      <div class="stat"><div class="value">${c['In-Progress']||0}</div><div class="label">In-Progress</div></div>
      <div class="stat"><div class="value">${c['Resolved']||0}</div><div class="label">Resolved</div></div>
    `;
  }catch(err){
    box.innerHTML = `<div class="meta">Error: ${err.message}</div>`;
  }
}

function bindForms(){
  // Add Event
  $('#form-event').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const note = $('#event-note');
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd.entries());
    try{
      await api('/events', {method:'POST', body: JSON.stringify(data)});
      setNote(note, 'Event created');
      e.target.reset();
      await loadEvents();
      await loadConflicts();
    }catch(err){ setNote(note, err.message, false); }
  });

  // Register Student (also creates student if not present)
  $('#form-register').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const note = $('#register-note');
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd.entries());
    try{
      if(data.name){
        // create student silently if provided
        await api('/students', {method:'POST', body: JSON.stringify({
          student_id:data.student_id, name:data.name, dept:data.dept||'NA', year: parseInt(data.year||'1',10), contact:data.contact||''
        })}).catch(()=>{});
      }
      const out = await api('/registrations', {method:'POST', body: JSON.stringify({
        student_id:data.student_id, event_id:data.event_id
      })});
      setNote(note, `Registration ${out.status}`);
      e.target.reset();
      await loadEvents();
    }catch(err){ setNote(note, err.message, false); }
  });

  // Raise Request
  $('#form-request').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const note = $('#request-note');
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd.entries());
    try{
      await api('/requests', {method:'POST', body: JSON.stringify(data)});
      setNote(note, 'Request submitted');
      e.target.reset();
      await loadRequestSummary();
    }catch(err){ setNote(note, err.message, false); }
  });

  // Update Request Status
  $('#form-request-status').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const note = $('#request-status-note');
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd.entries());
    try{
      await api(`/requests/${encodeURIComponent(data.request_id)}`, {method:'PATCH', body: JSON.stringify({status:data.status})});
      setNote(note, 'Status updated');
      e.target.reset();
      await loadRequestSummary();
    }catch(err){ setNote(note, err.message, false); }
  });
}

function bindTabs(){
  $$('.tab').forEach(tab => tab.addEventListener('click', ()=>{
    activateTab(tab);
    if(tab.dataset.tab==='events') loadEvents();
    if(tab.dataset.tab==='conflicts') loadConflicts();
    if(tab.dataset.tab==='requests') loadRequestSummary();
  }));
}

// Init
bindTabs();
bindForms();
loadEvents();
loadConflicts();
loadRequestSummary();

