/* v3 layout (Motion Designer review, approved by Dean 21 Oct 2026). Display only: never changes food bank, shelter or warm space data. */
(function(){
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
function status(layer,i,now=new Date()){const s=sched(layer,i);if(!s)return{st:'unknown'};const d=now.getDay(),m=now.getHours()*60+now.getMinutes();
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
const strip=()=>`<div class="v3sos" role="note">${B('<b>Sleeping rough, or worried about someone who is?</b> In England and Wales, tell StreetLink. <b>In danger? Call 999.</b><span class="sosb"><a class="sosl" href="https://streetlink.org.uk" target="_blank" rel="noopener">streetlink.org.uk</a><a class="sosl s999" href="tel:999">'+IC('phone')+'Call 999</a></span>',
 '<b>Yn cysgu allan, neu’n poeni am rywun sydd?</b> Yng Nghymru a Lloegr, rhowch wybod i StreetLink. <b>Mewn perygl? Ffoniwch 999.</b><span class="sosb"><a class="sosl" href="https://streetlink.org.uk" target="_blank" rel="noopener">streetlink.org.uk</a><a class="sosl s999" href="tel:999">'+IC('phone')+'Ffonio 999</a></span>')}</div>`;
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
big.innerHTML=NB.map(([k,ic,en,cy,sen,scy])=>`<button type="button" class="v3b" role="radio" data-l="${k}" aria-checked="false" tabindex="-1"><span class="ic" aria-hidden="true">${IC(ic)}</span><span class="v3bt"><span class="v3bl">${B(en,cy)}</span><span class="v3bs">${B(sen,scy)}</span></span><span class="v3tick" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 12.5l5 5 10-11"/></svg></span><span class="v3sr">${B(', selected',', wedi’i ddewis')}</span></button>`+(k==='sh'?`<div id="v3night" hidden>${B('Help tonight','Help heno')}</div>`:'')).join('');
{const f=document.getElementById('f');if(f){hdr.querySelector('h1').after(f);f.after(big)}else hdr.querySelector('h1').after(big)}
const sos=document.createElement('div');sos.id='v3sos';sos.hidden=true;sos.innerHTML=strip();big.after(sos);
const near=document.getElementById('xnear');if(near)near.hidden=true;
// UK clock (Europe/London) for the night cue and night theme; ?clock=20:00 fakes it for tests
const ukH=()=>{const q=new URLSearchParams(location.search).get('clock');if(q&&/^\d{1,2}:\d{2}$/.test(q))return +q.split(':')[0]+(+q.split(':')[1])/60;
 const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date());return +p.find(x=>x.type==='hour').value+(+p.find(x=>x.type==='minute').value)/60};
window.V3.ukH=ukH;
const nightL=document.getElementById('v3night');const syncNight=()=>{const h=ukH();nightL.hidden=!(h>=17||h<8)};syncNight();setInterval(syncNight,60000);
function mark(k){document.querySelectorAll('.v3b').forEach(b=>{const on=b.dataset.l===k;b.setAttribute('aria-checked',String(on));b.tabIndex=on?0:-1});try{localStorage.setItem('v3layer',k)}catch(e){};['fwrap','ftab'].forEach(id=>{const e=document.getElementById(id);if(e)e.style.display=k==='fb'?'':'none'})}
function want(k,noGo){window.v3focus=k;const on=b=>b.getAttribute('aria-pressed')==='true';
 ['fb','sh','ws'].forEach(x=>{const b=document.querySelector(`.xt[data-l=${x}]`);if(b&&on(b)!==(x===k))b.click()});
 mark(k);if(noGo)return;
 let s=null;try{s=JSON.parse(localStorage.getItem('lastSearch')||'null')}catch(e){}
 if(window.lastNear||s){setTimeout(()=>{const p=window.lastNear||[s.lat,s.lng,s.label];nearest(p[0],p[1],p[2]);const t=document.getElementById(k==='fb'?'list':'xlist');t&&t.scrollIntoView({block:'start'})},k==='fb'?0:900)}
 else document.getElementById('me').click()}
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
tools.innerHTML=`<button type="button" class="v3t" id="v3list" aria-pressed="false">${B('List only','Rhestr yn unig')}</button><button type="button" class="v3t" id="v3light" aria-pressed="false">${B('High contrast','Cyferbyniad uchel')}</button>`;
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
addEventListener('load',()=>setTimeout(()=>{if(window.lastNear)return;let s=null;try{s=JSON.parse(localStorage.getItem('lastSearch')||'null')}catch(e){}
 if(s&&typeof s.lat==='number'&&new URLSearchParams(location.search).get('fresh')!=='1')nearest(s.lat,s.lng,s.label)},400));
})();
