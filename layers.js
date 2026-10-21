/* Shelters + Warm Spaces layers. Loaded after the food bank script; it does not change food bank data or logic.
   Each layer has its own data file (shelters.js / warmspaces.js), scraper and update log. */
(function(){
const REPO='https://github.com/postcode-economics/find-your-food-bank';
const T={en:{sh:'Shelters',ws:'Warm spaces',near:'📍 Find nearest to me',upd:'updated',notLoaded:'tap to show',
 disc:'<b>Listings can change without notice.</b> Always call before you travel. In an emergency call 999. If you are sleeping rough in England, contact your local council or StreetLink.',
 add:'Add or update your service',closed:'Recently closed (last 30 days)',report:'Report an error',call:'Call',dir:'Directions',
 groups:'Who for',beds:'Beds',season:'Season',ref:'Referral',hours:'Hours',prov:'Provided',book:'Booking',dates:'Scheme dates',
 src:'Source',ver:'verified',stale:'Not verified for over 7 days, call first',ended:'This season’s scheme has ended',
 nSh:'Nearest shelters',nWs:'Nearest warm spaces',loading:'Loading…',offline:'You’re offline – showing saved data from ',none:'None listed',
 h1:'Find a food bank near you',search:'Search',ph:'Postcode or town, e.g. BN17 5 or Littlehampton',lang:'Cymraeg',noClosed:'Nothing closed in the last 30 days.'},
cy:{sh:'Llochesi',ws:'Mannau cynnes',near:'📍 Dod o hyd i’r agosaf ataf',upd:'diweddarwyd',notLoaded:'tapiwch i ddangos',
 disc:'<b>Gall rhestrau newid heb rybudd.</b> Ffoniwch bob amser cyn teithio. Mewn argyfwng ffoniwch 999. Os ydych chi’n cysgu ar y stryd, cysylltwch â’ch cyngor lleol.',
 add:'Ychwanegu neu ddiweddaru eich gwasanaeth',closed:'Wedi cau’n ddiweddar (30 diwrnod diwethaf)',report:'Rhoi gwybod am gamgymeriad',call:'Ffonio',dir:'Cyfarwyddiadau',
 groups:'I bwy',beds:'Gwelyau',season:'Tymor',ref:'Atgyfeirio',hours:'Oriau',prov:'Ar gael',book:'Archebu',dates:'Dyddiadau’r cynllun',
 src:'Ffynhonnell',ver:'gwiriwyd',stale:'Heb ei wirio ers dros 7 diwrnod, ffoniwch yn gyntaf',ended:'Mae cynllun y tymor hwn wedi dod i ben',
 nSh:'Llochesi agosaf',nWs:'Mannau cynnes agosaf',loading:'Wrthi’n llwytho…',offline:'Rydych chi all-lein – yn dangos data a gadwyd ar ',none:'Dim wedi’u rhestru',
 h1:'Dod o hyd i fanc bwyd yn agos atoch',search:'Chwilio',ph:'Cod post neu dref',lang:'English',noClosed:'Dim wedi cau yn y 30 diwrnod diwethaf.'}};
let lang=(()=>{try{return localStorage.getItem('lang')||'en'}catch(e){return 'en'}})();const t=k=>T[lang][k];
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hav=(a,b,c,d)=>{const r=x=>x*Math.PI/180,x=Math.sin(r(c-a)/2)**2+Math.cos(r(a))*Math.cos(r(c))*Math.sin(r(d-b)/2)**2;return 12742*Math.asin(Math.sqrt(x))};
const fmt=d=>d?new Date(d+'T12:00:00').toLocaleDateString(lang==='cy'?'cy-GB':'en-GB',{day:'numeric',month:'short',year:'numeric'}):'';
const LAYERS={sh:{file:'shelters.js',var:'SHELTERS',col:'#2EC4F1',on:false,data:null,group:null},ws:{file:'warmspaces.js',var:'WARMSPACES',col:'#FF8C42',on:false,data:null,group:null}};
const pinIcon=(col,grey)=>L.divIcon({className:'xpin',html:`<svg width="30" height="40" viewBox="0 0 30 40"><path d="M15 1C7 1 1 7 1 15c0 10 14 24 14 24s14-14 14-24C29 7 23 1 15 1z" fill="${grey?'#7a8496':col}" stroke="#0A1628" stroke-width="2.5"/><circle cx="15" cy="15" r="5.5" fill="#0A1628"/></svg>`,iconSize:[30,40],iconAnchor:[15,39],popupAnchor:[0,-34]});
// ---- UI
const bar=document.createElement('div');bar.id='xbar';bar.setAttribute('role','toolbar');
bar.innerHTML=`<button type="button" class="xt" data-l="sh" aria-pressed="false"><i style="background:${LAYERS.sh.col}"></i><span data-t="sh"></span><small id="u_sh"></small></button>
<button type="button" class="xt" data-l="ws" aria-pressed="false"><i style="background:${LAYERS.ws.col}"></i><span data-t="ws"></span><small id="u_ws"></small></button>
<button type="button" id="xlang" lang="${lang==='en'?'cy':'en'}"></button>`;
const hdr=document.querySelector('header');hdr.insertBefore(bar,hdr.querySelector('h1').nextSibling);
const nb=document.createElement('button');nb.type='button';nb.id='xnear';nb.className='btn';hdr.insertBefore(nb,document.getElementById('f').nextSibling);
nb.onclick=()=>document.getElementById('me').click();
const disc=document.createElement('div');disc.id='xdisc';disc.setAttribute('role','note');hdr.appendChild(disc);
const extra=document.createElement('section');extra.id='xextra';
extra.innerHTML=`<div id="xlist"></div><details id="xclosed"><summary data-t="closed"></summary><div id="xcl"></div></details>
<a class="btn call" id="xadd" target="_blank" rel="noopener" href="${REPO}/issues/new?template=register-service.yml"></a>`;
document.getElementById('list').after(extra);
function paint(){document.documentElement.lang=lang;document.querySelectorAll('[data-t]').forEach(e=>e.textContent=t(e.dataset.t));
 $x('xlang').textContent=t('lang');nb.textContent=t('near');disc.innerHTML=t('disc');$x('xadd').textContent=t('add');
 if(lang==='cy'||paint.done){document.querySelector('header h1').textContent=t('h1');document.querySelector('#f .go').textContent=t('search');document.getElementById('q').placeholder=t('ph')}
 paint.done=true;banner&&ban&&banner();for(const k in LAYERS)stamp(k);if(lastPos)nearX(...lastPos)}
function $x(i){return document.getElementById(i)}
function stamp(k){const L_=LAYERS[k];$x('u_'+k).textContent=L_.data?`${t('upd')} ${fmt(L_.data.updated)}`:t('notLoaded')}
$x('xlang').onclick=()=>{lang=lang==='en'?'cy':'en';try{localStorage.setItem('lang',lang)}catch(e){}paint()};
function load(k){const L_=LAYERS[k];if(L_.data)return Promise.resolve(L_.data);if(L_.p)return L_.p;$x('u_'+k).textContent=t('loading');
 return L_.p=new Promise((ok,no)=>{const s=document.createElement('script');s.src=L_.file;s.onload=()=>{L_.data=window[L_.var];stamp(k);ok(L_.data)};s.onerror=()=>{L_.p=null;stamp(k);no()};document.body.appendChild(s)})}
function hoursHtml(h){if(!h)return'';if(typeof h==='string')return esc(h);return '<table>'+Object.entries(h).map(([d,v])=>`<tr><td>${esc(d)}</td><td>${esc(v)}</td></tr>`).join('')+'</table>'}
function detail(k,i,dist){const tel=(i.phone||'').replace(/[^\d+]/g,''),row=(l,v)=>v&&v.length?`<p><b>${t(l)}:</b> ${v}</p>`:'';
 const rep=`${REPO}/issues/new?template=report-error.yml&layer=${k==='sh'?'Shelters':'Warm+spaces'}&entry=${encodeURIComponent(i.name+' ['+i.id+']')}&title=${encodeURIComponent('Correction: '+i.name)}`;
 return `<h3>${esc(i.name)}</h3>${dist!=null?`<div class="d">${dist<0.1?'<0.1':(dist*0.621).toFixed(1)} mi</div>`:''}
 ${i.ended?`<p class="xw">⚠ ${t('ended')}</p>`:''}${i.stale?`<p class="xw">⚠ ${t('stale')}</p>`:''}
 <p>${esc(i.address)}${i.postcode?` <b>${esc(i.postcode)}</b>`:''}</p>
 <a class="btn gm" href="https://www.google.com/maps/dir/?api=1&destination=${i.lat},${i.lng}" target="_blank" rel="noopener">${t('dir')} ➜</a>
 ${tel?`<a class="btn call" href="tel:${tel}">${t('call')} ${esc(i.phone)}</a>`:''}
 ${k==='sh'?row('groups',esc((i.groups||[]).join(', ')))+row('beds',esc(i.beds))+row('season',esc(i.season))+row('ref',esc(i.referral))+row('hours',esc(i.hours))
  :row('hours',hoursHtml(i.hours))+row('prov',esc((i.provided||[]).join(', ')))+row('book',esc(i.booking))+row('dates',esc(i.scheme_dates))}
 ${i.website?`<p><a href="${esc(/^https?:/.test(i.website)?i.website:'https://'+i.website)}" target="_blank" rel="noopener">${esc(i.website.replace(/^https?:\/\//,'').slice(0,40))}</a></p>`:''}
 <p class="sub">${t('src')}: <a href="${esc(i.source_url)}" target="_blank" rel="noopener">${esc(i.source)}</a>, ${t('ver')} ${fmt(i.last_verified)}</p>
 <a class="btn xrep" href="${rep}" target="_blank" rel="noopener">${t('report')}</a>`}
function showSheet(html){const s=document.getElementById('sheet');document.getElementById('sheetBody').innerHTML=`<div class="card">${html}</div>`;s.classList.add('open');s.setAttribute('aria-hidden','false')}
async function toggle(k,on){const L_=LAYERS[k],b=document.querySelector(`.xt[data-l=${k}]`);L_.on=on;b.setAttribute('aria-pressed',on);try{localStorage.setItem('lay_'+k,on?'1':'0')}catch(e){}
 if(!on){if(L_.group)map.removeLayer(L_.group);if(lastPos)nearX(...lastPos);return}
 try{await load(k)}catch(e){return}
 if(!L_.group){L_.group=L.markerClusterGroup({showCoverageOnHover:false,maxClusterRadius:45,iconCreateFunction:c=>L.divIcon({className:'xcl',html:`<div style="background:${L_.col}">${c.getChildCount()}</div>`,iconSize:[40,40]})});
  L_.data.items.forEach(i=>{const m=L.marker([i.lat,i.lng],{icon:pinIcon(L_.col,i.ended),opacity:i.ended?0.6:1,title:i.name});
   m.on('click',()=>showSheet(detail(k,i,lastPos?hav(lastPos[0],lastPos[1],i.lat,i.lng):null)));L_.group.addLayer(m)})}
 if(L_.on)map.addLayer(L_.group);if(lastPos)nearX(...lastPos)}
document.querySelectorAll('.xt').forEach(b=>b.onclick=()=>toggle(b.dataset.l,b.getAttribute('aria-pressed')!=='true'));
// ---- nearest lists for the extra layers, alongside (not inside) the food bank list
let lastPos=null;
function nearX(lat,lng,label){lastPos=[lat,lng,label];const out=[],save={lat,lng,label,at:new Date().toISOString(),fb:document.getElementById('list').innerHTML};
 for(const k in LAYERS){const L_=LAYERS[k];if(!L_.on||!L_.data)continue;
  const r=L_.data.items.map(i=>({i,d:hav(lat,lng,i.lat,i.lng)})).sort((a,b)=>(a.i.ended-b.i.ended)||a.d-b.d).slice(0,3);
  out.push(`<div class="lh" style="color:${L_.col}">${t(k==='sh'?'nSh':'nWs')}</div>`+(r.length?r.map(x=>`<div class="card x${k}">${detail(k,x.i,x.d)}</div>`).join(''):`<p>${t('none')}</p>`))}
 $x('xlist').innerHTML=out.join('');save.x=$x('xlist').innerHTML;try{localStorage.setItem('lastSearch',JSON.stringify(save))}catch(e){}}
const orig=window.nearest;window.nearest=function(lat,lng,label,note){const r=orig.apply(this,arguments);nearX(lat,lng,label);return r};
try{nearest=window.nearest}catch(e){}
// ---- recently closed (each layer kept separate)
$x('xclosed').addEventListener('toggle',async e=>{if(!e.target.open)return;const parts=[];
 for(const k of ['sh','ws']){try{const d=await load(k);const c=d.recently_closed||[];parts.push(`<div class="lh">${t(k)}</div>`+(c.length?c.map(i=>`<p><b>${esc(i.name)}</b>, ${esc(i.postcode)}<br><span class="sub">${esc(i.closed_reason||'')} · ${fmt(i.closed_on)}</span></p>`).join(''):`<p class="sub">${t('noClosed')}</p>`))}catch(_){}}
 $x('xcl').innerHTML=parts.join('')});
// ---- offline banner (EN/CY) + last saved search
const ban=document.createElement('div');ban.id='xoff';ban.setAttribute('role','status');ban.hidden=true;document.body.insertBefore(ban,document.body.firstChild);
let isOff=false;const savedAt=()=>{try{return localStorage.getItem('savedAt')}catch(e){return null}};
function banner(){if(!isOff){ban.hidden=true;return}const d=savedAt();ban.textContent=t('offline')+(d?new Date(d).toLocaleString(lang==='cy'?'cy-GB':'en-GB',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):'?');ban.hidden=false}
function goOffline(){if(isOff)return;isOff=true;banner();try{const s=JSON.parse(localStorage.getItem('lastSearch')||'null');
 if(s){if(!document.getElementById('list').innerHTML)document.getElementById('list').innerHTML=s.fb;if(!$x('xlist').innerHTML)$x('xlist').innerHTML=s.x}}catch(e){}}
addEventListener('offline',goOffline);addEventListener('online',()=>{isOff=false;banner()});
if(navigator.serviceWorker)navigator.serviceWorker.addEventListener('message',e=>{if(e.data==='offline')goOffline()});
function offlineCheck(){if(!navigator.onLine)goOffline()}
addEventListener('load',()=>{if(navigator.onLine&&!isOff)fetch('index.html',{cache:'no-store'}).then(r=>{if(r.ok&&!isOff)try{localStorage.setItem('savedAt',new Date().toISOString())}catch(e){}}).catch(goOffline)});
if('serviceWorker' in navigator)navigator.serviceWorker.register('sw.js').catch(()=>{});
paint();for(const k in LAYERS){try{if(localStorage.getItem('lay_'+k)==='1')toggle(k,true)}catch(e){}}
const q=new URLSearchParams(location.search);['sh','ws'].forEach(k=>{if(q.get(k)==='1')toggle(k,true)});
setTimeout(offlineCheck,500);
})();
