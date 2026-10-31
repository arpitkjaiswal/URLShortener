'use strict';
const $ = id => document.getElementById(id);
const sessionChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('linkly-session') : null;
let links = [], unlocked = false, sessionTimer, searchTimer, editingCode;
let pageNumber = 1, pageCount = 1, requestNumber = 0, viewVersion = 0, libraryAbort;

const date = value => value ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString() : 'Never';
const expired = item => Boolean(item.expires_at && new Date(/[zZ]|[+-]\d\d:\d\d$/.test(item.expires_at) ? item.expires_at : `${item.expires_at}Z`) <= new Date());
const status = item => expired(item) ? 'Expired' : item.is_paused ? 'Paused' : 'Active';
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function toast(message) {
  const node = element('div', message, 'toast'); $('toast-container').append(node);
  setTimeout(() => node.remove(), 4500);
}
async function api(path, options = {}) {
  const response = await fetch(`/api/v1/${path}`, { ...options, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...options.headers } });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const error = new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(e => `${e.loc.at(-1)}: ${e.msg}`).join('; ') : 'Something went wrong. Please try again.');
    error.status = response.status;
    if ([401, 503].includes(response.status) && path !== 'auth/login') clearPrivateView();
    throw error;
  }
  return data;
}
async function copy(value) {
  try { await navigator.clipboard.writeText(value); toast('Copied. Ready to share!'); }
  catch {
    const input = element('textarea'); input.value = value; document.body.append(input); input.select();
    const ok = document.execCommand('copy'); input.remove();
    toast(ok ? 'Copied.' : 'Please select the link and copy it manually.');
  }
}
function button(text, action) {
  const node = element('button', text, 'secondary'); node.type = 'button'; node.addEventListener('click', action); return node;
}
function downloadQR(code) {
  const a = element('a', '↓ QR', 'button secondary'); a.href = `/api/v1/qr/${encodeURIComponent(code)}`; a.download = `link-${code}.svg`; return a;
}
function normalizeDestination(value) {
  let destination = value.trim();
  if (!/^[a-z][a-z0-9+.-]*:/i.test(destination)) destination = `https://${destination}`;
  let url;
  try { url = new URL(destination); } catch { throw new Error('Please enter a website address, such as example.com.'); }
  if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password || /[\s\\]/.test(destination)) throw new Error('Enter a valid HTTP or HTTPS address without a username or password.');
  return destination;
}
function render() {
  if (!unlocked) return;
  $('recent-urls').replaceChildren();
  if (!links.length) {
    const filtered = $('search').value || $('status-filter').value !== 'all' || $('tag-filter').value;
    const empty = element('div', undefined, 'empty');
    empty.append(element('h3', filtered ? 'No matches just yet.' : 'Your next great link belongs here.'), element('p', filtered ? 'Try another search or clear the filters.' : 'Create a link above, or open Batch studio to get started.'));
    if (filtered) empty.append(button('Clear filters', resetFilters));
    $('recent-urls').append(empty); return;
  }
  for (const item of links) {
    const card = element('article', undefined, 'link-card');
    const info = element('div');
    if (item.title) info.append(element('h3', item.title, 'link-title'));
    const a = element('a', item.short_url); a.href = item.short_url; a.target = '_blank'; a.rel = 'noopener noreferrer'; info.append(a);
    info.append(element('p', item.original_url, 'destination'));
    const meta = element('div', undefined, 'meta');
    meta.append(element('span', status(item), `badge ${status(item).toLowerCase()}`));
    if (item.tag) meta.append(element('span', `#${item.tag}`, 'badge'));
    meta.append(element('span', `${item.clicks.toLocaleString()} ${item.clicks === 1 ? 'click' : 'clicks'}`), element('span', `Created ${date(item.created_at)}`), element('span', item.expires_at ? `Expires ${date(item.expires_at)}` : 'No expiry'));
    info.append(meta);
    const actions = element('div', undefined, 'actions');
    actions.append(button('Copy', () => copy(item.short_url)), button('Insights', () => insights(item)), button('Edit', () => editLink(item)));
    actions.append(button(item.is_paused ? 'Resume' : 'Pause', async event => {
      const version = viewVersion; event.currentTarget.disabled = true;
      try {
        await api(`urls/${encodeURIComponent(item.short_code)}`, {method:'PATCH', body:JSON.stringify({is_paused:!item.is_paused})});
        if (version !== viewVersion) return;
        toast(item.is_paused ? 'Sharing resumed. Expiry settings still apply.' : 'Sharing paused. You can resume it anytime.'); await load();
      } catch(error) { toast(error.message); event.target.disabled = false; }
    }));
    if (status(item) === 'Active') actions.append(downloadQR(item.short_code));
    actions.append(button('Delete', async event => {
      if (!confirm(`Delete /${item.short_code}? Its link and analytics will be removed permanently. You can pause it instead.`)) return;
      const version = viewVersion; event.currentTarget.disabled = true;
      try { await api(`urls/${encodeURIComponent(item.short_code)}`, {method:'DELETE'}); if (version !== viewVersion) return; toast('Link deleted.'); await load(); }
      catch(error) { toast(error.message); event.target.disabled = false; }
    }));
    card.append(info, actions); $('recent-urls').append(card);
  }
}
async function load({reset = false} = {}) {
  if (reset) pageNumber = 1;
  libraryAbort?.abort(); libraryAbort = new AbortController();
  const signal = libraryAbort.signal, number = ++requestNumber, version = viewVersion;
  $('refresh').disabled = true; $('recent-urls').setAttribute('aria-busy', 'true');
  const params = new URLSearchParams({page:pageNumber, page_size:20, q:$('search').value.trim(), state:$('status-filter').value, sort:$('sort-links').value, tag:$('tag-filter').value});
  try {
    const data = await api(`library?${params}`, {signal});
    const session = await api('auth/session', {signal});
    if (number !== requestNumber || version !== viewVersion) return;
    clearTimeout(sessionTimer); sessionTimer = setTimeout(lockDashboard, session.expires_in * 1000);
    links = data.items; pageNumber = data.page; pageCount = data.total_pages; unlocked = true;
    $('private-dashboard').hidden = false; $('session-bar').hidden = false; $('pagination').hidden = false;
    $('access-message').textContent = '';
    for (const [id,key] of [['total-links','links'],['total-clicks','clicks'],['active-links','active'],['paused-links','paused']]) $(id).textContent = data.summary[key].toLocaleString();
    const selectedTag = $('tag-filter').value;
    $('tag-filter').replaceChildren(new Option('All tags',''));
    for (const tag of new Set([...data.tags, ...(selectedTag ? [selectedTag] : [])])) $('tag-filter').append(new Option(tag,tag));
    $('tag-filter').value = selectedTag;
    $('page-info').textContent = `${data.total.toLocaleString()} matching ${data.total === 1 ? 'link' : 'links'} · Page ${data.page} of ${data.total_pages}`;
    $('prev-page').disabled = pageNumber <= 1; $('next-page').disabled = pageNumber >= pageCount;
    render();
  } catch(error) {
    if (error.name === 'AbortError' || (number !== requestNumber && error.status !== 401 && error.status !== 503)) return;
    if ([401, 503].includes(error.status)) {
      $('recent-urls').replaceChildren(element('p', error.status === 503 ? 'Management is locked. Set your private ADMIN_TOKEN in your deployment settings.' : 'Your workspace is private. Open Management access above to unlock your links.', 'empty'));
    } else {
      $('recent-urls').replaceChildren(element('p', 'We couldn’t load your workspace. Please try Refresh in a moment.', 'empty'));
    }
  } finally {
    if (number === requestNumber || !unlocked) { $('refresh').disabled = false; $('recent-urls').setAttribute('aria-busy','false'); }
  }
}
function resetFilters() {
  $('search').value = ''; $('status-filter').value = 'all'; $('tag-filter').value = ''; $('sort-links').value = 'newest';
  return load({reset:true});
}
function chart(days) {
  const ns = 'http://www.w3.org/2000/svg';
  const svgNode = (name, attrs, text) => { const n = document.createElementNS(ns,name); for(const [k,v] of Object.entries(attrs)) n.setAttribute(k,v); if(text) n.textContent = text; return n; };
  const svg = svgNode('svg', {viewBox:'0 0 490 155', role:'img', 'aria-label':'Daily click counts for the last 14 days in UTC', class:'chart'});
  svg.append(svgNode('line',{x1:0,y1:120,x2:490,y2:120}));
  const max = Math.max(1,...days.map(d=>d.clicks));
  days.forEach((day,index) => {
    const height = day.clicks / max * 90;
    const rect = svgNode('rect',{x:index*35+7,y:120-height,width:21,height:Math.max(1,height),rx:3});
    rect.append(svgNode('title',{},`${day.day}: ${day.clicks} clicks`)); svg.append(rect);
    if ([0,6,13].includes(index)) svg.append(svgNode('text',{x:index*35+4,y:145},day.day.slice(5)));
  });
  return svg;
}
async function insights(item) {
  const version = viewVersion;
  try {
    const data = await api(`analytics/${encodeURIComponent(item.short_code)}`);
    if (!unlocked || version !== viewVersion) return;
    const box = $('stats-body'); box.replaceChildren();
    const total = data.days.reduce((sum,d)=>sum+d.clicks,0);
    box.append(element('p', `${total.toLocaleString()} clicks in the last 14 days`, 'chart-total'), chart(data.days));
    const details = element('details'); details.append(element('summary','View daily counts'));
    const table = element('table',undefined,'analytics-table'), header = element('tr');
    header.append(element('th','Day (UTC)'),element('th','Clicks')); table.append(header);
    for (const day of data.days) {const row = element('tr'); row.append(element('td',day.day),element('td',String(day.clicks))); table.append(row);}
    details.append(table); box.append(details,element('small',data.tracking_note));
    const dl = element('dl');
    for (const [label,value] of [['Title',data.link.title || 'Untitled'],['Destination',data.link.original_url],['Short link',data.link.short_url],['Status',status(data.link)],['All-time clicks',data.link.clicks],['Expires',date(data.link.expires_at)],['Last visit',data.last_accessed ? date(data.last_accessed) : 'No visits yet']]) dl.append(element('dt',label),element('dd',String(value)));
    box.append(dl); $('stats-modal').showModal();
  } catch(error) { toast(error.message); }
}
$('shorten-form').addEventListener('submit', async event => {
  event.preventDefault(); const submit = $('submit-button'); if (submit.disabled) return;
  $('message').textContent = ''; $('result').hidden = true;
  let payload;
  try {
    const destination = normalizeDestination($('url-input').value);
    const entries = [['utm_source',$('utm-source').value.trim()],['utm_medium',$('utm-medium').value.trim()],['utm_campaign',$('utm-campaign').value.trim()]].filter(([,value])=>value);
    const tracked = new URL(destination);
    for(const [key,value] of entries) tracked.searchParams.set(key,value);
    payload = {url:entries.length ? tracked.href : destination};
  } catch(error) { $('message').textContent = error.message; $('message').dataset.kind = 'error'; $('url-input').focus(); return; }
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
    $('share-result').onclick = async () => {
      if (!navigator.share) return copy(data.short_url);
      try { await navigator.share({title:'A link for you',url:data.short_url}); } catch(error) {if(error.name !== 'AbortError') copy(data.short_url);}
    };
    $('result').hidden = false; $('message').textContent = 'Your short link is ready. Make it go places.'; $('message').dataset.kind = 'success';
    $('shorten-form').reset(); $('link-options').open = false;
    if (unlocked) await load({reset:true});
  } catch(error) { $('message').textContent = error.message; $('message').dataset.kind = 'error'; }
  finally { submit.disabled = false; submit.textContent = 'Shorten link →'; }
});
$('bulk-form').addEventListener('submit', async event => {
  event.preventDefault(); if ($('bulk-submit').disabled) return;
  const rows = $('bulk-input').value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);
  if (!rows.length || rows.length > 20) { $('bulk-message').textContent = 'Enter between 1 and 20 destinations, one per line.'; return; }
  const urls = rows.map(row => {try {return normalizeDestination(row);} catch {return row;}});
  $('bulk-submit').disabled = true; $('bulk-results').replaceChildren(); $('bulk-message').textContent = 'Creating your links…';
  const version = viewVersion;
  try {
    const results = await api('bulk',{method:'POST',body:JSON.stringify({urls})});
    if (version !== viewVersion) return;
    const successes = results.filter(r=>r.short_url);
    $('bulk-message').textContent = `${successes.length} created · ${results.length-successes.length} need attention. Only failed destinations remain in the input.`;
    if (successes.length) $('bulk-results').append(button('Copy all created links',()=>copy(successes.map(r=>r.short_url).join('\n'))));
    for(const result of results) {
      const row = element('div',undefined,'bulk-row'); row.append(element('small',`${result.index+1}. ${result.url}`));
      if(result.short_url) {const a = element('a',result.short_url); a.href = result.short_url; a.target='_blank'; a.rel='noopener noreferrer'; row.append(a);}
      else row.append(element('p',result.error));
      $('bulk-results').append(row);
    }
    $('bulk-input').value = results.filter(r=>r.error).map(r=>r.url).join('\n'); await load({reset:true});
  } catch(error) { if(version === viewVersion) $('bulk-message').textContent = `${error.message} Check your workspace before retrying to avoid duplicates.`; }
  finally { $('bulk-submit').disabled = false; }
});
$('refresh').addEventListener('click',()=>load());
$('unlock').addEventListener('click', async () => {
  const key = $('access-key').value; $('access-key').value = '';
  $('unlock').disabled = true; $('access-message').textContent = '';
  try { await api('auth/login', {method:'POST',body:JSON.stringify({key})}); await load(); if(unlocked) document.querySelector('.access').open=false; }
  catch(error) { $('access-message').textContent=error.message; }
  finally { $('unlock').disabled=false; }
});
$('access-key').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault(); $('unlock').click();}});
$('lock-dashboard').addEventListener('click',lockDashboard);
for (const id of ['status-filter','sort-links','tag-filter']) $(id).addEventListener('change',()=>load({reset:true}));
$('search').addEventListener('input',()=>{clearTimeout(searchTimer); searchTimer=setTimeout(()=>load({reset:true}),250);});
$('prev-page').addEventListener('click',()=>{if(pageNumber>1){pageNumber--; load();}});
$('next-page').addEventListener('click',()=>{if(pageNumber<pageCount){pageNumber++; load();}});
$('modal-close').addEventListener('click',()=>$('stats-modal').close());
$('stats-modal').addEventListener('click',event=>{if(event.target===$('stats-modal')) $('stats-modal').close();});
$('export').addEventListener('click',()=>{
  if(!links.length){toast('No links on this page to export.'); return;}
  const cell=value=>{let text=String(value??''); if(/^\s*[=+@-]|^[\t\r\n]/.test(text)) text=`'${text}`; return `"${text.replaceAll('"','""')}"`;};
  const rows=[['Title','Tag','Short URL','Destination','Status','Clicks','Created','Expires'],...links.map(item=>[item.title,item.tag,item.short_url,item.original_url,status(item),item.clicks,item.created_at,item.expires_at])];
  const url=URL.createObjectURL(new Blob([rows.map(row=>row.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
  const a=element('a'); a.href=url; a.download='linkly-links.csv'; document.body.append(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
});
function clearPrivateView() {
  viewVersion++; requestNumber++; libraryAbort?.abort(); unlocked=false; links=[]; pageNumber=1;
  clearTimeout(searchTimer); clearTimeout(sessionTimer);
  for (const id of ['private-dashboard','session-bar','pagination']) $(id).hidden=true;
  $('recent-urls').replaceChildren(element('p','Your workspace is private. Open Management access above to unlock your links.','empty'));
  $('stats-body').replaceChildren(); $('stats-modal').close(); $('edit-modal').close();
  $('edit-form').reset(); $('edit-code').textContent=''; editingCode=null;
  for(const id of ['total-links','total-clicks','active-links','paused-links']) $(id).textContent='—';
  $('search').value=''; $('status-filter').value='all'; $('tag-filter').replaceChildren(new Option('All tags',''));
  $('bulk-form').reset(); $('bulk-results').replaceChildren(); $('bulk-message').textContent=''; $('bulk-tool').open=false;
  $('refresh').disabled=false; $('recent-urls').setAttribute('aria-busy','false');
}
async function lockDashboard() {
  clearPrivateView();
  try {await api('auth/logout',{method:'POST',body:'{}'}); sessionChannel?.postMessage('locked'); toast('Workspace locked.');}
  catch {toast('Workspace hidden. Please try locking again to end the server session.');}
}
function editLink(item) {
  editingCode=item.short_code; $('edit-code').textContent=`Editing /${item.short_code}`;
  $('edit-name').value=item.title; $('edit-tag').value=item.tag;
  $('edit-url').value=item.original_url; $('edit-expiry').value='keep'; $('edit-message').textContent='';
  $('edit-modal').showModal();
}
$('edit-close').addEventListener('click',()=>$('edit-modal').close());
$('edit-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('save-edit').disabled=true; $('edit-message').textContent='';
  const version=viewVersion;
  try {
    const payload={url:normalizeDestination($('edit-url').value),title:$('edit-name').value.trim(),tag:$('edit-tag').value.trim()};
    if($('edit-expiry').value!=='keep') payload.ttl_seconds=$('edit-expiry').value==='never'?null:Number($('edit-expiry').value);
    await api(`urls/${encodeURIComponent(editingCode)}`,{method:'PATCH',body:JSON.stringify(payload)});
    if(version!==viewVersion) return;
    $('edit-modal').close(); toast('Saved. Same short link, fresh possibilities.'); await load();
  } catch(error) {if(version===viewVersion) $('edit-message').textContent=error.message;}
  finally {$('save-edit').disabled=false;}
});
if(sessionChannel) sessionChannel.onmessage=clearPrivateView;
window.addEventListener('pagehide',clearPrivateView);
window.addEventListener('pageshow',event=>{if(event.persisted) load();});
load();
