/* v3 layout (Motion Designer review, approved by Dean 21 Oct 2026). Display only: never changes food bank, shelter or warm space data. */
(function(){
try{history.scrollRestoration='manual'}catch(e){}  // round 4: a reload starts at the top, never at an old scroll position
const LG=()=>document.documentElement.lang==='cy'?'cy':'en';
const e_=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const B=(en,cy)=>`<span class="v-en">${en}</span><span class="v-cy" lang="cy">${cy}</span>`;  // both languages, CSS shows one
const DEN=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],DCY=['Sul','Llun','Maw','Mer','Iau','Gwe','Sad'];
// ---- opening hours -> {0..6:[[startMin,endMin]]}; null when unknown
const hm=s=>{const m=/^(\d{1,2})[:.](\d{2})$/.exec(s.trim());return m?(+m[1])*60+(+m[2]):null};
function rng(txt){const out=[];String(txt).replace(/(\d{1,2}[:.]\d{2})\s*[-–]\s*(\d{1,2}[:.]\d{2})/g,(_,a,b)=>{a=hm(a);b=hm(b);if(a!=null&&b!=null)out.push([a,b<=a?b+1440:b])});return out}
const DI={mo:1,tu:2,we:3,th:4,fr:5,sa:6,su:0,mon:1,tue:2,wed:3,thu:4,fri:5,sat:6,sun:0};
// free-text normaliser: "365 days, 5.00pm-10.00am" / "Every day 9am–5pm" / "Daily 17:00 – 10:00" -> "Mo-Su 17:00-10:00"
const ap=(h,m,x)=>{h=+h;m=m?+m:0;x=(x||'').toLowerCase();if(x==='pm'&&h<12)h+=12;if(x==='am'&&h===12)h=0;return p2(h)+':'+p2(m)};
function normH(h){let t=String(h).trim().replace(/[–—]/g,'-').replace(/\s*-\s*/g,'-').replace(/\s+to\s+/gi,'-');
 t=t.replace(/\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)\b/gi,(_,a,b,c)=>ap(a,b,c)).replace(/\b(\d{1,2})\.(\d{2})\b/g,'$1:$2');
 t=t.replace(/^(?:open\s+)?(?:every\s*day|daily|365\s*days(?:\s+a\s+year)?|7\s*days(?:\s+a\s+week)?)\s*[,:]?\s*(?:from\s+)?/i,'Mo-Su ');
 t=t.replace(/(\d{2}:\d{2})-(\d{1,2}:\d{2})(?:\s*\(?next day\)?)?/gi,'$1-$2');return t.trim()}
function sched(layer,i){
 if(layer==='fb'){const t=i.opening_times;if(!t||t.status!=='TIMES_FOUND'||(!t.structured&&!t.all_closed))return null;const s={};for(let d=0;d<7;d++)s[d]=[];
  for(const[k,v]of Object.entries(t.structured||{})){const d=DI[k];if(d==null)continue;(v||[]).forEach(([a,b])=>{a=hm(a);b=hm(b);if(a!=null&&b!=null)s[d].push([a,b<=a?b+1440:b])})}return s}
 const h=i.hours;if(!h)return null;const s={};for(let d=0;d<7;d++)s[d]=[];
 if(typeof h==='object'){let any=false;for(const[k,v]of Object.entries(h)){const d=DI[k.toLowerCase().slice(0,3)];if(d==null)continue;if(/monthly|fortnight|alternate|1st|2nd|3rd|last/i.test(v))return null;const r=rng(v);if(r.length){s[d].push(...r);any=true}}return any?s:null}
 const str=normH(h);if(/^24\/7$/.test(str)){for(let d=0;d<7;d++)s[d]=[[0,1440]];return s}
 if(/PH|SH|week|easter|dawn|dusk|sunrise|sunset|"/i.test(str))return null;let any=false;
 for(const part of str.split(/\s*;\s*/)){const m=/^((?:(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?,?)+)\s+(.+)$/.exec(part.trim());if(!m)return null;
  const days=[];m[1].split(',').filter(Boolean).forEach(x=>{const[a,b]=x.split('-').map(y=>DI[y.toLowerCase()]);if(b==null)days.push(a);else for(let d=a;;d=(d+1)%7){days.push(d);if(d===b)break}});
  if(/^off|closed$/i.test(m[2].trim())){days.forEach(d=>s[d]=[]);continue}
  const r=[];for(const x of m[2].split(',')){const q=/^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$/.exec(x.trim());if(!q)return null;const a=hm(q[1]),b=hm(q[2]);r.push([a,b<=a?b+1440:b])}
  days.forEach(d=>s[d]=r);any=true}
 return any?s:null}
const p2=n=>String(n).padStart(2,'0'),clk=m=>{m%=1440;const h=Math.floor(m/60),mm=m%60,h12=h%12||12;return h12+(mm?':'+p2(mm):'')+(h<12?'am':'pm')};
function status(layer,i,now=new Date()){if(i.upcoming)return{st:'closed',day:null};if(i.call_check)return{st:'unknown'};const s=sched(layer,i);if(!s)return{st:'unknown'};const d=now.getDay(),m=now.getHours()*60+now.getMinutes();
 for(const[a,b]of s[(d+6)%7])if(b>1440&&m<b-1440)return{st:'open',until:b-1440};
 for(const[a,b]of s[d])if(m>=a&&m<b)return{st:'open',until:b,next24:b-a>=1440};
 for(let k=0;k<8;k++){const dd=(d+k)%7;const c=(s[dd]||[]).filter(([a])=>k>0||a>m).sort((x,y)=>x[0]-y[0])[0];if(c)return{st:'closed',day:k===0?'today':k===1?'tomorrow':dd,dd,at:c[0],to:c[1]}}
 return{st:'closed',day:null}}
function badge(layer,i){const r=status(layer,i);
 if(r.st==='open')return `<div class="v3st open" role="note">${r.next24||(r.until===1440&&sched(layer,i)[0][0]&&false)?B('OPEN NOW','AR AGOR NAWR'):B('OPEN NOW until '+clk(r.until),'AR AGOR NAWR tan '+clk(r.until))}</div>`;
 if(r.st==='closed'){if(r.day==null)return `<div class="v3st shut" role="note">${B('Closed','Ar gau')}</div>`;
  const de=r.day==='today'?'today':r.day==='tomorrow'?'tomorrow':DEN[r.day],dc=r.day==='today'?'heddiw':r.day==='tomorrow'?'yfory':DCY[r.day];
  return `<div class="v3st shut" role="note">${B(`Closed · Next open <b>${DEN[r.dd]} ${clk(r.at)}⁠–⁠${clk(r.to)}</b>`,`Ar gau · Ar agor nesaf <b>${DCY[r.dd]} ${clk(r.at)}⁠–⁠${clk(r.to)}</b>`)}</div>`}
 return `<div class="v3st unk" role="note">${B('Times unknown – call first','Amseroedd heb eu rhestru – ffoniwch yn gyntaf')}</div>`}
const walk=km=>{if(km==null)return'';const min=Math.max(1,Math.round(km*1.3/4.8*60));// est.: straight line x1.3 at 4.8 km/h
 if(min>120)return'';
 return `<div class="v3wk">${IC('walk')}${B(`About ${min} min walk (est.)`,`Tua ${min} munud o gerdded (amcan.)`)}</div>`};
const share=i=>`<button type="button" class="btn v3share" data-n="${e_(i.name)}" data-a="${e_(i.address)}${i.postcode&&!(i.address||'').includes(i.postcode)?', '+e_(i.postcode):''}" data-ll="${i.lat},${i.lng}">${B('Share / text this address','Rhannu / tecstio’r cyfeiriad hwn')}</button>`;
const strip=()=>`<div class="v3sos" role="note">${B('<b>Sleeping rough, or worried about someone who is?</b> In England and Wales, tell StreetLink. <b>In danger? Call 999.</b><span class="sosb"><a class="sosl" href="https://streetlink.org.uk" target="_blank" rel="noopener">streetlink.org.uk</a><a class="sosl s999" href="tel:999">'+IC('phone')+'Call 999</a></span><details class="hlp"><summary>More free helplines</summary><ul><li><b>Shelter</b> housing advice (England): <a href="tel:08088004444">0808 800 4444</a>, Mon–Fri 8am–5pm</li><li><b>National Domestic Abuse Helpline</b> (England): <a href="tel:08082000247">0808 2000 247</a>, 24 hours</li><li><b>Live Fear Free</b> (Wales): <a href="tel:08088010100">0808 80 10 100</a>, 24 hours</li><li><b>Samaritans</b>: <a href="tel:116123">116 123</a>, 24 hours</li></ul></details>',
 '<b>Yn cysgu allan, neu’n poeni am rywun sydd?</b> Yng Nghymru a Lloegr, rhowch wybod i StreetLink. <b>Mewn perygl? Ffoniwch 999.</b><span class="sosb"><a class="sosl" href="https://streetlink.org.uk" target="_blank" rel="noopener">streetlink.org.uk</a><a class="sosl s999" href="tel:999">'+IC('phone')+'Ffonio 999</a></span><details class="hlp"><summary>Rhagor o linellau cymorth am ddim</summary><ul><li><b>Shelter</b> cyngor tai (Lloegr): <a href="tel:08088004444">0808 800 4444</a>, Llun–Gwener 8am–5pm</li><li><b>Llinell Gymorth Genedlaethol Cam-drin Domestig</b> (Lloegr): <a href="tel:08082000247">0808 2000 247</a>, 24 awr</li><li><b>Byw Heb Ofn</b> (Cymru): <a href="tel:08088010100">0808 80 10 100</a>, 24 awr</li><li><b>Samaritans</b>: <a href="tel:116123">116 123</a>, 24 awr</li></ul></details>')}</div>`;
window.V3={sched,status,badge,walk,share,strip};
// ---- food bank card + pop-up: status first, walking time, share. Donation-only sites get no open/closed badge (no client hours).
const insAfterD=(h,add)=>/<div class="d">[^<]*<\/div>/.test(h)?h.replace(/(<div class="d">[^<]*<\/div>)/,'$1'+add):h.replace(/(<\/h3>)/,'$1'+add);
const oc=window.card;window.card=function(i,d){let h=oc.apply(this,arguments);if(nc(i))return insAfterD(h,walk(d));
 h=badge('fb',i)+insAfterD(h,walk(d));return h.replace(/(<a class="btn gm"[^>]*>[^<]*<\/a>)/,'$1'+share(i))};
const op=window.pop;window.pop=function(i){let h=op.apply(this,arguments);return nc(i)?h:h.replace('<div class="pop">','<div class="pop">'+badge('fb',i))};
const on0=window.nearest;window.nearest=function(){const r=on0.apply(this,arguments);try{const l=document.getElementById('list'),cs=[...l.querySelectorAll(':scope>.card')];
 const sc=c=>{const i=items[+c.dataset.k];if(!i||nc(i))return 1;return({open:0,unknown:1,closed:2})[status('fb',i).st]};
 cs.map((c,n)=>({c,n,s:sc(c)})).sort((a,b)=>a.s-b.s||a.n-b.n).forEach(x=>{x.c.classList.toggle('v3closed',x.s===2);l.append(x.c)})}catch(e){}return r};
// ---- top: three big task buttons; toggle bar + search become secondary
const hdr=document.querySelector('header');const big=document.createElement('div');big.id='v3big';
const NB=[['fb','food','Food bank','Banc bwyd','Collect food','Casglu bwyd'],['ws','mug','Warm space','Man cynnes','Somewhere warm','Rhywle cynnes'],['sh','bed','Shelter tonight','Lloches heno','A bed tonight','Gwely heno']];
big.setAttribute('role','radiogroup');big.setAttribute('aria-label','Find help near you');
big.innerHTML=NB.map(([k,ic,en,cy,sen,scy])=>`<button type="button" class="v3b" role="radio" data-l="${k}" aria-checked="false" tabindex="-1"><span class="ic" aria-hidden="true">${IC(ic)}</span><span class="v3bt"><span class="v3bl">${B(en,cy)}</span><span class="v3bs">${B(sen,scy)}</span></span><span class="v3tick" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 12.5l5 5 10-11"/></svg></span><span class="v3sr">${B(', selected',', wedi’i ddewis')}</span></button>`).join('');
{const f=document.getElementById('f');if(f){hdr.querySelector('h1').after(f);f.after(big)}else hdr.querySelector('h1').after(big)}
const sos=document.createElement('div');sos.id='v3sos';sos.hidden=true;sos.innerHTML=strip();big.after(sos);
const near=document.getElementById('xnear');if(near)near.hidden=true;
// UK clock (Europe/London) for the night cue and night theme; ?clock=20:00 fakes it for tests
const ukH=()=>{const q=new URLSearchParams(location.search).get('clock');if(q&&/^\d{1,2}:\d{2}$/.test(q))return +q.split(':')[0]+(+q.split(':')[1])/60;
 const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date());return +p.find(x=>x.type==='hour').value+(+p.find(x=>x.type==='minute').value)/60};
window.V3.ukH=ukH;

function mark(k){document.querySelectorAll('.v3b').forEach(b=>{const on=b.dataset.l===k;b.setAttribute('aria-checked',String(on));b.tabIndex=on?0:-1});try{localStorage.setItem('v3layer',k)}catch(e){};['fwrap','ftab','v3open'].forEach(id=>{const e=document.getElementById(id);if(!e)return;e.classList.toggle('v3off',k!=='fb');e.inert=k!=='fb';e.setAttribute('aria-disabled',String(k!=='fb'));e.removeAttribute('aria-hidden')})}  // round 4: food bank filters dim (not vanish) for the other types: no blank gap, no shift  // round 2: filter row lives above the results (below the map), so hiding it never moves the buttons or the map
function want(k,noGo){window.v3focus=k;const on=b=>b.getAttribute('aria-pressed')==='true';
 ['fb','sh','ws'].forEach(x=>{const b=document.querySelector(`.xt[data-l=${x}]`);if(b&&on(b)!==(x===k))b.click()});
 mark(k);if(noGo)return;window.__go=false;
 // UX 22 Oct (Dean): a type tap never moves the page or asks for location; it re-runs the current search in place at once (no 900ms delay)
 // and the 'results updated' pill below the buttons says what changed, with a link down to the list
 let s=null;try{s=JSON.parse(localStorage.getItem('lastSearch')||'null')}catch(e){}
 const p=LN()||(s&&typeof s.lat==='number'?[s.lat,s.lng,s.label]:null);
 if(p){busy(k);const run=()=>{if(window.v3focus!==k)return;const y=scrollY;nearest(p[0],p[1],p[2],p[3]);if(scrollY!==y)scrollTo({top:y,behavior:'auto'});pill(k)};requestAnimationFrame(()=>setTimeout(run,0))}  // round 4: the pressed state paints first, then the list re-runs
 else{busy(null);pill(k)}}  // before any search: just select; the pill line (space always reserved) asks for a postcode
const LN=()=>{try{return typeof lastNear!=='undefined'&&lastNear?lastNear:null}catch(e){return null}};  // index.html's script-level let
// ---- 'results updated' pill (aria-live) + pressed/loading state
const pl=document.createElement('div');pl.id='v3pill';pl.setAttribute('aria-live','polite');pl.setAttribute('role','status');big.after(pl);setTimeout(()=>pill(),0);
let busyT=0;function busy(k){const b=big.querySelector(`.v3b[data-l=${k}]`);big.querySelectorAll('.v3b').forEach(x=>{x.classList.remove('v3busy');x.removeAttribute('aria-busy')});
 if(!b)return;b.classList.add('v3busy');b.setAttribute('aria-busy','true');clearTimeout(busyT);busyT=setTimeout(()=>pill(k),8000)}
const tgt=k=>document.getElementById(k==='fb'?'list':'xlist');
function pill(k){k=k||window.v3focus||'fb';const t=tgt(k);if(!t||!LN()){const W0={fb:['food banks','banc bwyd'],ws:['warm spaces','man cynnes'],sh:['shelters','lloches']}[k];pl.innerHTML=`<span class="v3ph">${B(`Showing ${W0[0]}. Enter a postcode or town above, or tap the pin, to see the nearest.`,`Yn dangos ${W0[1]}. Rhowch god post neu dref uchod, neu tapiwch y pin, i weld y rhai agosaf.`)}</span>`;flash();return}
 const n=t.querySelectorAll('.card').length;if(k!=='fb'&&!n&&!t.textContent.trim())return;  // layer data still loading: stay busy, the observer calls again
 big.querySelectorAll('.v3b').forEach(x=>{x.classList.remove('v3busy');x.removeAttribute('aria-busy')});clearTimeout(busyT);
 const W={fb:['food banks','banc bwyd'],ws:['warm spaces','man cynnes'],sh:['shelters','lloches']}[k];
 pl.innerHTML=`<a href="#${t.id}" class="v3pl">${B(`Showing ${W[0]}: ${n} nearby · see list ↓`,`Yn dangos ${W[1]}: ${n} gerllaw · gweld y rhestr ↓`)}</a>`;flash()}
function flash(){pl.classList.remove('v3flash');void pl.offsetWidth;pl.classList.add('v3flash');
 ['#list>.lh','#xlist>.lh'].forEach(q=>{const h=document.querySelector(q);if(h){h.classList.remove('v3flash');void h.offsetWidth;h.classList.add('v3flash')}})}  // brief pulse: every update (incl. the same search again or re-tapping the chosen type) is visible
pl.addEventListener('click',e=>{const a=e.target.closest('a.v3pl');if(!a)return;e.preventDefault();const t=tgt(window.v3focus);if(!t)return;
 const sosE=document.getElementById('v3sos'),h=(window.v3focus==='sh'&&sosE&&!sosE.hidden)?sosE:(t.querySelector('.lh')||t);h.style.scrollMarginTop='12px';h.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
 const c=t.querySelector('.card a,.card button,.card h3');if(c)setTimeout(()=>{(t.querySelector('.lh')||t).setAttribute('tabindex','-1');(t.querySelector('.lh')||t).focus({preventScroll:true})},400)});
{const ob=new MutationObserver(()=>{if(LN())pill(window.v3focus)});['list','xlist'].forEach(id=>{const e=document.getElementById(id);if(e)ob.observe(e,{childList:true})})}
big.addEventListener('click',e=>{const b=e.target.closest('.v3b');if(b)want(b.dataset.l)});
big.addEventListener('keydown',e=>{const ks=['fb','ws','sh'],b=e.target.closest('.v3b');if(!b)return;let i=ks.indexOf(b.dataset.l);
 if(['ArrowDown','ArrowRight'].includes(e.key))i=(i+1)%3;else if(['ArrowUp','ArrowLeft'].includes(e.key))i=(i+2)%3;else if(e.key==='Home')i=0;else if(e.key==='End')i=2;else return;
 e.preventDefault();const n=big.querySelector(`.v3b[data-l=${ks[i]}]`);n.focus();want(ks[i])});
// restore the last chosen button (works offline: localStorage only)
{let k=null;try{k=localStorage.getItem('v3layer')}catch(e){}if(!['fb','ws','sh'].includes(k))k='fb';
 mark(k);setTimeout(()=>want(k,true),0)}
// ---- shelters emergency strip: always visible while the shelters layer is on
const shB=document.querySelector('.xt[data-l=sh]');const syncSos=()=>{sos.hidden=!(shB&&shB.getAttribute('aria-pressed')==='true')};
if(shB)new MutationObserver(syncSos).observe(shB,{attributes:true,attributeFilter:['aria-pressed']});syncSos();
// ---- 'Open today' folded into the results; 'Before you go' kept to one line
const tog=document.querySelector('label.tog'),list=document.getElementById('list');const res=document.createElement('div');res.id='v3res';
list.before(res);res.before(sos);res.append(tog,document.querySelector('.tnote'),document.getElementById('hid'));
// ---- list-only view and light (high contrast) mode, both remembered
const tools=document.createElement('div');tools.id='v3tools';
tools.innerHTML=`<button type="button" class="v3t" id="v3list" aria-pressed="false">${B('List only','Rhestr yn unig')}</button><button type="button" class="v3t" id="v3light" aria-pressed="false">${B('Light mode','Modd golau')}</button>`;
document.getElementById('xbar').after(tools);document.getElementById('xbar').hidden=true;// layer row removed: the 3 need buttons set the layer
const pref=(k,v)=>{try{if(v===undefined)return localStorage.getItem(k)==='1';localStorage.setItem(k,v?'1':'0')}catch(e){}};
function setP(id,cls,on){document.documentElement.classList.toggle(cls,on);document.getElementById(id).setAttribute('aria-pressed',String(on));pref(cls,on);if(cls==='nomap'&&!on)setTimeout(()=>map.invalidateSize(),50)}
document.getElementById('v3list').onclick=()=>setP('v3list','nomap',!document.documentElement.classList.contains('nomap'));
document.getElementById('v3light').onclick=()=>setP('v3light','light',!document.documentElement.classList.contains('light'));
setP('v3list','nomap',pref('nomap'));
{let m=null;try{m=localStorage.getItem('light')}catch(e){}
 if(m==='1'||m==='0')setP('v3light','light',m==='1');
 else{const sysL=matchMedia('(prefers-color-scheme: light)').matches,sysD=matchMedia('(prefers-color-scheme: dark)').matches,h=ukH(),night=h>=19||h<7;
  const L_=sysL?true:sysD?false:!night&&false;// no system preference: app default (dark); at night always dark
  document.documentElement.classList.toggle('light',L_);document.getElementById('v3light').setAttribute('aria-pressed',String(L_))}}
// ---- share / text this address
document.addEventListener('click',async e=>{const b=e.target.closest('.v3share');if(!b)return;const txt=`${b.dataset.n}, ${b.dataset.a}. https://www.google.com/maps/dir/?api=1&destination=${b.dataset.ll}&travelmode=walking`;
 if(navigator.share){try{await navigator.share({title:b.dataset.n,text:txt});return}catch(err){if(err&&err.name==='AbortError')return}}
 location.href='sms:?&body='+encodeURIComponent(txt)});
// ---- remember last search: re-run it on the next visit
addEventListener('load',()=>setTimeout(()=>{if(LN())return;let s=null;try{s=JSON.parse(localStorage.getItem('lastSearch')||'null')}catch(e){}
 if(s&&typeof s.lat==='number'&&new URLSearchParams(location.search).get('fresh')!=='1'){window.__go=false;nearest(s.lat,s.lng,s.label)}},400));  // quiet restore: never moves the page
// ---- 'Change type' link above the results (the type buttons are far above once you scroll the list)
{const ct=document.createElement('a');ct.href='#v3big';ct.id='v3chg';ct.innerHTML=B('↑ Change type: food bank, warm space or shelter','↑ Newid math: banc bwyd, man cynnes neu loches');
 const sosE=document.getElementById('v3sos');(sosE||document.getElementById('v3res')).before(ct);
 ct.onclick=e=>{e.preventDefault();ct.blur();scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});const b=big.querySelector('.v3b[aria-checked=true]');if(b)b.focus({preventScroll:true})}}
// ---- map no longer hijacks the page scroll: wheel zoom only after a click/focus on the map, off again when the pointer leaves
try{map.options.wheelPxPerZoomLevel=180;map.options.wheelDebounceTime=80;map.scrollWheelZoom.disable();const mc=map.getContainer();map.on('click focus',()=>map.scrollWheelZoom.enable());mc.addEventListener('mouseleave',()=>map.scrollWheelZoom.disable());mc.addEventListener('blur',()=>map.scrollWheelZoom.disable())}catch(e){}
// ---- desktop (>=1024px): map and results side by side; phones keep the single column (CSS in v3.css)
{const m=document.getElementById('map'),sp=document.createElement('div'),col=document.createElement('div');sp.id='v3split';col.id='v3col';m.before(sp);sp.append(m,col);
 let n=sp.nextElementSibling;while(n&&!(n.classList&&n.classList.contains('share'))&&n.tagName!=='FOOTER'){const nx=n.nextElementSibling;col.append(n);n=nx}
 const xb=document.getElementById('xbefore'),fw=document.getElementById('fwrap'),ft=document.getElementById('ftab'),chg=document.getElementById('v3chg');
 col.prepend(chg);  // round 3 (Dean): filters, 'Always call' and List only/Light mode back above the map, right under the type buttons
 {const fl=document.createElement('div');fl.id='v3filt';const r2=document.createElement('div');r2.id='v3row2';const tl=document.getElementById('v3tools');r2.append(...[xb].filter(Boolean));const ot=document.querySelector('label.tog');if(ot)ot.id='v3open';fl.append(...[fw,ot,tl,ft,r2].filter(Boolean));fl.classList.toggle('fclosed',!!window.fbFiltersClosed);{const al=()=>{const o=document.getElementById('v3open'),x=document.getElementById('fhide'),w=document.querySelector('#v3filt [data-f=walk]');if(!o||!x||!w)return;const t=document.getElementById('v3tools'),vc=document.querySelector('#v3filt [data-f=vouch]');if(t){t.style.removeProperty('order');t.classList.remove('v3tight')}if(innerWidth>=1024||!w.offsetParent){o.style.removeProperty('margin-left');return}o.style.setProperty('margin-left',Math.max(0,Math.round(w.getBoundingClientRect().left-fl.getBoundingClientRect().left-parseFloat(getComputedStyle(fl).paddingLeft||0)))+'px','important');if(t&&vc){const top=e=>e.getBoundingClientRect().top;if(top(vc)>top(w)+5)t.style.setProperty('order','3','important');else if(top(t)>top(o)+5){t.classList.add('v3tight')}}};addEventListener('resize',al);if(window.ResizeObserver){const ro=new ResizeObserver(al);['fhide'].forEach(i=>{const e=document.getElementById(i);if(e)ro.observe(e)});ro.observe(fl)}setTimeout(al,0);window.v3align=al}big.after(fl);
    if(ot){const vr=document.getElementById('v3res'),mq=matchMedia('not all'),place=()=>{if(mq.matches){if(ot.parentElement!==vr)vr.prepend(ot)}else if(ot.parentElement!==fl)fl.insertBefore(ot,tl)};place();mq.addEventListener('change',place)}  // MD4: Open today sits with the chips where it fits (>=340px); below 340px it stays above the list so the map isn't pushed down
    const pr=document.createElement('div');pr.id='v3prow';fl.after(pr);pr.append(pl)}  // filters + 'Always call' + tools stay directly under the type buttons (Dean); pill row follows
 const xl=document.getElementById('xlist'),so=document.getElementById('v3sos');if(xl&&so)xl.before(so);
 setTimeout(()=>map.invalidateSize(),0);matchMedia('(min-width:1024px)').addEventListener('change',()=>setTimeout(()=>map.invalidateSize(),50))}

// ---- round 4: messages never push the map; offline helpers
(function(){const note=document.createElement('div');note.id='v3note';note.setAttribute('role','status');note.setAttribute('aria-live','polite');
 const chg=document.getElementById('v3chg');(chg||document.getElementById('v3res')).after(note);
 const om=window.msg;window.msg=function(t,err){om.apply(this,arguments);const has=!!t;
  if(err&&has){pl.innerHTML=`<span class="v3err" role="alert">${e_(t)}</span>`;  // errors take the reserved pill slot: no layout shift
   const L=document.querySelector('#list>.lh');if(L&&!document.getElementById('v3stale')&&LN()){const d=document.createElement('div');d.id='v3stale';d.className='v3stale';d.textContent=(LG()==='cy'?'Canlyniadau blaenorol (ni weithiodd y chwiliad newydd)':'Earlier results (the new search didn’t work)');L.before(d)}}
  else if(has&&/^Searching|^Finding|^Chwilio/.test(t)){pl.innerHTML=`<span class="v3ph">${e_(t)}</span>`}
  else{note.textContent=t||'';note.hidden=!t}};
 note.hidden=true})();
// restore the saved search text into the box
addEventListener('load',()=>setTimeout(()=>{const q=document.getElementById('q');if(!q||q.value)return;let s=null;try{s=JSON.parse(localStorage.getItem('lastSearch')||'null')}catch(e){}
 if(s&&s.label&&s.label!=='your location'&&new URLSearchParams(location.search).get('fresh')!=='1')q.value=s.label},450));
// offline map note: tiles that fail while offline
(function(){const m=document.getElementById('map');if(!m)return;const n=document.createElement('div');n.id='v3tilenote';n.hidden=true;n.setAttribute('role','note');
 n.innerHTML=B('Offline: map pictures for this area aren’t saved. The list below is still correct.','All-lein: does dim lluniau map wedi’u cadw ar gyfer yr ardal hon. Mae’r rhestr isod yn dal yn gywir.');m.append(n);
 let bad=0;const on=l=>{if(!l||!l.on||l._v3t)return;l._v3t=1;l.on('tileerror',()=>{if(!navigator.onLine){bad++;n.hidden=false}});l.on('tileload',()=>{if(bad>0)bad--;})};
 map.eachLayer(on);map.on('layeradd',e=>on(e.layer));addEventListener('online',()=>{n.hidden=true;bad=0});map.on('movestart',()=>{if(navigator.onLine)n.hidden=true})})();
})();
