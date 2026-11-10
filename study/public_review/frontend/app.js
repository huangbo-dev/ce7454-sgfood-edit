'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const QUESTIONS = ['Change achieved', 'Other food preserved', 'Looks plausible'];
  const CHOICES = ['Yes', 'No', 'Unsure'];
  let token = null, manifest = null, ratings = new Map(), index = 0;
  let dirty = false, timer = null, urls = [], generation = 0, busy = false;
  let pendingRating = null, pendingFamiliarity = null, countdownTimer = null, expiresAt = 0;
  const status = message => { $('status').textContent = message; };
  function revokeImages() { urls.forEach(url => URL.revokeObjectURL(url)); urls = []; $('images').replaceChildren(); }
  function reset(message = '') {
    generation++; clearTimeout(timer); clearInterval(countdownTimer); timer = null; countdownTimer = null; expiresAt = 0; token = null; manifest = null;
    $('countdown').textContent = ''; $('expiry-warning').textContent = ''; $('expiry-warning').hidden = true;
    ratings.clear(); index = 0; dirty = false; busy = false; pendingRating = null; pendingFamiliarity = null;
    revokeImages(); $('questions').replaceChildren(); $('task').textContent = ''; $('position').textContent = '';
    $('notice').textContent = ''; $('saved').textContent = ''; $('title').textContent = 'Image review';
    $('login').reset(); $('familiarity').reset(); $('login-panel').hidden = false;
    $('review').hidden = true; $('session').hidden = true; $('item-panel').hidden = true;
    $('familiarity-panel').hidden = false; status(message);
  }
  function updateCountdown() {
    if (!token) return;
    const remaining = Math.ceil((expiresAt - Date.now()) / 1000);
    if (remaining <= 0) { reset('Your session expired. Unsaved drafts were cleared. Please sign in again to load saved responses.'); return; }
    $('countdown').textContent = `Session time remaining: ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2,'0')}`;
    if (remaining <= 120 && $('expiry-warning').hidden) {
      $('expiry-warning').hidden = false;
      $('expiry-warning').textContent = 'Your session expires in less than two minutes. Save your responses now. Unsaved drafts will be lost at expiry.';
    }
  }
  async function api(path, body = {}, media = false) {
    updateCountdown();
    const current = token;
    if (!current) throw new Error('Please sign in again.');
    const response = await fetch(path, {method:'POST', credentials:'omit', cache:'no-store',
      headers:{'Content-Type':'application/json', Authorization:`Bearer ${current}`}, body:JSON.stringify(body)});
    if (current !== token) throw new Error('Session ended.');
    if (response.status === 401 || response.status === 403) {
      reset('Your session ended. Please sign in again.'); throw new Error('Your session ended. Please sign in again.');
    }
    if (!response.ok) {
      const error = new Error(response.status === 409 ? 'Save conflict: the server has a different revision or submission. Nothing was automatically overwritten. Copy any unsaved notes you want to keep, then log out and sign in again to reload the latest saved revision before editing.' : `Request failed (${response.status}). You can try again. Retrying the same unchanged response reuses its submission ID.`);
      error.status = response.status; throw error;
    }
    return media ? response.blob() : response.json();
  }
  const report = error => status(error.message || 'Something went wrong. Please try again.');
  function setBusy(value) {
    busy = value;
    $('save').disabled = value; $('previous').disabled = value || index === 0;
    $('next').disabled = value || !manifest || index >= manifest.items.length - 1;
  }
  function buildQuestions(payload) {
    $('questions').replaceChildren();
    for (const side of ['A','B']) {
      const card = document.createElement('section'); card.className = 'rating-card';
      const heading = document.createElement('h3'); heading.textContent = side; card.append(heading);
      QUESTIONS.forEach((question, q) => {
        const fieldset = document.createElement('fieldset'); const legend = document.createElement('legend');
        legend.textContent = question; fieldset.append(legend);
        for (const choice of CHOICES) {
          const label = document.createElement('label'); const input = document.createElement('input');
          input.type = 'radio'; input.name = `${side}-${q}`; input.value = choice; input.required = true;
          input.checked = payload?.[side]?.[question] === choice; label.append(input,document.createTextNode(choice)); fieldset.append(label);
        }
        card.append(fieldset);
      });
      const label = document.createElement('label'); label.htmlFor = `${side}-note`; label.textContent = 'Optional note (up to 1,000 characters)';
      const note = document.createElement('textarea'); note.id = `${side}-note`; note.maxLength = 1000; note.value = payload?.[side]?.note || '';
      card.append(label,note); $('questions').append(card);
    }
  }
  async function showItem() {
    const epoch = ++generation; revokeImages(); dirty = false; pendingRating = null; status('');
    $('item-panel').hidden = false; $('familiarity-panel').hidden = true;
    if (!manifest.items.length) { $('task').textContent = 'No review items are available.'; $('rating').hidden = true; return; }
    $('rating').hidden = false; const item = manifest.items[index], saved = ratings.get(item.id);
    $('position').textContent = `Item ${index + 1} of ${manifest.items.length}`;
    $('task').textContent = item.task_text; $('saved').textContent = saved ? `Saved revision ${saved.revision}` : 'Not saved yet';
    buildQuestions(saved?.payload); setBusy(true);
    try {
      await api('/api/exposure',{submission_id:crypto.randomUUID(),item_id:item.id});
      if (epoch !== generation) return;
      for (const [label,key] of [['Original','original'],['A','A'],['B','B']]) {
        const blob = await api('/api/media',{name:item[key]},true);
        if (epoch !== generation) return;
        const url = URL.createObjectURL(blob); urls.push(url);
        const figure = document.createElement('figure'), caption = document.createElement('figcaption'), img = document.createElement('img');
        caption.textContent = label; img.alt = `${label}: ${item.task_text}`; img.src = url;
        figure.append(caption,img); $('images').append(figure);
      }
      if (epoch === generation) setBusy(false);
    } catch (error) { if (epoch === generation) { report(error); $('previous').disabled = index === 0; $('next').disabled = index === manifest.items.length - 1; } }
  }
  $('login').addEventListener('submit',async event => {
    event.preventDefault(); const button = event.submitter; button.disabled = true; status('Signing in…');
    try {
      const response = await fetch('/api/login',{method:'POST',credentials:'omit',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('code').value})});
      $('code').value = '';
      if (!response.ok) throw new Error('Unable to sign in. Check your access code and try again.');
      const data = await response.json(); token = data.token;
      const expiry = typeof data.expires_at === 'number' ? (data.expires_at < 1e12 ? data.expires_at * 1000 : data.expires_at) : Date.parse(data.expires_at);
      if (!token || !Number.isFinite(expiry) || expiry <= Date.now()) throw new Error('The session is invalid or expired. Please sign in again.');
      expiresAt = expiry; updateCountdown(); countdownTimer = setInterval(updateCountdown,1000);
      timer = setTimeout(updateCountdown,Math.min(expiry-Date.now()+10,2147483647));
      const [loaded,state] = await Promise.all([api('/api/manifest'),api('/api/state')]);
      if (!token) return; manifest = loaded; ratings = new Map(state.ratings.map(row => [row.item_id,row]));
      $('title').textContent = manifest.title || 'Image review'; $('notice').textContent = manifest.notice || '';
      $('login-panel').hidden = true; $('review').hidden = false; $('session').hidden = false; status('');
      if (state.familiarity) await showItem();
    } catch (error) { reset(error.message); } finally { button.disabled = false; }
  });
  $('familiarity').addEventListener('submit',async event => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    const payload = {prior_familiarity:new FormData(event.target).get('familiarity'),note:$('familiarity-note').value};
    const serialized = JSON.stringify(payload);
    if (!pendingFamiliarity || pendingFamiliarity.serialized !== serialized) pendingFamiliarity = {serialized,submission_id:crypto.randomUUID()};
    try { await api('/api/familiarity',{submission_id:pendingFamiliarity.submission_id,payload}); if (token) { pendingFamiliarity = null; await showItem(); } }
    catch (error) { report(error); } finally { button.disabled = false; }
  });
  $('rating').addEventListener('input',() => { dirty = true; $('saved').textContent = 'Unsaved changes'; });
  $('rating').addEventListener('submit',async event => {
    event.preventDefault(); if (busy || !token) return;
    const item = manifest.items[index]; const payload = {}; const form = new FormData(event.target);
    for (const side of ['A','B']) { payload[side] = {note:$(`${side}-note`).value}; QUESTIONS.forEach((question,q) => {payload[side][question] = form.get(`${side}-${q}`);}); }
    const serialized = JSON.stringify(payload), epoch = generation;
    if (!pendingRating || pendingRating.serialized !== serialized) pendingRating = {serialized,submission_id:crypto.randomUUID(),base_revision:ratings.get(item.id)?.revision || 0};
    setBusy(true); $('questions').querySelectorAll('input,textarea').forEach(node => {node.disabled = true;});
    try {
      const result = await api('/api/rating',{submission_id:pendingRating.submission_id,item_id:item.id,base_revision:pendingRating.base_revision,payload});
      if (epoch !== generation) return;
      ratings.set(item.id,{item_id:item.id,revision:result.revision,payload}); pendingRating = null; dirty = false;
      $('saved').textContent = `Saved revision ${result.revision}`; status('Response saved.');
    } catch (error) { if (epoch === generation) report(error); }
    finally { if (epoch === generation) { setBusy(false); $('questions').querySelectorAll('input,textarea').forEach(node => {node.disabled = false;}); } }
  });
  function navigate(delta) { if (dirty && !confirm('Discard unsaved changes and move to another item?')) return; index += delta; showItem(); }
  $('previous').addEventListener('click',() => navigate(-1)); $('next').addEventListener('click',() => navigate(1));
  $('export').addEventListener('click',async () => {
    try { const data = await api('/api/export'); if (!token) return; const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})); urls.push(url);
      const link = document.createElement('a'); link.href = url; link.download = 'my-review-responses.json'; document.body.append(link); link.click(); link.remove();
      setTimeout(() => {URL.revokeObjectURL(url); urls = urls.filter(value => value !== url);},1000);
    } catch (error) { report(error); }
  });
  $('logout').addEventListener('click',async () => {
    if (dirty && !confirm('Log out and discard unsaved changes?')) return;
    const request = api('/api/logout'); reset('Logged out.');
    try { await request; } catch (error) { /* The local session is already cleared. */ }
  });
  window.addEventListener('beforeunload',event => {if (dirty) {event.preventDefault(); event.returnValue = '';}});
  window.addEventListener('pagehide',() => reset());
  document.addEventListener('visibilitychange',updateCountdown);
})();
