const $ = id => document.getElementById(id);
const phases = ['Onbekend','Aangekondigd','In productie','Geproduceerd','Beschikbaar'];
const kinds = ['Onbekend','Nieuwe serie','Nieuw seizoen'];
let state = {series:[],inbox:[],ignored:[],sources:[],meta:{}}, view='series', dossierId=null, loading=false;
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
 if($('series-detail').open&&!$('article-detail').open)renderDossier();
}
function renderSeries(){
 const query=$('search').value.toLocaleLowerCase('nl'),kind=$('kind-filter').value,status=$('status-filter').value;
 let groups=state.series.map(g=>({...g,visibleProductions:g.productions.filter(p=>(!kind||p.kind===kind)&&(!status||p.status===status))})).filter(g=>g.visibleProductions.length&&(!query||`${g.name} ${g.articles.map(a=>a.title+' '+a.publisher).join(' ')}`.toLocaleLowerCase('nl').includes(query)));
 if($('sort').value==='title')groups.sort((a,b)=>a.name.localeCompare(b.name,'nl'));
 $('catalog-count').textContent=`${groups.length} ${groups.length===1?'serie':'series'} · ${groups.reduce((n,g)=>n+g.articles.length,0)} nieuwsartikelen`;
 $('series-empty').hidden=groups.length>0;
 $('series-list').innerHTML=groups.map(g=>`<tr><td><button class="series-name" data-series="${g.id}">${esc(g.name)}</button><div class="subline">${esc([...new Set(g.articles.map(a=>a.publisher))].slice(0,3).join(' · '))}${new Set(g.articles.map(a=>a.publisher)).size>3?' + meer':''}</div></td><td>${g.visibleProductions.map(p=>`<div class="type"><strong>${esc(p.kind==='Onbekend'?'Niet vastgesteld':p.kind)}</strong><div class="subline">${p.kind==='Nieuwe serie'?'Seizoen 1':p.season?'Seizoen '+p.season:'Seizoen onbekend'}</div></div>`).join('<br>')}</td><td>${g.visibleProductions.map(p=>`${badge(p.status)}<div class="subline">${p.reviewed?'Beoordeeld':'Automatisch'}${p.tvdb?' · TVDB verwerkt':''}</div>`).join('<br>')}</td><td>${g.articles.length}</td><td>${date(g.updated)}</td></tr>`).join('');
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
 $('dossier-tvdb').href='https://thetvdb.com/search?query='+encodeURIComponent(group.name);
 $('dossier-productions').innerHTML=group.productions.map(p=>`<div class="production-row"><div><h3>${esc(productionLabel(p))}</h3><p>${p.articles.length} ${p.articles.length===1?'bericht':'berichten'}${p.release_hint?' · '+esc(p.release_hint):''}${p.tvdb?' · Verwerkt voor TVDB':''}</p><button class="evidence-button" data-article="${p.status_article}">Onderbouwing: ${esc(p.evidence)}</button></div><div>${badge(p.status)}<p>${p.reviewed?'Handmatig beoordeeld':'Automatisch herkend'}</p></div></div>`).join('');
 $('dossier-news').innerHTML=group.articles.map(a=>newsRow(a)).join('');
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
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.view)setView(b.dataset.view);if(b.dataset.close)$(b.dataset.close).close();if(b.dataset.series){dossierId=b.dataset.series;renderDossier();$('series-detail').showModal();}if(b.dataset.article)openArticle(b.dataset.article);if(b.dataset.source)openSource(b.dataset.source);});
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
load();setInterval(load,10000);
