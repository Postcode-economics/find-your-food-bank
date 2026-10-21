/* Report a problem: one form for every pin (food banks incl. donation-only sites, shelters, warm spaces).
   Sends to FormSubmit's AJAX endpoint; falls back to a pre-filled email if that fails or the device is offline.
   Display only: it never changes pin data. */
(function(){
const REPORT_EMAIL='postcode.economics@gmail.com';   // swap for FormSubmit's random alias later; used for both the form and the email backup
const ENDPOINT='https://formsubmit.co/ajax/'+REPORT_EMAIL;
const MAX_PER_DAY=3,MIN_MS=3000;
const LAYER={fb:{en:'Food banks',cy:'Banciau bwyd'},sh:{en:'Shelters',cy:'Llochesi'},ws:{en:'Warm spaces',cy:'Mannau cynnes'}};
const R={
 fb:['donations','place','times','phone','closed','other'],
 sh:['closed','place','times','phone','other'],ws:['closed','place','times','phone','other']};
const T={en:{btn:'Report a problem',title:'Report a problem',intro:'Tell us what’s wrong with this listing. We check every report before changing the map.',
  layer:'Map layer',name:'Name',address:'Address',id:'Listing ID',reason:'What’s wrong?',req:'(required)',opt:'(optional)',
  r_donations:'This is a donations-only site, not a food bank',r_place:'The address or pin is in the wrong place',r_times:'The opening times are wrong',r_phone:'The phone number is wrong',r_closed:'It’s closed',r_other:'Something else',
  details:'Details',detailsPh:'e.g. clients should go to the church hall on High Street',yname:'Your name',email:'Your email',emailHint:'Only if you’re happy for us to reply.',
  staff:'I work or volunteer here',send:'Send report',cancel:'Cancel',close:'Close',sending:'Sending…',
  ok:'Thank you. Your report has been sent and we’ll check it before changing anything on the map.',
  fail:'Sorry, we couldn’t send that just now.',offline:'You’re offline, so we can’t send this from the map.',
  mail:'Email your report instead',mailNote:'This opens your email app with the details filled in.',
  limit:'Thanks for your help. You’ve sent 3 reports today, which is the daily limit on this device. Please try again tomorrow, or email us:',
  wait:'Please take a moment to check the details, then press Send again.',pick:'Pick what’s wrong to continue.',bademail:'That email address doesn’t look right.'},
cy:{btn:'Rhoi gwybod am broblem',title:'Rhoi gwybod am broblem',intro:'Dywedwch wrthym beth sydd o’i le gyda’r rhestriad hwn. Rydym yn gwirio pob adroddiad cyn newid y map.',
  layer:'Haen y map',name:'Enw',address:'Cyfeiriad',id:'ID y rhestriad',reason:'Beth sydd o’i le?',req:'(gofynnol)',opt:'(dewisol)',
  r_donations:'Safle rhoddion yn unig yw hwn, nid banc bwyd',r_place:'Mae’r cyfeiriad neu’r pin yn y lle anghywir',r_times:'Mae’r oriau agor yn anghywir',r_phone:'Mae’r rhif ffôn yn anghywir',r_closed:'Mae wedi cau',r_other:'Rhywbeth arall',
  details:'Manylion',detailsPh:'e.e. dylai cleientiaid fynd i neuadd yr eglwys ar y Stryd Fawr',yname:'Eich enw',email:'Eich e-bost',emailHint:'Dim ond os ydych chi’n hapus i ni ateb.',
  staff:'Rwy’n gweithio neu’n gwirfoddoli yma',send:'Anfon adroddiad',cancel:'Canslo',close:'Cau',sending:'Wrthi’n anfon…',
  ok:'Diolch. Mae eich adroddiad wedi’i anfon a byddwn yn ei wirio cyn newid unrhyw beth ar y map.',
  fail:'Mae’n ddrwg gennym, methwyd anfon hynny ar hyn o bryd.',offline:'Rydych chi all-lein, felly ni allwn anfon hwn o’r map.',
  mail:'Anfonwch eich adroddiad drwy e-bost',mailNote:'Bydd hyn yn agor eich ap e-bost gyda’r manylion wedi’u llenwi.',
  limit:'Diolch am eich help. Rydych chi wedi anfon 3 adroddiad heddiw, sef y terfyn dyddiol ar y ddyfais hon. Rhowch gynnig arall arni yfory, neu anfonwch e-bost atom:',
  wait:'Cymerwch eiliad i wirio’r manylion, yna pwyswch Anfon eto.',pick:'Dewiswch beth sydd o’i le i barhau.',bademail:'Nid yw’r cyfeiriad e-bost yn edrych yn iawn.'}};
const lang=()=>{try{return localStorage.getItem('lang')==='cy'?'cy':'en'}catch(e){return document.documentElement.lang==='cy'?'cy':'en'}};
const e_=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Button markup used inside cards, pop-ups and sheets. Both languages are rendered; CSS shows the one matching <html lang>.
window.repB=(layer,i)=>`<button type="button" class="btn rpb" data-rl="${e_(layer)}" data-rid="${e_(i.id)}" data-rn="${e_(i.name)}" data-ra="${e_([i.address,i.postcode&&!(i.address||'').includes(i.postcode)?i.postcode:''].filter(Boolean).join(', '))}" data-rlab="${e_(i.label_en||'')}"><span class="en">${window.IC?IC('alert'):''}${T.en.btn}</span><span class="cy" lang="cy">${window.IC?IC('alert'):''}${T.cy.btn}</span></button>`;
// ---- daily limit (per device, localStorage)
const day=()=>new Date().toISOString().slice(0,10);
const used=()=>{try{const o=JSON.parse(localStorage.getItem('rpCount')||'{}');return o.d===day()?o.n:0}catch(e){return 0}};
const bump=()=>{try{localStorage.setItem('rpCount',JSON.stringify({d:day(),n:used()+1}))}catch(e){}};
// ---- modal
const ov=document.createElement('div');ov.id='rpm';ov.hidden=true;
ov.innerHTML='<div class="rpd" role="dialog" aria-modal="true" aria-labelledby="rpTitle" aria-describedby="rpIntro"></div>';
document.body.appendChild(ov);const dlg=ov.firstChild;let cur=null,opener=null,openedAt=0;
function mailto(p,L){const body=[`${T[L].layer}: ${p.layerName}`,`${T[L].name}: ${p.name}`,`${T[L].address}: ${p.address}`,`${T[L].id}: ${p.id}`,`${T[L].reason}: ${p.reason||''}`,
  `${T[L].details}: ${p.details||''}`,`${T[L].yname}: ${p.yname||''}`,`${T[L].email}: ${p.email||''}`,`${T[L].staff}: ${p.staff?'Yes / Ydw':'No / Na'}`,`Page: ${location.href}`,`Language: ${L}`,`Time: ${new Date().toISOString()}`].join('\n');
 return `mailto:${REPORT_EMAIL}?subject=${encodeURIComponent('Map report: '+p.name)}&body=${encodeURIComponent(body)}`}
function msg(kind,html){const m=dlg.querySelector('#rpMsg');m.className='rpmsg '+kind;m.innerHTML=html;m.hidden=false;m.focus()}
function fallback(p,L,why){msg('err',`<p>${T[L][why]}</p><a class="btn rpmail" href="${e_(mailto(p,L))}">${window.IC?IC('mail'):''}${T[L].mail}</a><p class="rph">${T[L].mailNote}</p>`)}
function values(){const f=dlg.querySelector('form'),r=f.querySelector('input[name=reason]:checked');
 return {...cur,reasonKey:r?r.value:'',reason:r?T.en['r_'+r.value]:'',details:f.details.value.trim(),yname:f.yname.value.trim(),email:f.email.value.trim(),staff:f.staff.checked,honey:f._honey.value}}
function open(b){const L=lang(),t=T[L];opener=b;openedAt=Date.now();
 cur={layer:b.dataset.rl,layerName:LAYER[b.dataset.rl]?LAYER[b.dataset.rl].en:b.dataset.rl,id:b.dataset.rid,name:b.dataset.rn,address:b.dataset.ra,label:b.dataset.rlab};
 const ro=(k,v)=>`<div class="rpro"><span class="rpk">${t[k]}</span><span class="rpv">${e_(v)}</span></div>`;
 const reasons=(R[cur.layer]||R.fb).map(k=>`<label class="rpr"><input type="radio" name="reason" value="${k}" required><span>${t['r_'+k]}</span></label>`).join('');
 const over=used()>=MAX_PER_DAY;
 dlg.innerHTML=`<div class="rphead"><h2 id="rpTitle">${t.title}</h2><button type="button" class="rpx" aria-label="${t.close}">×</button></div>
 <p id="rpIntro" class="rph">${t.intro}</p>
 <div class="rpfix" aria-label="${t.title}">${ro('layer',LAYER[cur.layer]?LAYER[cur.layer][L]:cur.layer)}${ro('name',cur.name)}${ro('address',cur.address||'–')}${ro('id',cur.id)}</div>
 ${over?`<div id="rpMsg" class="rpmsg err" tabindex="-1"><p>${t.limit}</p><a class="btn rpmail" href="${e_(mailto(cur,L))}">${window.IC?IC('mail'):''}${t.mail}</a></div>`:`<form novalidate>
 <fieldset><legend>${t.reason} <small>${t.req}</small></legend>${reasons}</fieldset>
 <label class="rpl" for="rpDet">${t.details} <small>${t.opt}</small></label><textarea id="rpDet" name="details" rows="3" maxlength="1500" placeholder="${t.detailsPh}"></textarea>
 <label class="rpl" for="rpName">${t.yname} <small>${t.opt}</small></label><input id="rpName" name="yname" type="text" autocomplete="name" maxlength="100">
 <label class="rpl" for="rpEmail">${t.email} <small>${t.opt}</small></label><input id="rpEmail" name="email" type="email" autocomplete="email" maxlength="150" aria-describedby="rpEh"><p id="rpEh" class="rph">${t.emailHint}</p>
 <label class="rpc"><input type="checkbox" name="staff"><span>${t.staff}</span></label>
 <div class="rphp" aria-hidden="true"><label>Leave this empty<input type="text" name="_honey" tabindex="-1" autocomplete="off"></label></div>
 <p id="rpPick" class="rph">${t.pick}</p>
 <div id="rpMsg" tabindex="-1" hidden></div>
 <div class="rpbtns"><button type="submit" class="btn rpsend" disabled aria-describedby="rpPick">${t.send}</button><button type="button" class="btn rpcancel">${t.cancel}</button></div></form>`}`;
 ov.hidden=false;document.documentElement.classList.add('rpopen');
 const f=dlg.querySelector('form');
 if(f){f.addEventListener('change',()=>{const ok=!!f.querySelector('input[name=reason]:checked');f.querySelector('.rpsend').disabled=!ok;dlg.querySelector('#rpPick').hidden=ok});
  f.addEventListener('submit',ev=>{ev.preventDefault();submit(f,L)});f.querySelector('.rpcancel').onclick=close}
 dlg.querySelector('.rpx').onclick=close;
 (dlg.querySelector('input[name=reason]')||dlg.querySelector('.rpx')).focus()}
async function submit(f,L){const t=T[L],p=values(),btn=f.querySelector('.rpsend');
 if(!p.reasonKey){msg('err',`<p>${t.pick}</p>`);return}
 if(p.email&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(p.email)){msg('err',`<p>${t.bademail}</p>`);f.email.focus();return}
 if(Date.now()-openedAt<MIN_MS){msg('err',`<p>${t.wait}</p>`);return}
 if(p.honey){msg('ok',`<p>${t.ok}</p>`);return}  // bot filled the trap: pretend success, send nothing
 if(used()>=MAX_PER_DAY){msg('err',`<p>${t.limit}</p><a class="btn rpmail" href="${e_(mailto(p,L))}">${window.IC?IC('mail'):''}${t.mail}</a>`);return}
 if(!navigator.onLine){fallback(p,L,'offline');return}
 btn.disabled=true;btn.textContent=t.sending;
 const payload={_subject:'Map report: '+p.name,_template:'table',_captcha:'false',_honey:'',
  layer:p.layerName,pin_name:p.name,pin_address:p.address,pin_id:p.id,current_label:p.label||'',reason:p.reason,details:p.details,reporter_name:p.yname,email:p.email,
  works_or_volunteers_here:p.staff?'Yes':'No',page_url:location.href,language:L,timestamp:new Date().toISOString()};
 try{const r=await fetch(ENDPOINT,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify(payload)});
  const j=await r.json().catch(()=>({}));if(!r.ok||String(j.success)==='false')throw new Error('send failed');
  bump();f.querySelectorAll('fieldset,textarea,input,.rpsend').forEach(x=>x.disabled=true);btn.textContent=t.send;msg('ok',`<p>${t.ok}</p>`);f.querySelector('.rpcancel').textContent=t.close}
 catch(err){btn.disabled=false;btn.textContent=t.send;fallback(p,L,navigator.onLine?'fail':'offline')}}
function close(){ov.hidden=true;document.documentElement.classList.remove('rpopen');dlg.innerHTML='';if(opener&&document.contains(opener))opener.focus();opener=null}
document.addEventListener('click',ev=>{const b=ev.target.closest('.rpb');if(!b)return;ev.preventDefault();ev.stopPropagation();open(b)},true);
ov.addEventListener('click',ev=>{if(ev.target===ov)close()});
document.addEventListener('keydown',ev=>{if(ov.hidden)return;
 if(ev.key==='Escape'){ev.preventDefault();ev.stopImmediatePropagation();close();return}
 if(ev.key==='Tab'){const fs=[...dlg.querySelectorAll('button:not([disabled]),a[href],input:not([disabled]):not([tabindex="-1"]),textarea:not([disabled])')].filter(x=>x.offsetParent!==null);
  if(!fs.length)return;const a=fs[0],z=fs[fs.length-1];if(ev.shiftKey&&document.activeElement===a){ev.preventDefault();z.focus()}else if(!ev.shiftKey&&document.activeElement===z){ev.preventDefault();a.focus()}}},true);
window.__report={REPORT_EMAIL,ENDPOINT,open};
})();
