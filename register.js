/* Self-registration for shelters and warm spaces. Sends to FormSubmit (same inbox as Report a problem).
   Submissions are for review only: nothing here ever writes to the map data. An approved entry is added by hand
   to overrides/shelters_manual.json or overrides/warmspaces_manual.json with its source. */
(function(){
const EMAIL='postcode.economics@gmail.com',ENDPOINT='https://formsubmit.co/ajax/5030e7451fb0b7d985eef5842d9af2aa',MIN_MS=5000,MAX_PER_DAY=3;
const T={en:{title:'Add or update your service',intro:'For shelters and warm spaces. It’s free. We check every submission before anything appears on the map.',
 layer:'Type of service',sh:'Shelter',ws:'Warm space',name:'Service name',address:'Full address',postcode:'Postcode',phone:'Public phone number',web:'Website',
 hours:'Opening hours',hoursPh:'e.g. Mon–Fri 10:00–16:00',who:'Who it’s for (shelters)',whoPh:'e.g. men 18+, families',beds:'Beds (shelters)',ref:'Referral needed? (shelters)',
 dates:'Scheme start and end dates (warm spaces)',datesPh:'e.g. 1 Nov 2026 to 31 Mar 2027',offer:'What’s on offer',offerPh:'e.g. hot drinks, wifi, charging',
 yname:'Your name',email:'Your email',emailHint:'So we can check the details with you. Not shown on the map.',role:'Your role at the service',
 ok_:'I confirm these details are correct and can be shown publicly.',req:'(required)',opt:'(optional)',send:'Send for review',cancel:'Cancel',close:'Close',sending:'Sending…',
 ok:'Thanks. Your details have been sent for review. We’ll check them before they appear on the map.',fail:'Sorry, that didn’t send. Please email us instead:',
 offline:'You’re offline. Please try again when you’re connected, or email us:',missing:'Please fill in the required fields.',bademail:'That email address doesn’t look right.',
 badpc:'That postcode doesn’t look right.',wait:'Please take a moment to check the details, then press Send again.',limit:'You’ve sent 3 submissions today on this device. Please email us:'},
cy:{title:'Ychwanegu neu ddiweddaru eich gwasanaeth',intro:'Ar gyfer llochesi a mannau cynnes. Mae am ddim. Rydym yn gwirio pob cyflwyniad cyn i unrhyw beth ymddangos ar y map.',
 layer:'Math o wasanaeth',sh:'Lloches',ws:'Man cynnes',name:'Enw’r gwasanaeth',address:'Cyfeiriad llawn',postcode:'Cod post',phone:'Rhif ffôn cyhoeddus',web:'Gwefan',
 hours:'Oriau agor',hoursPh:'e.e. Llun–Gwe 10:00–16:00',who:'I bwy (llochesi)',whoPh:'e.e. dynion 18+, teuluoedd',beds:'Gwelyau (llochesi)',ref:'Angen atgyfeiriad? (llochesi)',
 dates:'Dyddiadau dechrau a gorffen y cynllun (mannau cynnes)',datesPh:'e.e. 1 Tach 2026 i 31 Maw 2027',offer:'Beth sydd ar gael',offerPh:'e.e. diodydd poeth, wifi, gwefru',
 yname:'Eich enw',email:'Eich e-bost',emailHint:'Er mwyn i ni wirio’r manylion gyda chi. Ni chaiff ei ddangos ar y map.',role:'Eich rôl yn y gwasanaeth',
 ok_:'Rwy’n cadarnhau bod y manylion hyn yn gywir ac y gellir eu dangos yn gyhoeddus.',req:'(gofynnol)',opt:'(dewisol)',send:'Anfon i’w adolygu',cancel:'Canslo',close:'Cau',sending:'Wrthi’n anfon…',
 ok:'Diolch. Mae eich manylion wedi’u hanfon i’w hadolygu. Byddwn yn eu gwirio cyn iddynt ymddangos ar y map.',fail:'Mae’n ddrwg gennym, methwyd anfon. Anfonwch e-bost atom:',
 offline:'Rydych chi all-lein. Rhowch gynnig arall arni pan fyddwch wedi cysylltu, neu anfonwch e-bost atom:',missing:'Llenwch y meysydd gofynnol.',bademail:'Nid yw’r cyfeiriad e-bost yn edrych yn iawn.',
 badpc:'Nid yw’r cod post yn edrych yn iawn.',wait:'Cymerwch eiliad i wirio’r manylion, yna pwyswch Anfon eto.',limit:'Rydych chi wedi anfon 3 chyflwyniad heddiw ar y ddyfais hon. Anfonwch e-bost atom:'}};
const L=()=>{try{return localStorage.getItem('lang')==='cy'?'cy':'en'}catch(e){return 'en'}};
const day=()=>new Date().toISOString().slice(0,10);
const used=()=>{try{const o=JSON.parse(localStorage.getItem('rgCount')||'{}');return o.d===day()?o.n:0}catch(e){return 0}};
const bump=()=>{try{localStorage.setItem('rgCount',JSON.stringify({d:day(),n:used()+1}))}catch(e){}};
const ov=document.createElement('div');ov.id='rgm';ov.hidden=true;ov.innerHTML='<div class="rpd" role="dialog" aria-modal="true" aria-labelledby="rgTitle"></div>';
document.body.appendChild(ov);const dlg=ov.firstChild;let at=0,opener=null;
const mail=`<a class="btn rpmail" href="mailto:${EMAIL}?subject=${encodeURIComponent('Map self-registration')}">${EMAIL}</a>`;
function msg(k,h){const m=dlg.querySelector('#rgMsg');m.className='rpmsg '+k;m.innerHTML=h;m.hidden=false;m.focus()}
const fld=(t,n,lab,req,type,ph,extra)=>`<label class="rpl" for="rg_${n}">${t[lab]} <small>${req?t.req:t.opt}</small></label><input id="rg_${n}" name="${n}" type="${type||'text'}" maxlength="300"${req?' required':''}${ph?` placeholder="${t[ph]}"`:''}${extra||''}>`;
function open(b,layer){const t=T[L()];opener=b;at=Date.now();
 dlg.innerHTML=`<div class="rphead"><h2 id="rgTitle">${t.title}</h2><button type="button" class="rpx" aria-label="${t.close}">×</button></div><p class="rph">${t.intro}</p>
 <form novalidate><fieldset><legend>${t.layer} <small>${t.req}</small></legend>
 <label class="rpr"><input type="radio" name="layer" value="Shelter" required${layer==='sh'?' checked':''}><span>${t.sh}</span></label>
 <label class="rpr"><input type="radio" name="layer" value="Warm space"${layer==='ws'?' checked':''}><span>${t.ws}</span></label></fieldset>
 ${fld(t,'name','name',1)}${fld(t,'address','address',1,'text','',' autocomplete="street-address"')}${fld(t,'postcode','postcode',1,'text','',' autocomplete="postal-code" autocapitalize="characters"')}
 ${fld(t,'phone','phone',0,'tel')}${fld(t,'website','web',0,'url')}${fld(t,'hours','hours',1,'text','hoursPh')}
 ${fld(t,'who_for','who',0,'text','whoPh')}${fld(t,'beds','beds',0)}${fld(t,'referral','ref',0)}${fld(t,'scheme_dates','dates',0,'text','datesPh')}${fld(t,'offer','offer',0,'text','offerPh')}
 ${fld(t,'contact_name','yname',1,'text','',' autocomplete="name"')}${fld(t,'email','email',1,'email','',' autocomplete="email" aria-describedby="rgEh"')}<p id="rgEh" class="rph">${t.emailHint}</p>
 ${fld(t,'role','role',0)}
 <label class="rpc"><input type="checkbox" name="confirm" required><span>${t.ok_}</span></label>
 <div class="rphp" aria-hidden="true"><label>Leave this empty<input type="text" name="_honey" tabindex="-1" autocomplete="off"></label></div>
 <div id="rgMsg" tabindex="-1" hidden></div>
 <div class="rpbtns"><button type="submit" class="btn rpsend">${t.send}</button><button type="button" class="btn rpcancel">${t.cancel}</button></div></form>`;
 ov.hidden=false;document.documentElement.classList.add('rpopen');const f=dlg.querySelector('form');
 f.onsubmit=e=>{e.preventDefault();send(f)};f.querySelector('.rpcancel').onclick=close;dlg.querySelector('.rpx').onclick=close;f.name.focus()}
async function send(f){const t=T[L()],g=n=>(f[n]&&f[n].value||'').trim(),lay=f.querySelector('input[name=layer]:checked');
 if(!lay||!g('name')||!g('address')||!g('postcode')||!g('hours')||!g('contact_name')||!g('email')||!f.confirm.checked){msg('err',`<p>${t.missing}</p>`);return}
 if(!/^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$/i.test(g('postcode'))){msg('err',`<p>${t.badpc}</p>`);f.postcode.focus();return}
 if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(g('email'))){msg('err',`<p>${t.bademail}</p>`);f.email.focus();return}
 if(Date.now()-at<MIN_MS){msg('err',`<p>${t.wait}</p>`);return}
 if(g('_honey')){msg('ok',`<p>${t.ok}</p>`);return}
 if(used()>=MAX_PER_DAY){msg('err',`<p>${t.limit}</p>${mail}`);return}
 if(!navigator.onLine){msg('err',`<p>${t.offline}</p>${mail}`);return}
 const p={_subject:'Self-registration ('+lay.value+'): '+g('name'),_template:'table',_captcha:'false',_honey:'',status:'FOR REVIEW – not on the map',layer:lay.value};
 ['name','address','postcode','phone','website','hours','who_for','beds','referral','scheme_dates','offer','contact_name','email','role'].forEach(n=>p[n]=g(n));
 Object.assign(p,{confirmed_public:'Yes',page_url:location.href,language:L(),timestamp:new Date().toISOString()});
 if(window.__rgTest){window.__rgTest(p);bump();msg('ok',`<p>${t.ok}</p>`);return}  // test hook: never posts
 const b=f.querySelector('.rpsend');b.disabled=true;b.textContent=t.sending;
 try{const r=await fetch(ENDPOINT,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify(p)});
  const j=await r.json().catch(()=>({}));if(!r.ok||String(j.success)==='false')throw 0;bump();f.querySelectorAll('input,.rpsend').forEach(x=>x.disabled=true);b.textContent=t.send;msg('ok',`<p>${t.ok}</p>`)}
 catch(e){b.disabled=false;b.textContent=t.send;msg('err',`<p>${navigator.onLine?t.fail:t.offline}</p>${mail}`)}}
function close(){ov.hidden=true;document.documentElement.classList.remove('rpopen');dlg.innerHTML='';if(opener)opener.focus()}
document.addEventListener('click',e=>{const b=e.target.closest('#xadd');if(!b)return;e.preventDefault();open(b)});
ov.addEventListener('click',e=>{if(e.target===ov)close()});document.addEventListener('keydown',e=>{if(!ov.hidden&&e.key==='Escape')close()});
window.__register={open,ENDPOINT};
})();
