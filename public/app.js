const $ = id => document.getElementById(id);
const isAdmin = /^\/admin\/?$/.test(location.pathname);
document.body.classList.toggle('admin-mode',isAdmin);
$('access-link').href=isAdmin?'/':'/admin';
$('access-link').textContent=isAdmin?'Openbare website ↗':'Beheer →';
if(isAdmin)document.querySelector('.edition').textContent='Beheeromgeving';
const phases = ['Onbekend','Aangekondigd','Release gepland','In productie','Geproduceerd','Beschikbaar'];
const kinds = ['Onbekend','Nieuwe serie','Nieuw seizoen'];
let state = {series:[],inbox:[],ignored:[],sources:[],meta:{}}, view='series', dossierId=null, loading=false, stateRevision=null, polling=false, dossierScope='', dossierTab='overview', editingProfile=null;
let dossierGroup=null, detailRevision=null, detailRequest=0, reviewRequest=0;
const findGroup = id => dossierGroup?.id===id?dossierGroup:state.series.find(g=>g.id===id);
const showError = e => {$('error').textContent=e.message;$('error').hidden=false;};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const searchKey = value => String(value??'').normalize('NFKD').toLocaleLowerCase('nl').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const date = s => s ? new Date(s).toLocaleString('nl-NL',{day:'numeric',month:'short',year:'numeric'}) : 'Datum onbekend';
const clock = s => s ? new Date(s).toLocaleString('nl-NL',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : 'Nog niet';
const badge = (status,label=status) => `<span class="status ${{'Aangekondigd':'announced','Release gepland':'announced','In productie':'production','Geproduceerd':'complete','Beschikbaar':'available','Onbekend':'unknown'}[status]||'unknown'}">${esc(label)}</span>`;
const productionLabel = p => p.kind==='Onbekend'?'Seizoen niet vastgesteld':p.kind==='Nieuwe serie'?'Nieuwe serie · seizoen 1':`Nieuw seizoen · ${p.season ? 'seizoen '+p.season:'nummer onbekend'}`;
const productionStatusLabel = p => p.kind==='Nieuw seizoen'&&p.status==='Aangekondigd'?(p.season?`Seizoen ${p.season} aangekondigd`:'Vervolg aangekondigd'):p.status;
const allArticles = () => [...state.inbox,...state.ignored,...(dossierGroup?.articles||[])];
async function request(path,data){
 if(data&&!isAdmin)throw new Error('Open Beheer om wijzigingen te maken.');
 const response = await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json','X-Radar-Request':'1'},body:JSON.stringify(data)}:{});
 let result; try {result=await response.json();} catch {throw new Error('De server gaf geen geldig antwoord.');}
 if(!response.ok) throw new Error(result.error||`Verzoek mislukt (${response.status}).`);
 return result;
}
async function load(){
 if(loading)return; loading=true;
 try {
  state=await request((isAdmin?'/api/admin/dashboard':'/api/dashboard')+'?summary=1');stateRevision=state.revision;$('error').hidden=true;render();
  if(view==='review')await loadReview();
  if($('series-detail').open)await loadDossier();
 }
 catch(e){showError(e);}
 finally{loading=false;}
}
async function loadReview(){
 if(!isAdmin)return;
 const token=++reviewRequest;
 $('review-list').textContent='Berichten laden…';
 try{const result=await request('/api/admin/review');if(token!==reviewRequest)return;state.inbox=result.inbox;state.ignored=result.ignored;renderReview();}
 catch(e){if(token===reviewRequest)$('review-list').textContent='Berichten konden niet worden geladen.';throw e;}
}
async function loadDossier(){
 const id=dossierId,token=++detailRequest;
 if(!id)return false;
 if(!state.series.some(g=>g.id===id)){$('series-detail').close();dossierGroup=null;return false;}
 const group=await request((isAdmin?'/api/admin/series/':'/api/series/')+encodeURIComponent(id));
 if(token!==detailRequest||id!==dossierId)return false;
 dossierGroup=group;
 if(!$('article-detail').open&&!$('metadata-detail').open)renderDossier();
 return true;
}
async function openDossier(button){
 dossierId=button.dataset.series;dossierScope=button.dataset.scope||'';dossierTab='overview';
 button.disabled=true;
 try{if(await loadDossier())$('series-detail').showModal();}
 catch(e){showError(e);}
 finally{button.disabled=false;}
}
function renderScanStatus(){
 $('app-version').textContent='SeriesRadar'+(state.version?' v'+state.version:'');
 $('review-count').textContent=state.counts?.inbox??state.inbox.length;
 const failures=state.sources.filter(s=>s.enabled!==false&&s.error).length;
 $('scan-status').textContent=state.scanning?'Scan bezig…':`Laatste scan: ${clock(state.meta.last_finished)}${failures?' · '+failures+' bron(nen) met een fout':''}`;
 $('next-scan').textContent=state.scanning?'':state.meta.next_scan?`Volgende scan: ${clock(Number(state.meta.next_scan)*1000)}`:`Interval: ${Math.round((state.interval||1800)/60)} minuten`;
 $('scan').disabled=state.scanning;
}
async function poll(){
 if(document.hidden||polling||loading)return;polling=true;
 try{
  const status=await request(isAdmin?'/api/admin/status':'/api/status');state.meta=status.meta;state.scanning=status.scanning;renderScanStatus();
  if(!status.scanning){
   if(stateRevision===null||status.revision!==stateRevision)await load();
   else if($('series-detail').open&&status.detail_revision!==detailRevision)await loadDossier();
   detailRevision=status.detail_revision;
  }
 }
 catch(e){$('error').textContent=e.message;$('error').hidden=false;}
 finally{polling=false;}
}
function render(){
 renderScanStatus();
 $('known-titles').innerHTML=state.series.map(g=>`<option value="${esc(g.name)}"></option>`).join('');
 renderSeries(); renderReview(); renderSources();
 if($('series-detail').open&&!$('article-detail').open&&!$('metadata-detail').open)renderDossier();
}
function renderSeries(){
 const terms=searchKey($('search').value).split(' ').filter(Boolean),kind=$('kind-filter').value,status=$('status-filter').value;
 let groups=state.series.map(g=>({...g,visibleProductions:g.productions.filter(p=>(!kind||p.kind===kind)&&(!status||p.status===status))})).filter(g=>{const text=searchKey(`${g.name} ${g.search_text}`);return g.visibleProductions.length&&terms.every(term=>text.includes(term));});
 if($('sort').value==='title')groups.sort((a,b)=>a.name.localeCompare(b.name,'nl'));
 else groups.sort((a,b)=>Date.parse(b.updated||0)-Date.parse(a.updated||0));
 $('catalog-count').textContent=`${groups.length} ${groups.length===1?'serie':'series'} · ${groups.reduce((n,g)=>n+g.article_count,0)} nieuwsartikelen`;
 $('series-empty').hidden=groups.length>0;
 $('series-list').innerHTML=groups.map(g=>{
 const p=g.visibleProductions.find(p=>p.articles.includes(g.latest_news?.article_id))||g.visibleProductions[0],d=(g.dossiers||[]).find(d=>d.kind===p.kind&&d.season===p.season)||g.dossiers?.[0], f=d?.fields||{};
 const castCount=d?.cast_count||0, network=f.platforms?.value||f.networks?.value||'Platform nog onbekend';
 return `<article class="series-card"><div class="card-top"><span class="title-mark">${esc(g.name.slice(0,2).toUpperCase())}</span>${badge(p.status,productionStatusLabel(p))}</div><button class="series-name" data-series="${g.id}" data-scope="${esc(d?.scope||'')}">${esc(g.name)}</button><div class="card-type">${esc(productionLabel(p))}${g.visibleProductions.length>1?' + '+(g.visibleProductions.length-1)+' producties':''}</div><div class="card-network">${esc(network.replaceAll('\n',' · '))}</div>${f.release_date?.value?`<div class="card-type">Uitzending: ${esc(f.release_date.value)}</div>`:''}<div class="card-latest" title="${esc(g.latest_news?.title||'')}"><strong>Laatste nieuws</strong> ${esc(g.latest_news?.title||'')}</div><div class="card-people"><span>${castCount?castCount+' castleden':'Cast nog niet ingevuld'}</span><span>${g.article_count} artikelen</span></div><div class="card-progress"><span>Dossier</span><strong>${d?.filled||0} / ${d?.total||11} basisvelden</strong></div><progress max="${d?.total||11}" value="${d?.filled||0}" aria-label="Ingevulde basisvelden"></progress><div class="card-bottom"><span>${date(g.updated)}</span><button class="text-button" data-series="${g.id}" data-scope="${esc(d?.scope||'')}">Dossier openen ↗</button></div></article>`;
 }).join('');
}
function newsRow(a,reason=false){return `<article class="news-row"><div class="news-meta"><span>${esc(a.publisher)}</span><span>${date(a.published)}</span>${a.classification_reviewed?'<span>Beoordeeld</span>':''}${a.tvdb?'<span>TVDB verwerkt</span>':''}</div><h3>${esc(a.title)}</h3>${reason?`<p>${esc(a.rejection||a.issue)}</p>`:`<p>${esc(productionLabel({kind:a.kind,season:a.season}))} · ${esc(a.status)}</p>`}<p class="explanation">Eerste vondst: ${clock(a.discovered)}${a.retrieval?.feed_checked?' · Feed gecontroleerd: '+clock(a.retrieval.feed_checked):''}${a.retrieval?.last_success?' · Artikel laatst gelezen: '+clock(a.retrieval.last_success):''} · ${a.retrieval?.status==='read'?'Volledige bron gelezen':a.retrieval?.status==='failed'?'Volledige bron niet opgehaald · poging: '+clock(a.retrieval.attempted):'Alleen feedfragment; artikel nog niet gelezen'}</p><div class="news-actions"><a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">Bronbericht ↗</a><button class="text-button admin-only" data-article="${a.id}">Beoordelen / koppelen</button></div></article>`;}
function renderReview(){
 const query=$('review-search').value.toLowerCase(),selected=$('review-selection').value;
 const rows=state[selected].filter(a=>!query||`${a.title} ${a.publisher}`.toLowerCase().includes(query));
 $('review-list').innerHTML=rows.length?rows.map(a=>newsRow(a,true)).join(''):'<div class="empty">Geen berichten in deze selectie.</div>';
}
function renderDossier(){
 const group=dossierGroup;
 if(!group||group.id!==dossierId)return;
 if(!state.series.some(g=>g.id===dossierId)){$('series-detail').close();return;}
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
 const run=group.ai_runs?.find(r=>r.scope===dossierScope);
 if($('research-detail').open&&researchContext?.series_id===group.id){const externalRun=group.ai_runs?.find(r=>r.scope===researchContext.scope&&r.method==='external');if(externalRun){$('research-import-status').textContent=externalRun.message+' · '+clock(externalRun.checked);renderResearchReport(externalRun);}}
 $('enrich-dossier').disabled=!!state.scanning;
 const enrichment=group.metadata_enrichment,discovery=group.metadata_discovery;
 $('enrich-status').textContent=state.scanning?'Bronnen worden gecontroleerd…':enrichment?`${enrichment.error||'Gerichte aanvulling afgerond. Gevonden voorstellen staan in het dossier.'} · ${clock(enrichment.checked)}${discovery?.error?' · Zoekbron: '+discovery.error:''}`:'Automatisch aanvullen zoekt gericht naar ontbrekende seriegegevens en leest gekoppelde artikelen. Zonder AI- of API-kosten.';
 $('research-status').textContent=run?`${run.message} · ${clock(run.checked)}`:'Maak een opdracht, plak die in je eigen chat en plak het JSON-antwoord terug. De site controleert de bronnen; een API-sleutel is niet nodig.';
 const tvdbId=fields.tvdb_id?.value;
 $('dossier-tvdb').href=tvdbId?'https://thetvdb.com/dereferrer/series/'+encodeURIComponent(tvdbId):'https://thetvdb.com/search?query='+encodeURIComponent(group.name);
 $('dossier-tvdb').textContent=tvdbId?'Bestaand op TVDB · '+tvdbId+' ↗':'TVDB niet bevestigd · handmatig zoeken ↗';
 $('dossier-tvdb-status').textContent=tvdbId?'Bestaand TVDB-ID vastgelegd.':group.tvdb_check?((group.tvdb_check.error||'Controle afgerond')+' · '+clock(group.tvdb_check.checked)):'TVDB nog niet gecontroleerd. Automatische controle volgt tijdens scans.';

 const renderField=f=>{const v=fields[f.key];const sources=v?.sources?.length?v.sources:v?.source_url?[v]:[];return `<div class="metadata-value ${v?.value?'':'not-known'}"><dt>${esc(f.label)}</dt><dd>${v?.value?esc(v.value).replaceAll('\n','<br>'):'Nog onbekend'}</dd>${v?.value?`<div class="fact-source"><span>${v.origin==='manual'?'Handmatig beoordeeld':v.origin==='tvmaze'?'TVmaze · CC BY-SA':['ai','external_ai'].includes(v.origin)?'AI-voorstel · inhoud controleren':'Automatisch voorstel'}</span>${v.checked?`<span>Bron gelezen: ${clock(v.checked)}</span>`:''}${sources.length?sources.map((s,i)=>`<a href="${esc(s.source_url)}" target="_blank" rel="noopener noreferrer" title="${esc(s.evidence||'Bron bekijken')}">Bron${sources.length>1?' '+(i+1):''} ↗</a>`).join(' '):'<span>Bron ontbreekt</span>'}</div>`:''}</div>`;};
 $('dossier-metadata').innerHTML=`<div class="dossier-summary"><div>${badge(profile.status,productionStatusLabel(profile))}<h3>${esc(productionLabel(profile))}</h3><p>${profile.filled} van ${profile.total} basisvelden ingevuld. ${profile.missing.length} nog onbekend.</p></div><div class="completion-number">${profile.filled}<span>/${profile.total}</span></div></div>`+['Basis','Uitgave','Links','Aanvullend'].map(section=>`<section class="metadata-section"><h3>${section}</h3><dl class="metadata-grid">${state.dossier_fields.filter(f=>f.section===section).map(renderField).join('')}</dl></section>`).join('');
 $('dossier-people').innerHTML=`<p class="explanation">Cast en crew voor ${esc(productionLabel(profile).toLowerCase())}. Rollen die niet bevestigd zijn, blijven leeg.</p><dl class="people-grid">${state.dossier_fields.filter(f=>f.section==='Makers').map(renderField).join('')}</dl>`;
 $('dossier-productions').innerHTML=group.productions.map(p=>`<div class="production-row"><div><h3>${esc(productionLabel(p))}</h3>${isAdmin?`<button class="evidence-button" data-article="${p.status_article}">Onderbouwing: ${esc(p.evidence)}</button>`:`<p>Onderbouwing: ${esc(p.evidence)}</p>`}</div><div>${badge(p.status,productionStatusLabel(p))}</div></div>`).join('');
 $('dossier-news').innerHTML=group.articles.map(a=>newsRow(a)).join('');
 $('dossier-linked-sources').innerHTML=(group.metadata_sources||[]).filter(s=>s.scope===dossierScope).map(s=>`<p><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">Gekoppelde metadata-bron ↗</a> · Laatst gelezen: ${clock(s.last_success)} · Laatste poging: ${clock(s.checked)} · ${s.error||s.status==='failed'?'Ophalen mislukt':'Bron gelezen'}</p>`).join('');
 $('dossier-checklist').innerHTML=`<div class="checklist"><strong>Nog aan te vullen</strong><p>${profile.missing.length?profile.missing.map(k=>esc(state.dossier_fields.find(f=>f.key===k)?.label||k)).join(' · '):'De basisvelden zijn gevuld. Controleer de gegevens en bronvermeldingen.'}</p></div>`;
 $('export-text').value=exportText(group,profile);
 $('export-checks').textContent=`${profile.filled} van ${profile.total} basisvelden ingevuld. Controleer de bronnen, het seizoen en de credits per aflevering voordat je gegevens indient. Een gevuld dossier is geen goedkeuring door TVDB of IMDb.`;
 document.querySelectorAll('[data-dossier-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.dossierTab===dossierTab);b.setAttribute('aria-selected',String(b.dataset.dossierTab===dossierTab));});
 for(const [key,id] of Object.entries({overview:'dossier-overview',people:'dossier-people',news:'dossier-news-panel',export:'dossier-export'}))$(id).hidden=dossierTab!==key;
}
function exportText(group,profile){
 const target=$('export-target').value;
 let lines=[group.name,productionLabel(profile),'Productiestatus: '+profile.status,'','Invoerhulp voor '+({both:'TVDB en IMDb',tvdb:'TVDB',imdb:'IMDb'}[target])+'. Controleer ieder gegeven bij de bron.',''];
 if(target!=='imdb')lines.push('TVDB: controleer eerst of de serie al bestaat. Houd uitzending, seizoen en specials apart. Controleer of acteurs in minstens de helft van de afleveringen voorkomen voordat je ze als seriecast toevoegt. Een persbericht bewijst dat niet.', 'Richtlijnen: https://support.thetvdb.com/kb/faq.php?cid=4','');
 if(target!=='tvdb')lines.push('IMDb: controleer titel, jaar en type. Voeg cast en crew toe bij de afleveringen waarvoor de credits bevestigd zijn. Een seizoenscredit bewijst niet dat iemand aan alle afleveringen meewerkt. Geef directe bronlinks mee.', 'Richtlijnen: https://help.imdb.com/article/contribution/filmography-credits/filmography-faqs/GXXHC234LLGMKTEE','');
 for(const f of state.dossier_fields.filter(f=>f.key!=='notes')){const v=profile.fields[f.key];lines.push(f.label+': '+(v?.value||'ONBEKEND'));if(v?.value){lines.push('Controle: '+(v.origin==='manual'?'door beheerder beoordeeld':'bronvoorstel; nog zelf beoordelen'));const sources=v.sources?.length?v.sources:[v];for(const s of sources){if(s.source_url)lines.push('Bron: '+s.source_url);if(s.evidence)lines.push('Onderbouwing: '+s.evidence);}if(v.license_url)lines.push('Bronlicentie: '+v.license_url);}lines.push('');}
 lines.push('NIEUWSBRONNEN');group.articles.forEach(a=>lines.push(a.title+' — '+a.url));return lines.join('\n');
}
function openMetadata(target){
 const group=findGroup(target?.series_id||dossierId), profile=group?.dossiers.find(p=>p.scope===(target?.scope||dossierScope));if(!profile?.fields)return;
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
 if(value==='review')loadReview().catch(showError);
}
async function scanNow(){await request('/api/scan',{});$('notice').textContent='Scan aangevraagd. Het overzicht wordt automatisch bijgewerkt.';setTimeout(load,600);}
$('scan').onclick=async()=>{try{$('scan').disabled=true;await scanNow();}catch(e){$('error').textContent=e.message;$('error').hidden=false;$('scan').disabled=false;}};
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.view)setView(b.dataset.view);if(b.dataset.close)$(b.dataset.close).close();if(b.dataset.series)openDossier(b);if(b.dataset.dossierTab){dossierTab=b.dataset.dossierTab;renderDossier();}if(b.dataset.article)openArticle(b.dataset.article);if(b.dataset.source)openSource(b.dataset.source);});
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
$('metadata-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{const fields={};for(const f of state.dossier_fields){const key=f.key, value=document.querySelector(`[data-field-value="${key}"]`).value,source_url=document.querySelector(`[data-field-source="${key}"]`).value,evidence=document.querySelector(`[data-field-evidence="${key}"]`).value;const old=editingProfile.fields[key]||{};if(key===editingProfile.forceField||value!==(old.value||'')||source_url!==(old.source_url||'')||evidence!==(old.evidence||''))fields[key]={value,source_url,evidence};}await request('/api/dossier',{series_id:editingProfile.series_id,scope:editingProfile.scope,revision:editingProfile.revision,fields});$('metadata-detail').close();await load();}catch(e){$('metadata-error').textContent=e.message;}finally{e.submitter.disabled=false;}};
$('import-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;const scope=dossierScope,series_id=dossierId;$('import-status').textContent='Bron uitlezen…';try{const r=await request('/api/dossier/import',{series_id,scope,url:$('import-url').value});$('import-status').textContent=r.found?r.found+' velden gevonden. Bekijk en controleer de voorstellen.':'Geen expliciete metadata gevonden. Je kunt de gegevens handmatig aanvullen.';await load();}catch(e){$('import-status').textContent=e.message;}finally{e.submitter.disabled=false;}};
$('copy-dossier').onclick=async()=>{try{await navigator.clipboard.writeText($('export-text').value);$('export-status').textContent='Gekopieerd.';}catch{$('export-text').focus();$('export-text').select();$('export-status').textContent='Selectie klaar. Kopieer met Ctrl+C.';}};
$('export-target').onchange=()=>{const group=findGroup(dossierId),profile=group?.dossiers.find(p=>p.scope===dossierScope);if(profile)$('export-text').value=exportText(group,profile);};
$('download-dossier').onclick=()=>{const g=findGroup(dossierId),p=g?.dossiers.find(p=>p.scope===dossierScope);if(!p)return;const url=URL.createObjectURL(new Blob([JSON.stringify({title:g.name,...p,fields:Object.fromEntries(Object.entries(p.fields).filter(([key])=>key!=='notes')),news_sources:g.articles.map(a=>({title:a.title,url:a.url}))},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=g.name.replace(/[^a-z0-9]/gi,'-')+'-'+p.scope.replace(':','-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
load();setInterval(poll,10000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});

$('check-tvdb').onclick=async e=>{e.target.disabled=true;try{await request('/api/dossier/check-tvdb',{series_id:dossierId,scope:dossierScope});await load();}catch(e){$('dossier-tvdb-status').textContent=e.message;}finally{e.target.disabled=false;}};

$('enrich-dossier').onclick=async e=>{e.target.disabled=true;try{const result=await request('/api/dossier/enrich',{series_id:dossierId,scope:dossierScope});await load();$('enrich-status').textContent=result.message;}catch(err){$('enrich-status').textContent=err.message;e.target.disabled=false;}};

let researchContext=null;
function renderResearchReport(run){
 const panel=$('research-report');
 if(!run||run.status==='running'){panel.textContent='';return;}
 if(!run.report){panel.innerHTML='<p>Bij deze oudere import zijn de redenen en niet-bevestigde voorstellen niet bewaard. Plak hetzelfde JSON-antwoord opnieuw om een rapport per veld te krijgen; bestaande gegevens blijven behouden.</p>';return;}
 const rows=[...run.report].sort((a,b)=>(a.status==='confirmed')-(b.status==='confirmed'));
 panel.innerHTML='<h3>Controle per veld</h3><p>Afwijkingen, onbekende gegevens en synopsisconcepten blijven hier staan. Bekijk de bron en kies Beoordelen om een bruikbaar voorstel zelf over te nemen.</p>'+rows.map((r,i)=>`<article class="news-row"><h4>${esc(state.dossier_fields.find(f=>f.key===r.field)?.label||r.field)} · ${r.status==='confirmed'?'Bron en waarde gecontroleerd':r.code==='not_found'?'Niet gevonden':'Zelf beoordelen'}</h4><p>${esc(r.reason)}</p><details><summary>Voorstel en citaat bekijken</summary><p>${esc(r.value).replaceAll('\n','<br>')}</p><blockquote>${esc(r.evidence)}</blockquote></details>${/^https?:\/\//i.test(r.source_url)?`<a href="${esc(r.source_url)}" target="_blank" rel="noopener noreferrer">Bron bekijken ↗</a>`:''}${r.code!=='invalid'&&r.code!=='not_found'&&r.value&&state.dossier_fields.some(f=>f.key===r.field&&f.key!=='notes')?` <button type="button" data-review-proposal="${i}">Beoordelen / overnemen</button>`:''}</article>`).join('');
 panel.querySelectorAll('[data-review-proposal]').forEach(button=>button.onclick=()=>{
  if(!researchContext)return;
  const group=findGroup(researchContext.series_id),profile=group?.dossiers.find(p=>p.scope===researchContext.scope);
  if(!profile)return;
  const proposal=rows[Number(button.dataset.reviewProposal)];
  openMetadata(researchContext);
  editingProfile.forceField=proposal.field;
  document.querySelector(`[data-field-value="${proposal.field}"]`).value=proposal.value;
  document.querySelector(`[data-field-source="${proposal.field}"]`).value=proposal.source_url;
  document.querySelector(`[data-field-evidence="${proposal.field}"]`).value=proposal.evidence;
  $('metadata-error').textContent='Controleer dit voorstel en de bron. Dossier opslaan bevestigt het als handmatig gegeven.';
 });
}
async function submitResearch(result){
 const response=await request('/api/dossier/research-import',result);
 await load();return response;
}
function researchOptions(){return {mode:$('research-mode').value,target:$('research-target').value,brief:$('research-brief').value};}
async function updateResearchPrompt(){
 researchContext=await request('/api/dossier/research-package',{series_id:dossierId,scope:dossierScope,options:researchOptions()});
 $('research-prompt').value=researchContext.prompt;
}
$('research-options').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{await updateResearchPrompt();$('research-import-feedback').textContent='Opdracht bijgewerkt. Kopieer de volledige tekst naar je chat.';}catch(err){$('research-import-feedback').textContent=err.message;}finally{e.submitter.disabled=false;}};
$('research-external').onclick=async e=>{
 e.target.disabled=true;
 try{
  await updateResearchPrompt();
  const selectedProfile=findGroup(researchContext.series_id)?.dossiers.find(p=>p.scope===researchContext.scope);
  $('research-context').textContent=researchContext.title+(selectedProfile?' · '+productionLabel(selectedProfile):'');
  $('research-prompt').value=researchContext.prompt;$('research-result').value='';
  $('research-import-status').textContent=researchContext.research_status?.method==='external'?researchContext.research_status.message:'';
  renderResearchReport(researchContext.research_status?.method==='external'?researchContext.research_status:null);
  $('research-import-feedback').textContent='Plak het JSON-antwoord en klik op Geplakt resultaat toepassen. Hiervoor zijn geen API-credits nodig.';
  $('research-tools-status').textContent=typeof document.modelContext?.registerTool==='function'?'Deze browser ondersteunt websitefuncties; beschikbaarheid hangt ook af van je gekozen model en account.':'Deze browser biedt geen websitefuncties. De kopieer/import-route werkt wel.';
  $('research-detail').showModal();
 }catch(err){$('research-status').textContent=err.message;}finally{e.target.disabled=false;}
};
$('copy-research').onclick=async()=>{
 try{await navigator.clipboard.writeText($('research-prompt').value);$('research-import-feedback').textContent='Opdracht gekopieerd. Plak deze in je ChatGPT-chat.';}
 catch{$('research-prompt').focus();$('research-prompt').select();$('research-import-feedback').textContent='Kopieer de geselecteerde opdracht met Ctrl+C.';}
};
$('research-import-form').onsubmit=async e=>{
 e.preventDefault();e.submitter.disabled=true;$('research-import-feedback').textContent='Geplakt antwoord controleren…';
 try{
  if(!researchContext)throw new Error('Open de onderzoeksopdracht opnieuw.');
  const response=await submitResearch({series_id:researchContext.series_id,scope:researchContext.scope,raw:$('research-result').value});$('research-import-feedback').textContent='Antwoord ontvangen. Elk veld wordt apart gecontroleerd; een fout in één veld blokkeert de andere voorstellen niet.';$('research-import-status').textContent=response.message;renderResearchReport({status:'running'});
 }catch(err){$('research-import-feedback').textContent=err.message;}finally{e.submitter.disabled=false;}
};

if(isAdmin&&typeof document.modelContext?.registerTool==='function'){
 const targetSchema={type:'object',properties:{series_id:{type:'string'},scope:{type:'string'}},required:['series_id','scope'],additionalProperties:false};
 const optionsSchema={type:'object',properties:{mode:{type:'string',enum:['missing','all','verify']},target:{type:'string',enum:['both','tvdb','imdb']},brief:{type:'string',maxLength:2000}},additionalProperties:false};
 const factSchema={type:'object',properties:{field:{type:'string'},value:{type:'string'},source_url:{type:'string'},evidence:{type:'string'}},required:['field','value','source_url','evidence'],additionalProperties:false};
 const researchTools=[
  {name:'list_research_dossiers',description:'Lees beschikbare SeriesRadar-seriedossiers en productie/seizoen-IDs. Geeft ook het geselecteerde dossier terug. Geen wijzigingen.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute:async()=>{await load();return {selected:{series_id:dossierId,scope:dossierScope},series:state.series.map(g=>({series_id:g.id,title:g.name,productions:g.dossiers.map(p=>({scope:p.scope,kind:p.kind,season:p.season}))}))};}},
  {name:'get_research_dossier',description:'Lees de onderzoeksopdracht, bronlinks en actuele onderzoeksstatus voor één productie. Kies met options ontbrekende velden, volledig onderzoek of controle; geef target tvdb/imdb/both en extra aanwijzingen in brief. Intern notitieveld en inloggegevens worden niet gedeeld. Lees opnieuw om de broncontrole te volgen.',inputSchema:{...targetSchema,properties:{...targetSchema.properties,options:optionsSchema}},annotations:{readOnlyHint:true,untrustedContentHint:true},execute:async input=>request('/api/dossier/research-package',input)},
  {name:'submit_research_result',description:'Sla brononderbouwde voorstellen op na toestemming van de gebruiker. Neem schema_version en dossier_revision uit de opdracht over. De server controleert pagina, citaat, waarde en seizoen zonder OpenAI API. Afwijkingen, synopsissen en onzekere relaties blijven ter beoordeling. Handmatige waarden blijven behouden. Een running-antwoord is geen voltooiing: controleer daarna get_research_dossier.',inputSchema:{type:'object',properties:{...targetSchema.properties,title:{type:'string'},schema_version:{type:'integer',enum:[2]},dossier_revision:{type:'integer',minimum:0},facts:{type:'array',minItems:0,maxItems:60,items:factSchema},unanswered:{type:'array',maxItems:30,items:{type:'object',properties:{field:{type:'string'},reason:{type:'string'}},required:['field','reason'],additionalProperties:false}}},required:['series_id','scope','title','facts'],additionalProperties:false},annotations:{readOnlyHint:false,destructiveHint:false,untrustedContentHint:true},execute:submitResearch}
 ];
 for(const tool of researchTools){try{Promise.resolve(document.modelContext.registerTool(tool)).catch(()=>{});}catch{}}
}
