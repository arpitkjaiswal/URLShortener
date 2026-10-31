'use strict';
const $ = id => document.getElementById(id);
const sessionChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('linkly-session') : null;
let links = [], loading = false, unlocked = false, sessionTimer, editingCode, viewVersion = 0;
const date = value => value ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString() : 'Never';
const expired = item => item.expires_at && new Date(/[zZ]|[+-]\d\d:\d\d$/.test(item.expires_at) ? item.expires_at : `${item.expires_at}Z`) <= new Date();
function element(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function toast(message) { const node = element('div', message, 'toast'); $('toast-container').append(node); setTimeout(() => node.remove(), 4500); }
async function api(path, options = {}) {
  const response = await fetch(`/api/v1/${path}`, { ...options, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...options.headers } });
  const data = await response.json().catch(() => null);
  if (!response.ok) { const detail = data?.detail; const error = new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(e => `${e.loc.at(-1)}: ${e.msg}`).join('; ') : 'Something went wrong. Please try again.'); error.status = response.status; if (response.status === 401 && path !== 'auth/login') clearPrivateView(); throw error; }
  return data;
}
async function copy(value) {
  try { await navigator.clipboard.writeText(value); toast('Link copied. Ready to share!'); }
  catch { const input = element('textarea'); input.value = value; document.body.append(input); input.select(); const ok = document.execCommand('copy'); input.remove(); toast(ok ? 'Link copied.' : 'Select the short link and copy it manually.'); }
}
function button(text, action) { const node = element('button', text, 'secondary'); node.type = 'button'; node.addEventListener('click', action); return node; }
function downloadQR(code) { const a = element('a', '↓ QR', 'button secondary'); a.href = `/api/v1/qr/${encodeURIComponent(code)}`; a.download = `link-${code}.svg`; return a; }
function render() {
  $('total-links').textContent = links.length;
  $('total-clicks').textContent = links.reduce((sum, item) => sum + item.clicks, 0).toLocaleString();
  $('active-links').textContent = links.filter(item => !expired(item)).length;
  const query = $('search').value.trim().toLowerCase();
  if (!unlocked) return;
  const filtered = links.filter(item => `${item.original_url} ${item.short_code}`.toLowerCase().includes(query))
    .filter(item => $('status-filter').value === 'all' || ($('status-filter').value === 'expired' ? expired(item) : !expired(item)))
    .sort((a, b) => $('sort-links').value === 'clicks' ? b.clicks - a.clicks : $('sort-links').value === 'oldest' ? a.created_at.localeCompare(b.created_at) : b.created_at.localeCompare(a.created_at));
  $('recent-urls').replaceChildren();
  if (!filtered.length) { $('recent-urls').append(element('p', query ? 'No matches. Try a different destination or alias.' : 'Your next link belongs here. Shorten a URL above to get started.', 'empty')); return; }
  for (const item of filtered) {
    const card = element('article', undefined, 'link-card');
    const info = element('div');
    const a = element('a', item.short_url); a.href = item.short_url; a.target = '_blank'; a.rel = 'noopener noreferrer'; info.append(a);
    info.append(element('p', item.original_url, 'destination'));
    const meta = element('div', undefined, 'meta'); const isExpired = expired(item);
    meta.append(element('span', isExpired ? 'Expired' : 'Active', `badge${isExpired ? ' expired' : ''}`), element('span', `${item.clicks.toLocaleString()} clicks`), element('span', `Created ${date(item.created_at)}`), element('span', item.expires_at ? `Expires ${date(item.expires_at)}` : 'No expiry'));
    info.append(meta);
    const actions = element('div', undefined, 'actions');
    actions.append(button('Copy', () => copy(item.short_url)), button('Insights', () => insights(item)), button('Edit', () => editLink(item)));
    if (!isExpired) actions.append(downloadQR(item.short_code));
    actions.append(button('Delete', async event => {
      if (!confirm(`Delete /${item.short_code}? This link will stop working permanently.`)) return;
      event.currentTarget.disabled = true;
      try { await api(`urls/${encodeURIComponent(item.short_code)}`, {method:'DELETE'}); links = links.filter(link => link.short_code !== item.short_code); render(); toast('Link deleted.'); }
      catch (error) { toast(error.message); event.target.disabled = false; }
    }));
    card.append(info, actions); $('recent-urls').append(card);
  }
}
async function load() {
  if (loading) return;
  const version = viewVersion;
  loading = true; $('refresh').disabled = true;
  try {
    const data = await api('urls?limit=50');
    const session = await api('auth/session');
    if (version !== viewVersion) return;
    clearTimeout(sessionTimer); sessionTimer = setTimeout(lockDashboard, session.expires_in * 1000);
    links = data; unlocked = true; $('private-dashboard').hidden = false; $('session-bar').hidden = false;
    $('access-message').textContent = ''; render();
  }
  catch(error) { clearPrivateView(); ['total-links','total-clicks','active-links'].forEach(id => $(id).textContent = '—'); $('recent-urls').replaceChildren(element('p', error.status === 401 ? 'Your dashboard is locked. Open Management access above to sign in. Shared short links still work.' : 'We couldn’t load your links. Please try Refresh in a moment.', 'empty')); }
  finally { loading = false; $('refresh').disabled = false; }
}
async function insights(item) {
  try {
    const version = viewVersion;
    const data = expired(item) ? item : await api(`stats/${encodeURIComponent(item.short_code)}`);
    if (!unlocked || version !== viewVersion) return;
    const dl = element('dl');
    for (const [label,value] of [['Destination',data.original_url],['Short link',item.short_url],['Total clicks',data.clicks],['Created',date(data.created_at)],['Expires',date(data.expires_at)],['Last visit',data.last_accessed ? date(data.last_accessed) : expired(item) ? 'Unavailable for expired links' : 'No visits yet']]) dl.append(element('dt',label),element('dd',String(value)));
    $('stats-body').replaceChildren(dl); $('stats-modal').showModal();
  } catch(error) { toast(error.message); }
}
$('shorten-form').addEventListener('submit', async event => {
  event.preventDefault(); const submit = $('submit-button'); if (submit.disabled) return;
  $('message').textContent = ''; $('result').hidden = true;
  let payload;
  try { payload = {url:normalizeDestination($('url-input').value)}; }
  catch(error) { $('message').textContent = error.message; $('message').dataset.kind = 'error'; $('url-input').focus(); return; }
  if ($('alias-input').value.trim()) payload.custom_alias = $('alias-input').value.trim();
  if ($('ttl-input').value) payload.ttl_seconds = Number($('ttl-input').value) * Number($('ttl-unit').value);
  if (payload.ttl_seconds > 315360000) { $('message').textContent = 'Choose an expiry of 10 years or less.'; $('message').dataset.kind = 'error'; return; }
  submit.disabled = true; submit.textContent = 'Creating your link…';
  try {
    const data = await api('shorten',{method:'POST',body:JSON.stringify(payload)});
    $('short-url').textContent = data.short_url; $('short-url').href = data.short_url;
    $('qr-result').href = `/api/v1/qr/${encodeURIComponent(data.short_code)}`;
    $('result-expiry').textContent = data.expires_at ? `Expires ${date(data.expires_at)}` : 'Ready to share. This link has no expiry.';
    $('copy-result').onclick = () => copy(data.short_url);
    $('result').hidden = false; $('message').textContent = 'Your short link has been created.'; $('message').dataset.kind = 'success';
    $('shorten-form').reset(); $('link-options').open = false; await load();
  } catch(error) { $('message').textContent = error.message; $('message').dataset.kind = 'error'; }
  finally { submit.disabled = false; submit.textContent = 'Shorten link →'; }
});
$('refresh').addEventListener('click',load);
$('unlock').addEventListener('click', async () => {
  const key = $('access-key').value; $('access-key').value = '';
  $('unlock').disabled = true; $('access-message').textContent = '';
  try {
    await api('auth/login', {method:'POST', body:JSON.stringify({key})});
    clearTimeout(sessionTimer); sessionTimer = setTimeout(lockDashboard, 30 * 60 * 1000);
    await load(); if (unlocked) document.querySelector('.access').open = false;
  } catch(error) { $('access-message').textContent = error.message; }
  finally { $('unlock').disabled = false; }
});
$('lock-dashboard').addEventListener('click', lockDashboard);
$('status-filter').addEventListener('change', render);
$('sort-links').addEventListener('change', render);
$('access-key').addEventListener('keydown',event => {if(event.key === 'Enter') { event.preventDefault(); $('unlock').click(); }});
$('search').addEventListener('input',render);
$('modal-close').addEventListener('click',() => $('stats-modal').close());
$('stats-modal').addEventListener('click',event => {if(event.target === $('stats-modal')) $('stats-modal').close();});
$('export').addEventListener('click',() => {
  if (!links.length) {toast('Load some links before exporting.'); return;}
  const cell = value => { let text = String(value ?? ''); if (/^[=+@\-\t\r\n]/.test(text)) text = `'${text}`; return `"${text.replaceAll('"','""')}"`; };
  const rows = [['Short URL','Destination','Clicks','Created','Expires'],...links.map(item => [item.short_url,item.original_url,item.clicks,item.created_at,item.expires_at])];
  const url = URL.createObjectURL(new Blob([rows.map(row => row.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
  const a = element('a'); a.href = url; a.download = 'linkly-links.csv'; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
});

function clearPrivateView() {
  viewVersion++; unlocked = false; links = [];
  $('private-dashboard').hidden = true; $('session-bar').hidden = true;
  $('recent-urls').replaceChildren(element('p', 'Your dashboard is locked. Open Management access above to sign in.', 'empty'));
  $('stats-body').replaceChildren(); $('stats-modal').close(); $('edit-modal').close();
  $('edit-form').reset(); $('edit-code').textContent = ''; editingCode = null;
  ['total-links', 'total-clicks', 'active-links'].forEach(id => $(id).textContent = '—');
  $('search').value = '';
}
async function lockDashboard() {
  clearTimeout(sessionTimer); clearPrivateView();
  try { await api('auth/logout', {method:'POST',body:'{}'}); sessionChannel?.postMessage('locked'); toast('Dashboard locked.'); }
  catch { toast('Dashboard hidden. Close this browser to discard its session, or try locking again.'); }
}
function normalizeDestination(value) {
  let destination = value.trim();
  if (!/^[a-z][a-z0-9+.-]*:/i.test(destination)) destination = `https://${destination}`;
  const url = new URL(destination);
  if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || /[\s\\]/.test(destination)) throw new Error('Enter a valid website address without a username or password.');
  return destination;
}
function editLink(item) {
  editingCode = item.short_code; $('edit-code').textContent = `Editing /${item.short_code}`;
  $('edit-url').value = item.original_url; $('edit-expiry').value = 'keep'; $('edit-message').textContent = '';
  $('edit-modal').showModal();
}
$('edit-close').addEventListener('click', () => $('edit-modal').close());
$('edit-form').addEventListener('submit', async event => {
  event.preventDefault(); $('save-edit').disabled = true; $('edit-message').textContent = '';
  const version = viewVersion;
  try {
    const payload = {url:normalizeDestination($('edit-url').value)};
    if ($('edit-expiry').value !== 'keep') payload.ttl_seconds = $('edit-expiry').value === 'never' ? null : Number($('edit-expiry').value);
    await api(`urls/${encodeURIComponent(editingCode)}`, {method:'PATCH', body:JSON.stringify(payload)});
    if (version !== viewVersion) return;
    $('edit-modal').close(); toast('Link updated. Your short address stays the same.'); await load();
  } catch(error) { $('edit-message').textContent = error.message; }
  finally { $('save-edit').disabled = false; }
});
if (sessionChannel) sessionChannel.onmessage = () => clearPrivateView();
window.addEventListener('pagehide', clearPrivateView);
window.addEventListener('pageshow', event => { if (event.persisted) load(); });
load();
