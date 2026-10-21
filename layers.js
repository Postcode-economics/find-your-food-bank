/* Shelters + Warm Spaces layers. Loaded after the food bank script; it does not change food bank data or logic.
   Each layer has its own data file (shelters.js / warmspaces.js), scraper and update log. */
(function(){
const REPO='https://github.com/postcode-economics/find-your-food-bank';
const T={en:{fb:'Food banks',before:'Before you go',beforeSum:'Always call before you go',legend:'Key',sh:'Shelters',ws:'Warm spaces',near:'Find nearest to me',upd:'updated',notLoaded:'tap to show',
 disc:'<b>Listings can change without notice.</b> Always call before you travel. In an emergency call 999. If you are sleeping rough in England, contact your local council or StreetLink.',
 add:'Add or update your service',closed:'Recently closed (last 30 days)',report:'Report an error',call:'Call',dir:'Directions',
 groups:'Who for',beds:'Beds',season:'Season',ref:'Referral',hours:'Hours',prov:'Provided',book:'Booking',dates:'Scheme dates',
 src:'Source',ver:'verified',stale:'Not verified for over 7 days, call first',ended:'This season’s scheme has ended',
 nSh:'Nearest shelters',nWs:'Nearest warm spaces',loading:'Loading…',offline:'You’re offline – showing saved data from ',none:'None listed',
 h1:'Find help near you',search:'Search',ph:'Postcode or town',lang:'Cymraeg',noClosed:'Nothing closed in the last 30 days.',on:'✓ ON',mi:'miles',srcNote:'Details are shown in the language the source published them in.'},
cy:{fb:'Banciau bwyd',before:'Cyn i chi fynd',beforeSum:'Ffoniwch bob amser cyn mynd',legend:'Allwedd',sh:'Llochesi',ws:'Mannau cynnes',near:'Dod o hyd i’r agosaf ataf',upd:'diweddarwyd',notLoaded:'tapiwch i ddangos',
 disc:'<b>Gall rhestrau newid heb rybudd.</b> Ffoniwch bob amser cyn teithio. Mewn argyfwng ffoniwch 999. Os ydych chi’n cysgu ar y stryd, cysylltwch â’ch cyngor lleol.',
 add:'Ychwanegu neu ddiweddaru eich gwasanaeth',closed:'Wedi cau’n ddiweddar (30 diwrnod diwethaf)',report:'Rhoi gwybod am gamgymeriad',call:'Ffonio',dir:'Cyfarwyddiadau',
 groups:'I bwy',beds:'Gwelyau',season:'Tymor',ref:'Atgyfeirio',hours:'Oriau',prov:'Ar gael',book:'Archebu',dates:'Dyddiadau’r cynllun',
 src:'Ffynhonnell',ver:'gwiriwyd',stale:'Heb ei wirio ers dros 7 diwrnod, ffoniwch yn gyntaf',ended:'Mae cynllun y tymor hwn wedi dod i ben',
 nSh:'Llochesi agosaf',nWs:'Mannau cynnes agosaf',loading:'Wrthi’n llwytho…',offline:'Rydych chi all-lein – yn dangos data a gadwyd ar ',none:'Dim wedi’u rhestru',
 h1:'Dod o hyd i help yn agos atoch',search:'Chwilio',ph:'Cod post neu dref',lang:'EN',noClosed:'Dim wedi cau yn y 30 diwrnod diwethaf.',on:'✓ YMLAEN',mi:'milltir',srcNote:'Dangosir y manylion yn yr iaith a ddefnyddiodd y ffynhonnell.'}};
let lang=(()=>{try{return localStorage.getItem('lang')||'en'}catch(e){return 'en'}})();const t=k=>T[lang][k];
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hav=(a,b,c,d)=>{const r=x=>x*Math.PI/180,x=Math.sin(r(c-a)/2)**2+Math.cos(r(a))*Math.cos(r(c))*Math.sin(r(d-b)/2)**2;return 12742*Math.asin(Math.sqrt(x))};
const MCY=['Ionawr','Chwefror','Mawrth','Ebrill','Mai','Mehefin','Gorffennaf','Awst','Medi','Hydref','Tachwedd','Rhagfyr'],MEN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const p2=n=>String(n).padStart(2,'0');
const dstr=(dt,time)=>`${dt.getDate()} ${(lang==='cy'?MCY:MEN)[dt.getMonth()]} ${dt.getFullYear()}`+(time?(lang==='cy'?' am ':', ')+p2(dt.getHours())+':'+p2(dt.getMinutes()):'');
const fmt=d=>d?dstr(new Date(d+'T12:00:00')):'';
// Welsh for source-data values (shown as-is in English)
const VCY={'Hot Drinks':'Diodydd poeth','Accessible Toilets':'Toiledau hygyrch','Free Wifi':'Wifi am ddim','Child Friendly':'Croeso i blant','Charging Facilities':'Cyfleusterau gwefru','Parking':'Parcio','Other Refreshments':'Lluniaeth arall','Food Available':'Bwyd ar gael','Computer Access':'Mynediad at gyfrifiadur','Volunteers':'Gwirfoddolwyr','Co-working Desks':'Desgiau cydweithio','TV':'Teledu','Cool Space':'Man oer','Dog Friendly':'Croeso i gŵn','Energy Advice':'Cyngor ar ynni','Volunteers Needed':'Angen gwirfoddolwyr','Not stated':'Heb ei nodi','Not stated by source':'Heb ei nodi gan y ffynhonnell','Winter-only':'Gaeaf yn unig','Year-round':'Drwy’r flwyddyn','men':'dynion','women':'menywod','families':'teuluoedd','young people':'pobl ifanc','Booking needed':'Rhaid archebu','No booking needed':'Dim angen archebu','Mon':'Llun','Tue':'Maw','Wed':'Mer','Thu':'Iau','Fri':'Gwe','Sat':'Sad','Sun':'Sul'};
const v=x=>lang==='cy'&&VCY[x]?VCY[x]:x;
const vdates=x=>lang==='cy'&&/^Until /.test(x||'')?'Tan '+fmt(x.slice(6)):v(x);
const vreason=x=>lang==='cy'?String(x||'').replace(/^No longer listed by source \(unseen (\d+) days\)$/,'Nid yw’r ffynhonnell yn ei restru mwyach (heb ei weld ers $1 diwrnod)'):x;
const LAYERS={sh:{file:'shelters.js',var:'SHELTERS',col:'#56B4E9',shape:'sq',on:false,data:null,group:null},ws:{file:'warmspaces.js',var:'WARMSPACES',col:'#D55E00',shape:'dia',on:false,data:null,group:null}};
const SHP={sq:(c)=>`<svg width="32" height="40" viewBox="0 0 32 40"><path d="M3 3h26v26H21l-5 9-5-9H3z" fill="${c}" stroke="#0A1628" stroke-width="2.5"/><path d="M9 18l7-7 7 7v6H9z" fill="#0A1628"/></svg>`,
 dia:(c)=>`<svg width="34" height="40" viewBox="0 0 34 40"><path d="M17 1l15 15-15 23L2 16z" fill="${c}" stroke="#0A1628" stroke-width="2.5"/><path d="M13 21c0-4 4-5 3-9 4 2 6 6 4 10a4 4 0 0 1-7-1z" fill="#0A1628"/></svg>`};
const pinIcon=(col,grey,shape)=>L.divIcon({className:'xpin',html:SHP[shape](grey?'#7a8496':col),iconSize:[34,40],iconAnchor:[17,39],popupAnchor:[0,-34]});
// ---- UI
const bar=document.createElement('div');bar.id='xbar';bar.setAttribute('role','toolbar');
const seg=(k,col,shape,on)=>`<button type="button" class="xt" data-l="${k}" aria-pressed="${on}"><i class="sw ${shape}" style="background:${col}"></i><span data-t="${k}"></span></button>`;
bar.innerHTML=seg('fb','#F5C518','tear',true)+seg('sh',LAYERS.sh.col,'sq',false)+seg('ws',LAYERS.ws.col,'dia',false);
const hdr=document.querySelector('header');hdr.insertBefore(bar,hdr.querySelector('h1').nextSibling);
const lg=document.createElement('div');lg.id='xleg';lg.innerHTML=`<span><i class="sw tear" style="background:#F5C518"></i><b data-t="fb"></b> <small id="u_fb"></small></span><span><i class="sw sq" style="background:${LAYERS.sh.col}"></i><b data-t="sh"></b> <small id="u_sh"></small></span><span><i class="sw dia" style="background:${LAYERS.ws.col}"></i><b data-t="ws"></b> <small id="u_ws"></small></span>`;
const ft=document.querySelector('footer');const fu=document.createElement('div');fu.id='xupd';ft.prepend(fu);fu.append(...lg.children);
const lb=document.createElement('button');lb.type='button';lb.id='xlang';hdr.style.position='relative';hdr.prepend(lb);
document.getElementById('f').after(document.getElementById('msg'));  // search errors show inline under the search box
const nb=document.createElement('button');nb.type='button';nb.id='xnear';nb.className='btn';hdr.insertBefore(nb,document.getElementById('f').nextSibling);
nb.onclick=()=>document.getElementById('me').click();
const bf=document.createElement('details');bf.id='xbefore';bf.innerHTML='<summary><span class="bt" data-t="before"></span><span class="bs" data-t="beforeSum"></span></summary>';
const disc=document.createElement('div');disc.id='xdisc';disc.setAttribute('role','note');
const tog=hdr.querySelector('label.tog');tog.before(bf);bf.append(hdr.querySelector('.ref'),disc,hdr.querySelector('.tnote'));
const extra=document.createElement('section');extra.id='xextra';
extra.innerHTML=`<div id="xlist"></div><details id="xclosed"><summary data-t="closed"></summary><div id="xcl"></div></details>
<button type="button" class="btn call" id="xadd"></button>`;
document.getElementById('list').after(extra);
function paint(){document.documentElement.lang=lang;document.querySelectorAll('[data-t]').forEach(e=>e.textContent=t(e.dataset.t));
 $x('xlang').innerHTML=lang==='en'?'<b>EN</b><span aria-hidden="true">|</span>CY':'EN<span aria-hidden="true">|</span><b>CY</b>';$x('xlang').setAttribute('aria-label',lang==='en'?'Newid i’r Gymraeg':'Switch to English');nb.innerHTML=IC('pin')+'<span>'+esc(t('near'))+'</span>';disc.innerHTML=t('disc');$x('xadd').textContent=t('add');
 document.getElementById('q').placeholder=t('ph');if(lang==='cy'||paint.done){document.querySelector('header h1').textContent=t('h1');document.querySelector('#f .go').textContent=t('search');document.getElementById('q').placeholder=t('ph')}
 paint.done=true;trAll();stamp('fb');banner&&ban&&banner();for(const k in LAYERS)stamp(k);if(lastPos)nearX(...lastPos)}
function $x(i){return document.getElementById(i)}
function stamp(k){if(k==='fb'){$x('u_fb').textContent=`${t('upd')} ${fmt(String(window.FB_DATA.fetched).slice(0,10))}`;return}const L_=LAYERS[k];$x('u_'+k).textContent=L_.data?`${t('upd')} ${fmt(L_.data.updated)}`:t('notLoaded')}
$x('xlang').onclick=()=>{lang=lang==='en'?'cy':'en';try{localStorage.setItem('lang',lang)}catch(e){}paint()};
// Re-check expiry/staleness against today's date in the browser too, so a warm space greys out the day its scheme ends
// and a shelter is flagged once 7 days pass, even between nightly builds. ?testdate=YYYY-MM-DD simulates a date (testing only).
const TODAY=(()=>{const q=new URLSearchParams(location.search).get('testdate');if(q&&/^\d{4}-\d{2}-\d{2}$/.test(q))return q;const d=new Date();return d.getFullYear()+'-'+p2(d.getMonth()+1)+'-'+p2(d.getDate())})();
const dd=(a,b)=>Math.round((new Date(a+'T12:00:00')-new Date(b+'T12:00:00'))/864e5);
function relife(D){if(!D)return;(D.items||[]).forEach(i=>{if(i.scheme_end)i.ended=i.scheme_end<TODAY;if(i.last_verified)i.stale=dd(TODAY,i.last_verified)>7});
 D.recently_closed=(D.recently_closed||[]).filter(i=>!i.closed_on||dd(TODAY,i.closed_on)<=30)}
function load(k){const L_=LAYERS[k];if(L_.data)return Promise.resolve(L_.data);if(L_.p)return L_.p;$x('u_'+k).textContent=t('loading');
 return L_.p=new Promise((ok,no)=>{const s=document.createElement('script');s.src=L_.file;s.onload=()=>{L_.data=window[L_.var];relife(L_.data);stamp(k);ok(L_.data)};s.onerror=()=>{L_.p=null;stamp(k);no()};document.body.appendChild(s)})}
function hoursHtml(h){if(!h)return'';if(typeof h==='string')return esc(h);return '<table>'+Object.entries(h).map(([d,h])=>`<tr><td>${esc(v(d))}</td><td>${esc(lang==='cy'?h.replace(/Closed/i,'Ar gau'):h)}</td></tr>`).join('')+'</table>'}
// address: no repeated town or postcode, postcode once at the end
function addr(i){const pc=(i.postcode||'').trim(),re=pc?new RegExp('\\s*'+pc.replace(/\s+/g,'\\s*')+'\\s*','ig'):null;const seen=new Set(),out=[];
 String(i.address||'').split(',').map(x=>(re?x.replace(re,' '):x).replace(/\s+/g,' ').trim()).filter(Boolean).forEach(x=>{const k=x.toLowerCase();if(seen.has(k))return;
  // 'Birmingham Birmingham' left after removing the postcode
  const w=x.split(' ');const h=w.length%2===0&&w.slice(0,w.length/2).join(' ').toLowerCase()===w.slice(w.length/2).join(' ').toLowerCase()?w.slice(0,w.length/2).join(' '):x;
  if(seen.has(h.toLowerCase()))return;seen.add(h.toLowerCase());out.push(esc(h))});
 return out.join(', ')+(pc?` <b>${esc(pc)}</b>`:'')}
const known=x=>x&&!/^not stated/i.test(String(x).trim());
const CHIP=[['Food Available','Food','Bwyd'],['Charging Facilities','Charging','Gwefru'],['Free Wifi','Wifi','Wifi'],['Accessible Toilets','Toilets','Toiledau']];
const chips=i=>{const p=i.provided||[];const c=CHIP.filter(([k])=>p.includes(k));return c.length?`<div class="chips">${c.map(([,en,cy])=>`<span class="chip">${lang==='cy'?cy:en}</span>`).join('')}</div>`:''};
function detail(k,i,dist){const tel=(i.phone||'').replace(/[^\d+]/g,''),row=(l,v)=>v&&v.length?`<p><b>${t(l)}:</b> ${v}</p>`:'';
 return `${window.V3?V3.badge(k,i):''}<h3>${esc(i.name)}</h3>${dist!=null?`<div class="d">${dist*0.621<0.1?'0.1':dist*0.621<10?(dist*0.621).toFixed(1):Math.round(dist*0.621)} ${lang==='cy'?'milltir':(dist*0.621).toFixed(1)==='1.0'?'mile':'miles'}</div>`:''}${window.V3?V3.walk(dist):''}${k==='sh'&&window.V3?V3.strip():''}
 ${i.ended?`<p class="xw">${IC('alert')}${t('ended')}</p>`:''}${i.stale?`<p class="xw">${IC('alert')}${t('stale')}</p>`:''}
 <p>${addr(i)}</p>
 <a class="btn gm" href="https://www.google.com/maps/dir/?api=1&destination=${i.lat},${i.lng}&travelmode=walking" target="_blank" rel="noopener">${t('dir')}</a>${window.V3?V3.share(i):''}
 ${tel?`<a class="btn call" href="tel:${tel}">${IC('phone')}${t('call')} ${esc(i.phone)}</a>`:''}
 ${k==='sh'?row('groups',esc((i.groups||[]).map(v).join(', ')))+row('beds',esc(i.beds))+row('season',esc(v(i.season)))+row('ref',esc(i.referral))+row('hours',esc(i.hours))
  :row('hours',hoursHtml(i.hours))+chips(i)+(known(i.booking)?row('book',esc(v(i.booking))):'')+(known(i.scheme_dates)?row('dates',esc(vdates(i.scheme_dates))):'')}
 ${i.website?`<p><a href="${esc(/^https?:/.test(i.website)?i.website:'https://'+i.website)}" target="_blank" rel="noopener">${esc(i.website.replace(/^https?:\/\//,'').slice(0,40))}</a></p>`:''}
 ${lang==='cy'?`<p class="sub">${t('srcNote')}</p>`:''}<p class="sub">${t('src')}: <a href="${esc(i.source_url)}" target="_blank" rel="noopener">${esc(i.source)}</a>, ${t('ver')} ${fmt(i.last_verified)}</p>
 ${window.repB?repB(k,i):''}`}
function showSheet(html){const s=document.getElementById('sheet');document.getElementById('sheetBody').innerHTML=`<div class="card">${html}</div>`;s.classList.add('open');s.setAttribute('aria-hidden','false')}
async function toggle(k,on){if(k==='fb'){const b=document.querySelector('.xt[data-l=fb]');b.setAttribute('aria-pressed',on);on?map.addLayer(cl):map.removeLayer(cl);return}const L_=LAYERS[k],b=document.querySelector(`.xt[data-l=${k}]`);L_.on=on;b.setAttribute('aria-pressed',on);try{localStorage.setItem('lay_'+k,on?'1':'0')}catch(e){}
 if(!on){if(L_.group)map.removeLayer(L_.group);if(lastPos)nearX(...lastPos);return}
 try{await load(k)}catch(e){return}
 if(!L_.group){L_.group=L.markerClusterGroup({showCoverageOnHover:false,maxClusterRadius:45,iconCreateFunction:c=>L.divIcon({className:'xcl',html:`<div class="${L_.shape}" style="background:${L_.col}"><span>${c.getChildCount()}</span></div>`,iconSize:[40,40]})});
  L_.data.items.forEach(i=>{const m=L.marker([i.lat,i.lng],{icon:pinIcon(L_.col,i.ended,L_.shape),opacity:i.ended?0.6:1,title:i.name});
   m.on('click',()=>showSheet(detail(k,i,lastPos?hav(lastPos[0],lastPos[1],i.lat,i.lng):null)));L_.group.addLayer(m)})}
 if(L_.on)map.addLayer(L_.group);if(lastPos)nearX(...lastPos)}
document.querySelectorAll('.xt').forEach(b=>b.onclick=()=>toggle(b.dataset.l,b.getAttribute('aria-pressed')!=='true'));
// ---- nearest lists for the extra layers, alongside (not inside) the food bank list
let lastPos=null;const openOnly={sh:true,ws:true};
document.addEventListener('click',e=>{const b=e.target.closest('.v3oo');if(!b)return;openOnly[b.dataset.k]=!openOnly[b.dataset.k];if(lastPos)nearX(...lastPos)});
function nearX(lat,lng,label){lastPos=[lat,lng,label];const out=[],save={lat,lng,label,at:new Date().toISOString(),fb:document.getElementById('list').innerHTML};
 for(const k in LAYERS){const L_=LAYERS[k];if(!L_.on||!L_.data)continue;
  const all=L_.data.items.map(i=>({i,d:hav(lat,lng,i.lat,i.lng)})).sort((a,b)=>(a.i.ended-b.i.ended)||a.d-b.d);const oo=openOnly[k]&&window.V3;const sc=x=>oo?({open:0,unknown:1,closed:2})[V3.status(k,x.i).st]:0;
  const r=(oo?all.slice(0,60).filter(x=>sc(x)<2&&!x.i.ended).sort((a,b)=>sc(a)-sc(b)||a.d-b.d):all).slice(0,3);
  out.push(`<div class="lh" style="color:${L_.col}">${t(k==='sh'?'nSh':'nWs')}</div>`+`<button type="button" class="v3t v3oo" data-k="${k}" aria-pressed="${openOnly[k]}">${lang==='cy'?'Ar agor nawr yn unig':'Open now only'}</button>`+(oo?`<p class="sub v3ex">${lang==='cy'?'Ar agor nawr yn gyntaf. Lleoedd ar gau wedi’u cuddio.':'Open now first. Closed places hidden.'}</p>`:'')+(r.length?r.map(x=>`<div class="card x${k}">${detail(k,x.i,x.d)}</div>`).join(''):`<p>${t('none')}</p>`))}
 $x('xlist').innerHTML=out.join('');save.x=$x('xlist').innerHTML;try{localStorage.setItem('lastSearch',JSON.stringify(save))}catch(e){}}
const orig=window.nearest;window.nearest=function(lat,lng,label,note){const r=orig.apply(this,arguments);nearX(lat,lng,label);
 const me=document.getElementById('map'),top=me.getBoundingClientRect().top;if(top<0)scrollTo({top:Math.max(0,top+scrollY-8),behavior:'auto'});map.invalidateSize();return r};
try{nearest=window.nearest}catch(e){}
// ---- recently closed (each layer kept separate)
$x('xclosed').addEventListener('toggle',async e=>{if(!e.target.open)return;const parts=[];
 for(const k of ['sh','ws']){try{const d=await load(k);const c=d.recently_closed||[];parts.push(`<div class="lh">${t(k)}</div>`+(c.length?c.map(i=>`<p><b>${esc(i.name)}</b>, ${esc(i.postcode)}<br><span class="sub">${esc(vreason(i.closed_reason))} · ${fmt(i.closed_on)}</span></p>`).join(''):`<p class="sub">${t('noClosed')}</p>`))}catch(_){}}
 $x('xcl').innerHTML=parts.join('')});
// ---- Welsh for existing food bank UI: rewrites displayed text only, never data or behaviour
const FBX=[[/^Closed$/,'Ar gau'],[/^Times change, call ahead\.$/,'Mae amseroedd yn newid, ffoniwch ymlaen llaw.'],[/^Times not listed, call ahead\.$/,'Amseroedd heb eu rhestru, ffoniwch ymlaen llaw.'],
[/^Times not listed, call to check$/,'Amseroedd heb eu rhestru, ffoniwch i wirio'],[/^Opening times$/,'Oriau agor'],[/^Directions$/,'Cyfarwyddiadau'],[/^Their website$/,'Eu gwefan'],
[/^Give Food page$/,'Tudalen Give Food'],[/^Check times$/,'Gwirio amseroedd'],[/^source$/,'ffynhonnell'],[/^Share this map$/,'Rhannu’r map hwn'],[/^Link copied ✓$/,'Dolen wedi’i chopïo ✓'],
[/^Pin placed at the postcode centre\. Check the address\.$/,'Pin wedi’i osod yng nghanol y cod post. Gwiriwch y cyfeiriad.'],[/^Phone \(from Give Food\)$/,'Ffôn (gan Give Food)'],[/^Phone \(checked on their site\)$/,'Ffôn (wedi’i wirio ar eu gwefan)'],[/^Phone number from Give Food$/,'Rhif ffôn gan Give Food'],[/^Phone number checked on their site$/,'Rhif ffôn wedi’i wirio ar eu gwefan'],
[/^ ?Open today only$/,' Ar agor heddiw yn unig'],[/^Places with no times stay listed$/,'Mae lleoedd heb amseroedd yn aros ar y rhestr'],[/^Hides only places listed as closed today\. Places without listed times stay, call to check\.$/,'Yn cuddio dim ond lleoedd sydd wedi’u rhestru ar gau heddiw. Mae lleoedd heb amseroedd yn aros, ffoniwch i wirio.'],
[/^Most food banks need a referral or voucher\.$/,'Mae angen atgyfeiriad neu daleb ar y rhan fwyaf o fanciau bwyd.'],[/^ Call first\.$/,' Ffoniwch yn gyntaf.'],
[/^Searching…$/,'Wrthi’n chwilio…'],[/^Finding you…$/,'Wrthi’n dod o hyd i chi…'],[/^Search failed\. Check your connection and try again\.$/,'Methodd y chwiliad. Gwiriwch eich cysylltiad a rhowch gynnig arall arni.'],
[/^We couldn’t find “(.*)”\. Try a postcode or a town name, e\.g\. BN17 5LF or Littlehampton\.$/,'Methwyd dod o hyd i “$1”. Rhowch gynnig ar god post neu enw tref, e.e. BN17 5LF neu Littlehampton.'],
[/^Enter a postcode or town, e\.g\. BN17 5LF or Littlehampton\.$/,'Rhowch god post neu dref, e.e. BN17 5LF neu Littlehampton.'],
[/^Location isn’t available on this device\. Enter a postcode instead\.$/,'Nid yw lleoliad ar gael ar y ddyfais hon. Rhowch god post yn lle hynny.'],
[/^No problem, location is off\. Type a postcode instead and we’ll find the nearest food banks\.$/,'Dim problem, mae lleoliad wedi’i ddiffodd. Teipiwch god post a byddwn yn dod o hyd i’r banciau bwyd agosaf.'],
[/^Couldn’t get your location\. Type a postcode instead\.$/,'Methwyd cael eich lleoliad. Teipiwch god post yn lle hynny.'],
[/^Nearest 5( \(open today first\))? to (.*)$/,(m,a,b)=>'Y 5 agosaf'+(a?' (ar agor heddiw yn gyntaf)':'')+' at '+(b==='your location'?'eich lleoliad':b)],
[/^Part of (.*)$/,'Rhan o $1'],[/^(\d[\d.]*) miles? away$/,'$1 milltir i ffwrdd'],[/^(\d[\d.]*) miles?$/,'$1 milltir'],[/^From their website(.*)$/,(m,a)=>'O’u gwefan'+a.replace(/checked/,'gwiriwyd').replace(/not yet checked/,'heb ei wirio eto')],
[/^Hides only places listed as closed today \(([\d,]+) hidden\)\. Showing ([\d,]+) listed open today and ([\d,]+) without listed times, call to check\.$/,'Yn cuddio lleoedd sydd ar gau heddiw ($1 wedi’u cuddio). Yn dangos $2 ar agor heddiw a $3 heb amseroedd, ffoniwch i wirio.'],
[/^Mon$/,'Llun'],[/^Tue$/,'Maw'],[/^Wed$/,'Mer'],[/^Thu$/,'Iau'],[/^Fri$/,'Gwe'],[/^Sat$/,'Sad'],[/^Sun$/,'Sul'],[/^You are here$/,'Rydych chi yma'],[/^Searched: (.*)$/,'Chwiliwyd: $1'],
[/^Made by @postcode_economics\. $/,'Gwnaed gan @postcode_economics. '],[/^Follow for more UK money maps$/,'Dilynwch am fwy o fapiau arian y DU'],
[/^Data: $/,'Data: '],[/^, last updated $/,', diweddarwyd ddiwethaf '],[/^\. Times change, call ahead to confirm\. Phone numbers and opening times $/,'. Mae amseroedd yn newid, ffoniwch ymlaen llaw i gadarnhau. Rhifau ffôn ac oriau agor '],
[/^\. Postcodes: $/,'. Codau post: '],[/^\. Map © OpenStreetMap contributors\. Built by $/,'. Map © cyfranwyr OpenStreetMap. Adeiladwyd gan '],[/^checked (.*)$/,'gwiriwyd $1'],
[/^(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{4})$/,(m,d,mo,y)=>d+' '+MCY[MEN.indexOf(mo.slice(0,3))]+' '+y]];
const ATTR=[['q','aria-label','Postcode or town','Cod post neu dref'],['me','aria-label','Use my location','Defnyddio fy lleoliad'],['me','title','Use my location','Defnyddio fy lleoliad']];
const skip=n=>n.parentElement&&n.parentElement.closest('#rpm,.rpb,#xextra,#xbar,#xleg,#xbefore summary,#xoff,#xnear,#xlang,script,style,.leaflet-control-attribution');
function trNode(n){if(n.nodeType!==3||skip(n))return;if(n.__en==null||n.nodeValue!==n.__cy)n.__en=n.nodeValue;
 if(lang!=='cy'){if(n.__cy!=null&&n.nodeValue===n.__cy)n.nodeValue=n.__en;return}
 let x=n.__en;for(const[r,w]of FBX)if(r.test(x)){x=x.replace(r,w);break}n.__cy=x;if(n.nodeValue!==x)n.nodeValue=x}
function trAll(root){const w=document.createTreeWalker(root||document.body,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode())trNode(n);
 ATTR.forEach(([id,a,en,cy])=>{const e=document.getElementById(id);if(e)e.setAttribute(a,lang==='cy'?cy:en)})}
new MutationObserver(ms=>{if(lang!=='cy')return;for(const m of ms){if(m.type==='characterData')trNode(m.target);else m.addedNodes.forEach(n=>n.nodeType===3?trNode(n):trAll(n))}}).observe(document.body,{subtree:true,childList:true,characterData:true});
// ---- donation-only food bank sites: Welsh label + 'Get food at' links jump to the client location
const FBI=window.FB_DATA.items;const ENCY={};FBI.forEach(i=>{if(i.label_en){ENCY['📦 '+i.label_en]='📦 '+i.label_cy;ENCY[i.label_en]=i.label_cy}});
FBX.unshift([/^📦 (.*)$/,m=>ENCY[m]||m],...(()=>{const L=Object.keys(ENCY).filter(k=>!k.startsWith('📦'));return L.length?[[new RegExp('^('+L.map(x=>x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')+')$'),m=>ENCY[m]]]:[]})(),[/^Get food at:$/,'Cael bwyd yn:'],[/^Contact the food bank for where to get food\.$/,'Cysylltwch â’r banc bwyd i wybod ble i gael bwyd.'],[/^Phone \(to donate or ask\)$/,'Ffôn (i roi neu holi)']);
document.addEventListener('click',e=>{const a=e.target.closest('a[data-cid]');if(!a)return;e.preventDefault();const k=FBI.findIndex(i=>i.id===a.dataset.cid);if(k<0)return;
 map.setView([FBI[k].lat,FBI[k].lng],15);setTimeout(()=>select(k,false),300)});
// ---- offline banner (EN/CY) + last saved search
const ban=document.createElement('div');ban.id='xoff';ban.setAttribute('role','status');ban.hidden=true;document.body.insertBefore(ban,document.body.firstChild);
let isOff=false;const savedAt=()=>{try{return localStorage.getItem('savedAt')}catch(e){return null}};
function banner(){if(!isOff){ban.hidden=true;return}const d=savedAt();ban.textContent=t('offline')+(d?dstr(new Date(d),true):'?');ban.hidden=false}
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
