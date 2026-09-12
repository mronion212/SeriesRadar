const $ = id => document.getElementById(id);
const phases = ['Onbekend','Aangekondigd','In productie','Geproduceerd','Beschikbaar'];
const kinds = ['Onbekend','Nieuwe serie','Nieuw seizoen'];
let state = {series:[],inbox:[],ignored:[],sources:[],meta:{}}, view='series', dossierId=null, loading=false, dossierScope='', dossierTab='overview', editingProfile=null;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = s => s ? new Date(s).toLocaleString('nl-NL',{day:'numeric',month:'short',year:'numeric'}) : 'Datum onbekend';
const clock = s => s ? new Date(s).toLocaleString('nl-NL',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : 'Nog niet';
const badge = status => `<span class="status ${{'Aangekondigd':'announced','In productie':'production','Geproduceerd':'complete','Beschikbaar':'available','Onbekend':'unknown'}[status]||'unknown'}">${esc(status)}</span>`;
const productionLabel = p => p.kind==='Onbekend'?'Seizoen niet vastgesteld':p.kind==='Nieuwe serie'?'Nieuwe serie · seizoen 1':`Nieuw seizoen · ${p.season ? 'seizoen '+p.season:'nummer onbekend'}`;
const allArticles = () => [...state.series.flatMap(g=>g.articles),...state.inbox,...state.ignored];
async function request(path,data){
 const response = await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json','X-Radar-Request':'1'},body:JSON.stringify(data)}:{});
 let result; try {result=await response.json();} catch {throw new Error('De server gaf geen geldig antwoord.');}
 if(!response.ok) throw new Error(result.error||`Verzoek mislukt (${response.status}).`);
 return result;
}
async function load(){
 if(loading)return; loading=true;
 try {state=await request('/api/dashboard');$('error').hidden=true;render();}
 catch(e){$('error').textContent=e.message;$('error').hidden=false;}
 finally{loading=false;}
}
function render(){
 $('review-count').textContent=state.inbox.length;
 const failures=state.sources.filter(s=>s.enabled!==false&&s.error).length;
 $('scan-status').textContent=state.scanning?'Scan bezig…':`Laatste scan: ${clock(state.meta.last_finished)}${failures?' · '+failures+' bron(nen) met een fout':''}`;
 $('next-scan').textContent=state.scanning?'':state.meta.next_scan?`Volgende scan: ${clock(Number(state.meta.next_scan)*1000)}`:`Interval: ${Math.round(state.interval/60)} minuten`;
 $('scan').disabled=state.scanning;
 $('known-titles').innerHTML=state.series.map(g=>`<option value="${esc(g.name)}"></option>`).join('');
 renderSeries(); renderReview(); renderSources();
 if($('series-detail').open&&!$('article-detail').open&&!$('metadata-detail').open)renderDossier();
}
function renderSeries(){
 const query=$('search').value.toLocaleLowerCase('nl'),kind=$('kind-filter').value,status=$('status-filter').value;
 let groups=state.series.map(g=>({...g,visibleProductions:g.productions.filter(p=>(!kind||p.kind===kind)&&(!status||p.status===status))})).filter(g=>g.visibleProductions.length&&(!query||`${g.name} ${g.articles.map(a=>a.title+' '+a.publisher).join(' ')}`.toLocaleLowerCase('nl').includes(query)));
 if($('sort').value==='title')groups.sort((a,b)=>a.name.localeCompare(b.name,'nl'));
 $('catalog-count').textContent=`${groups.length} ${groups.length===1?'serie':'series'} · ${groups.reduce((n,g)=>n+g.articles.length,0)} nieuwsartikelen`;
 $('series-empty').hidden=groups.length>0;
 $('series-list').innerHTML=groups.map(g=>{
 const p=g.visibleProductions[0],d=(g.dossiers||[]).find(d=>d.kind===p.kind&&d.season===p.season)||g.dossiers?.[0], f=d?.fields||{};
 const cast=f.cast?.value?.split('\n').filter(Boolean)||[], network=f.platforms?.value||f.networks?.value||'Platform nog onbekend';
 return `<article class="series-card"><div class="card-top"><span class="title-mark">${esc(g.name.slice(0,2).toUpperCase())}</span>${badge(p.status)}</div><button class="series-name" data-series="${g.id}">${esc(g.name)}</button><div class="card-type">${esc(productionLabel(p))}${g.visibleProductions.length>1?' + '+(g.visibleProductions.length-1)+' producties':''}</div><div class="card-network">${esc(network.replaceAll('\n',' · '))}</div><div class="card-people"><span>${cast.length?cast.length+' castleden':'Cast nog niet ingevuld'}</span><span>${g.articles.length} artikelen</span></div><div class="card-progress"><span>Dossier</span><strong>${d?.filled||0} / ${d?.total||11} basisvelden</strong></div><progress max="${d?.total||11}" value="${d?.filled||0}" aria-label="Ingevulde basisvelden"></progress><div class="card-bottom"><span>${date(g.updated)}</span><button class="text-button" data-series="${g.id}">Dossier openen ↗</button></div></article>`;
 }).join('');
}
function newsRow(a,reason=false){return `<article class="news-row"><div class="news-meta"><span>${esc(a.publisher)}</span><span>${date(a.published)}</span>${a.classification_reviewed?'<span>Beoordeeld</span>':''}${a.tvdb?'<span>TVDB verwerkt</span>':''}</div><h3>${esc(a.title)}</h3>${reason?`<p>${esc(a.rejection||a.issue)}</p>`:`<p>${esc(productionLabel({kind:a.kind,season:a.season}))} · ${esc(a.status)}</p>`}<div class="news-actions"><a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">Bronbericht ↗</a><button class="text-button" data-article="${a.id}">Beoordelen / koppelen</button></div></article>`;}
function renderReview(){
 const query=$('review-search').value.toLowerCase(),selected=$('review-selection').value;
 const rows=state[selected].filter(a=>!query||`${a.title} ${a.publisher}`.toLowerCase().includes(query));
 $('review-list').innerHTML=rows.length?rows.map(a=>newsRow(a,true)).join(''):'<div class="empty">Geen berichten in deze selectie.</div>';
}
function renderDossier(){
 const group=state.series.find(g=>g.id===dossierId);
 if(!group){$('series-detail').close();return;}
 $('dossier-title').textContent=group.name;
 $('dossier-subtitle').textContent=group.articles.length+' nieuwsartikelen · gegevens per productie';
 $('dossier-tvdb').href='https://thetvdb.com/search?query='+encodeURIComponent(group.name);
 $('dossier-imdb').href='https://www.imdb.com/find/?q='+encodeURIComponent(group.name)+'&s=tt';
 const profiles=group.dossiers||[];
 if(!profiles.some(p=>p.scope===dossierScope))dossierScope=profiles[0]?.scope||'';
 $('dossier-scope').innerHTML=profiles.map(p=>`<option value="${esc(p.scope)}">${esc(productionLabel(p))}</option>`).join('');$('dossier-scope').value=dossierScope;
 const profile=profiles.find(p=>p.scope===dossierScope);
 if(!profile)return;
 const fields=profile.fields;
 const tvdbId=fields.tvdb_id?.value;
 $('dossier-tvdb').href=tvdbId?'https://thetvdb.com/dereferrer/series/'+encodeURIComponent(tvdbId):'https://thetvdb.com/search?query='+encodeURIComponent(group.name);
 $('dossier-tvdb').textContent=tvdbId?'Bestaand op TVDB · '+tvdbId+' ↗':'TVDB niet bevestigd · handmatig zoeken ↗';
 $('dossier-tvdb-status').textContent=tvdbId?'Bestaand TVDB-ID vastgelegd.':group.tvdb_check?((group.tvdb_check.error||'Controle afgerond')+' · '+clock(group.tvdb_check.checked)):'TVDB nog niet gecontroleerd. Automatische controle volgt tijdens scans.';

 const renderField=f=>{const v=fields[f.key];return `<div class="metadata-value ${v?.value?'':'not-known'}"><dt>${esc(f.label)}</dt><dd>${v?.value?esc(v.value).replaceAll('\n','<br>'):'Nog onbekend'}</dd>${v?.value?`<div class="fact-source"><span>${v.origin==='manual'?'Handmatig beoordeeld':'Automatisch voorstel'}</span>${v.source_url?`<a href="${esc(v.source_url)}" target="_blank" rel="noopener noreferrer" title="${esc(v.evidence||'Bron bekijken')}">Bron ↗</a>`:'<span>Bron ontbreekt</span>'}</div>`:''}</div>`;};
 $('dossier-metadata').innerHTML=`<div class="dossier-summary"><div>${badge(profile.status)}<h3>${esc(productionLabel(profile))}</h3><p>${profile.filled} van ${profile.total} basisvelden ingevuld. ${profile.missing.length} nog onbekend.</p></div><div class="completion-number">${profile.filled}<span>/${profile.total}</span></div></div>`+['Basis','Uitgave','Links','Aanvullend'].map(section=>`<section class="metadata-section"><h3>${section}</h3><dl class="metadata-grid">${state.dossier_fields.filter(f=>f.section===section).map(renderField).join('')}</dl></section>`).join('');
 $('dossier-people').innerHTML=`<p class="explanation">Cast en crew voor ${esc(productionLabel(profile).toLowerCase())}. Rollen die niet bevestigd zijn, blijven leeg.</p><dl class="people-grid">${state.dossier_fields.filter(f=>f.section==='Makers').map(renderField).join('')}</dl>`;
 $('dossier-productions').innerHTML=group.productions.map(p=>`<div class="production-row"><div><h3>${esc(productionLabel(p))}</h3><button class="evidence-button" data-article="${p.status_article}">Onderbouwing: ${esc(p.evidence)}</button></div><div>${badge(p.status)}</div></div>`).join('');
 $('dossier-news').innerHTML=group.articles.map(a=>newsRow(a)).join('');
 $('dossier-linked-sources').innerHTML=(group.metadata_sources||[]).filter(s=>s.scope===dossierScope).map(s=>`<p><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">Gekoppelde metadata-bron ↗</a> · ${clock(s.checked)}${s.error?' · '+esc(s.error):''}</p>`).join('');
 $('dossier-checklist').innerHTML=`<div class="checklist"><strong>Nog aan te vullen</strong><p>${profile.missing.length?profile.missing.map(k=>esc(state.dossier_fields.find(f=>f.key===k)?.label||k)).join(' · '):'De basisvelden zijn gevuld. Controleer de gegevens en bronvermeldingen.'}</p></div>`;
 $('export-text').value=exportText(group,profile);
 document.querySelectorAll('[data-dossier-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.dossierTab===dossierTab);b.setAttribute('aria-selected',String(b.dataset.dossierTab===dossierTab));});
 for(const [key,id] of Object.entries({overview:'dossier-overview',people:'dossier-people',news:'dossier-news-panel',export:'dossier-export'}))$(id).hidden=dossierTab!==key;
}
function exportText(group,profile){
 let lines=[group.name,productionLabel(profile),'Productiestatus: '+profile.status,'','INVOERDOSSIER — controleer automatische voorstellen en brongegevens.',''];
 for(const f of state.dossier_fields){const v=profile.fields[f.key];lines.push(f.label+': '+(v?.value||'ONBEKEND'));if(v?.value){lines.push('Beoordeling: '+(v.origin==='manual'?'handmatig':'automatisch voorstel'));if(v.source_url)lines.push('Bron: '+v.source_url);if(v.evidence)lines.push('Onderbouwing: '+v.evidence);}lines.push('');}
 lines.push('NIEUWSBRONNEN');group.articles.forEach(a=>lines.push(a.title+' — '+a.url));return lines.join('\n');
}
function openMetadata(){
 const group=state.series.find(g=>g.id===dossierId), profile=group?.dossiers.find(p=>p.scope===dossierScope);if(!profile)return;
 editingProfile=JSON.parse(JSON.stringify({...profile,series_id:group.id}));
 $('metadata-heading').textContent=group.name+' · '+productionLabel(profile);
 $('metadata-fields').innerHTML=['Basis','Uitgave','Makers','Links','Aanvullend'].map(section=>`<fieldset><legend>${section}</legend>${state.dossier_fields.filter(f=>f.section===section).map(f=>{const v=profile.fields[f.key]||{};return `<div class="edit-fact"><label>${esc(f.label)}<textarea data-field-value="${f.key}" rows="${['cast','synopsis','episode_guide'].includes(f.key)?4:2}" maxlength="6000">${esc(v.value||'')}</textarea></label><details><summary>Bron en onderbouwing</summary><label>Bron-URL<input data-field-source="${f.key}" type="url" value="${esc(v.source_url||'')}" maxlength="2000"></label><label>Onderbouwing<textarea data-field-evidence="${f.key}" rows="2" maxlength="600">${esc(v.evidence||'')}</textarea></label></details></div>`;}).join('')}</fieldset>`).join('');
 $('metadata-error').textContent='';$('metadata-detail').showModal();
}
function openArticle(id){
 const a=allArticles().find(a=>a.id===id);if(!a)return;
 $('article-id').value=id;$('article-title').textContent=a.title;$('article-summary').textContent=a.summary;$('article-url').href=a.url;
 $('article-evidence').textContent=`Automatische aanwijzing: ${a.evidence}. ${a.rejection||a.issue||''}`;
 $('edit-title').value=a.name||a.series_title||'';$('edit-kind').value=a.kind;$('edit-season').value=a.season??(a.kind==='Nieuwe serie'?1:'');$('edit-status').value=a.status;$('edit-notes').value=a.notes||'';$('edit-tvdb').checked=!!a.tvdb;$('edit-excluded').checked=!!a.excluded;$('article-error').textContent='';$('article-detail').showModal();
}
function renderSources(){
 $('source-list').innerHTML=state.sources.map(s=>`<article class="source-row ${s.enabled===false?'paused':''}"><div><h3>${esc(s.name)}</h3><p>${esc(s.kind)}</p><code>${esc(s.query||s.url)}</code></div><div class="source-state ${s.error&&s.enabled!==false?'bad':''}">${s.enabled===false?'Gepauzeerd':s.error?'Fout bij ophalen':s.last_success?'Bereikbaar':'Nog niet gescand'}<small>Laatste succes: ${clock(s.last_success)}</small><small>${s.error?esc(s.error):`${s.fetched||0} berichten · ${s.added||0} nieuw in laatste scan`}</small></div><button data-source="${esc(s.id)}">Wijzigen</button></article>`).join('');
}
function sourceMode(){
 const feed=$('source-mode').value==='feed';
 $('source-value-label').firstChild.textContent=feed?'Feed-URL':'Zoekopdracht';
 $('source-value').placeholder=feed?'https://pers.voorbeeld.nl/feed':'site:voorbeeld.nl ("nieuwe serie" OR opnames OR "nieuw seizoen") when:90d';
 $('source-help').textContent=feed?'Gebruik de RSS- of Atom-link, niet de gewone homepage. Alleen publieke HTTPS-adressen.':'Met site:domein.nl volg je één website. Google Nieuws moet de berichten wel indexeren. Een directe persfeed is sneller als die beschikbaar is.';
 $('source-test').textContent='';
}
function openSource(id){
 const s=state.sources.find(s=>s.id===id);
 $('source-heading').textContent=s?'Bron wijzigen':'Bron toevoegen';$('source-id').value=s?.id||'';$('source-name').value=s?.name||'';$('source-mode').value=s?.url?'feed':'search';$('source-value').value=s?.url||s?.query||'';$('source-enabled').checked=s?.enabled!==false;$('source-error').textContent='';sourceMode();$('source-detail').showModal();
}
function sourceData(){return {id:$('source-id').value||undefined,name:$('source-name').value,mode:$('source-mode').value,value:$('source-value').value,enabled:$('source-enabled').checked};}
function setView(value){
 view=value;for(const name of ['series','review','sources'])$(name+'-view').hidden=name!==view;
 document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-current',b.dataset.view===view?'page':'false');});
 $('page-title').textContent={series:'Series',review:'Te beoordelen',sources:'Bronnen'}[view];
 $('page-description').textContent={series:'Nieuwe producties en seizoenen. Nieuws gebundeld per titel.',review:'Controleer onduidelijke berichten voordat ze in het serieoverzicht verschijnen.',sources:'Beheer welke persfeeds en websites je volgt.'}[view];
}
async function scanNow(){await request('/api/scan',{});$('notice').textContent='Scan aangevraagd. Het overzicht wordt automatisch bijgewerkt.';setTimeout(load,600);}
$('scan').onclick=async()=>{try{$('scan').disabled=true;await scanNow();}catch(e){$('error').textContent=e.message;$('error').hidden=false;$('scan').disabled=false;}};
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.view)setView(b.dataset.view);if(b.dataset.close)$(b.dataset.close).close();if(b.dataset.series){dossierId=b.dataset.series;dossierScope='';dossierTab='overview';renderDossier();$('series-detail').showModal();}if(b.dataset.dossierTab){dossierTab=b.dataset.dossierTab;renderDossier();}if(b.dataset.article)openArticle(b.dataset.article);if(b.dataset.source)openSource(b.dataset.source);});
for(const id of ['search','kind-filter','status-filter','sort'])$(id).addEventListener('input',renderSeries);
for(const id of ['review-search','review-selection'])$(id).addEventListener('input',renderReview);
$('edit-kind').onchange=()=>{if($('edit-kind').value==='Nieuwe serie')$('edit-season').value=1;else if($('edit-season').value==='1')$('edit-season').value='';};
$('article-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{await request('/api/article',{id:$('article-id').value,series_title:$('edit-title').value,phase:$('edit-status').value,production_kind:$('edit-kind').value,season_number:$('edit-season').value?Number($('edit-season').value):null,notes:$('edit-notes').value,tvdb:Number($('edit-tvdb').checked),excluded:Number($('edit-excluded').checked)});$('article-detail').close();$('notice').textContent='Beoordeling opgeslagen.';await load();}catch(e){$('article-error').textContent=e.message;}finally{e.submitter.disabled=false;}};
$('source-mode').onchange=sourceMode;
$('source-value').oninput=()=>$('source-test').textContent='';
$('add-source').onclick=()=>openSource();
$('test-source').onclick=async()=>{const b=$('test-source');b.disabled=true;$('source-test').textContent='Bron testen…';$('source-error').textContent='';try{const result=await request('/api/source/test',sourceData());$('source-test').innerHTML=`${result.count} berichten opgehaald.${result.count?' Voorbeelden:':' De feed is bereikbaar, maar leeg.'}<ul>${result.examples.map(t=>`<li>${esc(t)}</li>`).join('')}</ul>`;}catch(e){$('source-test').textContent='';$('source-error').textContent=e.message;}finally{b.disabled=false;}};
$('source-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{await request('/api/source',sourceData());$('source-detail').close();$('notice').textContent='Bron opgeslagen. Actieve bronnen gaan mee in de volgende scan.';await load();}catch(e){$('source-error').textContent=e.message;}finally{e.submitter.disabled=false;}};
$('status-filter').innerHTML+=phases.map(p=>`<option>${p}</option>`).join('');$('edit-status').innerHTML=phases.map(p=>`<option>${p}</option>`).join('');$('edit-kind').innerHTML=kinds.map(p=>`<option>${p}</option>`).join('');
if(document.modelContext?.registerTool){
 const lifecycle=new AbortController();
 try{Promise.resolve(document.modelContext.registerTool({name:'filter_series',description:'Filter het zichtbare serieoverzicht op titel en type productie; wijzigt geen opgeslagen gegevens.',inputSchema:{type:'object',properties:{query:{type:'string'},kind:{type:'string',enum:['','Nieuwe serie','Nieuw seizoen']}},required:['query','kind'],additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute(input){if(typeof input?.query!=='string'||!['','Nieuwe serie','Nieuw seizoen'].includes(input.kind))throw new Error('Ongeldige filters');setView('series');$('search').value=input.query;$('kind-filter').value=input.kind;$('status-filter').value='';renderSeries();return {result:$('catalog-count').textContent};}},{signal:lifecycle.signal})).catch(()=>{});}catch{}
 window.addEventListener('pagehide',()=>lifecycle.abort(),{once:true});
}
$('dossier-scope').onchange=()=>{dossierScope=$('dossier-scope').value;$('import-status').textContent='';$('export-status').textContent='';renderDossier();};
$('edit-dossier').onclick=openMetadata;
$('metadata-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{const fields={};for(const f of state.dossier_fields){const key=f.key, value=document.querySelector(`[data-field-value="${key}"]`).value,source_url=document.querySelector(`[data-field-source="${key}"]`).value,evidence=document.querySelector(`[data-field-evidence="${key}"]`).value;const old=editingProfile.fields[key]||{};if(value!==(old.value||'')||source_url!==(old.source_url||'')||evidence!==(old.evidence||''))fields[key]={value,source_url,evidence};}await request('/api/dossier',{series_id:editingProfile.series_id,scope:editingProfile.scope,revision:editingProfile.revision,fields});$('metadata-detail').close();await load();}catch(e){$('metadata-error').textContent=e.message;}finally{e.submitter.disabled=false;}};
$('import-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;const scope=dossierScope,series_id=dossierId;$('import-status').textContent='Bron uitlezen…';try{const r=await request('/api/dossier/import',{series_id,scope,url:$('import-url').value});$('import-status').textContent=r.found?r.found+' velden gevonden. Bekijk en controleer de voorstellen.':'Geen expliciete metadata gevonden. Je kunt de gegevens handmatig aanvullen.';await load();}catch(e){$('import-status').textContent=e.message;}finally{e.submitter.disabled=false;}};
$('copy-dossier').onclick=async()=>{try{await navigator.clipboard.writeText($('export-text').value);$('export-status').textContent='Gekopieerd.';}catch{$('export-text').focus();$('export-text').select();$('export-status').textContent='Selectie klaar. Kopieer met Ctrl+C.';}};
$('download-dossier').onclick=()=>{const g=state.series.find(g=>g.id===dossierId),p=g?.dossiers.find(p=>p.scope===dossierScope);if(!p)return;const url=URL.createObjectURL(new Blob([JSON.stringify({title:g.name,...p,news_sources:g.articles.map(a=>({title:a.title,url:a.url}))},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=g.name.replace(/[^a-z0-9]/gi,'-')+'-'+p.scope.replace(':','-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
load();setInterval(load,10000);

$('check-tvdb').onclick=async e=>{e.target.disabled=true;try{await request('/api/dossier/check-tvdb',{series_id:dossierId,scope:dossierScope});await load();}catch(e){$('dossier-tvdb-status').textContent=e.message;}finally{e.target.disabled=false;}};
