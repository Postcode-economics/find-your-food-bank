/* Display-only opening-times lines (Dean, 31 Oct 2026).
   Rewrites each free-text line into the same style as the structured table:
   short day name(s) plus 24-hour HH:MM–HH:MM. Does not read or write stored data.
   A line that is not a clear day and time is returned unchanged. Exact duplicate
   lines are dropped after normalising. Two different times for the same day both stay. */
(function(){
const SHORT=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const DAY='mon(?:day)?s?|tues(?:day)?s?|tue|weds(?:nesday)?s?|wed(?:nesday)?s?|thurs(?:day)?s?|thu|fri(?:day)?s?|sat(?:urday)?s?|sun(?:day)?s?';
const AP='a\\.?\\s*m\\.?|p\\.?\\s*m\\.?';
const CLOCK='(?:\\d{1,2}\\s*[:.;]\\s*\\d{2}\\s*(?:'+AP+')?|\\d{1,2}\\s*(?:'+AP+')|\\d{1,2}\\s*(?:noon|midday)|noon|midday|midnight|\\d{1,2})';
const RANGE='('+CLOCK+')\\s*(?:\\-|\\u2013|\\u2014|to|until|till)\\s*('+CLOCK+')';
const FILL='from|between|the|hours|hour|of|morning|mornings|afternoon|afternoons|evening|evenings|open|opens|is|are|on|a|an|at|our|we|drop|in|session|sessions|each|every|just|currently|weekly';
const DAYGROUP='(?:'+DAY+')(?:\\s*(?:,|&|/|\\band\\b|to|through|thru|\\-|\\u2013|\\u2014)\\s*(?:'+DAY+'))*';
const CHUNK=new RegExp('('+DAYGROUP+')(?:[\\s:.,\\-\\u2013\\u2014]+|\\b(?:'+FILL+')\\b\\s*)+(closed|(?:'+RANGE+')(?:\\s*(?:,|&|and)\\s*'+RANGE+')?)','ig');
const HARD=/\b(?:appoint\w*|except|unless|alternat\w*|referral|referred|donation|weather|delivery|collection|family|aged|ages|holiday|term|phone|only\s+when)\b|\*|\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b/i;
const LEAD=/^(?:(?:opening|times|time|open|every|each|weekly|currently|just|foodbank|food|bank)\b[\s:,.\-\u2013\u2014]*)+/i;

function dayIndex(w){
  w=String(w||'').toLowerCase();
  const keys=[['monday',0],['mon',0],['tues',1],['tue',1],['weds',2],['wednes',2],['wed',2],['thurs',3],['thu',3],['fri',4],['sat',5],['sun',6]];
  for(let i=0;i<keys.length;i++) if(w.indexOf(keys[i][0])===0) return keys[i][1];
  return null;
}
function formatDays(spec){
  const rx=new RegExp('('+DAY+')|(to|through|thru|\\-|\\u2013|\\u2014)|(?:,|&|/|\\band\\b)|(\\S+)','ig');
  const toks=[]; let m;
  while((m=rx.exec(spec))){
    if(m[3]) return null; // a word that is not a day
    if(m[1]){const i=dayIndex(m[1]); if(i==null) return null; toks.push(i);}
    else if(m[2]) toks.push('to');
    else toks.push(',');
  }
  if(!toks.length) return null;
  const label=[]; const seen={};
  for(let i=0;i<toks.length;i++){
    if(toks[i]==='to'||toks[i]===',') return null;
    const a=toks[i];
    if(toks[i+1]==='to'&&typeof toks[i+2]==='number'){
      const b=toks[i+2];
      const text=SHORT[a]+'\u2013'+SHORT[b];
      if(!seen[text]){seen[text]=1; label.push(text);}
      i+=2;
    }else{
      const text=SHORT[a];
      if(!seen[text]){seen[text]=1; label.push(text);}
    }
    if(i+1<toks.length){
      if(toks[i+1]!==',') return null;
      i++;
    }
  }
  return label.length?label.join(', '):null;
}
function parseClock(tok){
  let t=String(tok||'').toLowerCase().replace(/\s+/g,'').replace(/a\.m\.?/g,'am').replace(/p\.m\.?/g,'pm');
  t=t.replace(/(\d);(\d{2})/g,'$1:$2');
  if(/^(?:12(?::00|\.00)?)?(?:noon|midday)$/.test(t)||t==='noon'||t==='midday') return {fixed:12*60};
  if(t==='midnight') return {fixed:0};
  const m=t.match(/^(\d{1,2})(?:[:.](\d{2}))?(am|pm)?$/);
  if(!m) return null;
  let h=+m[1], mi=m[2]?+m[2]:0, ap=m[3]||null;
  if(mi>59||h>23) return null;
  if(ap){
    if(h>12){if(ap!=='pm') return null; return {fixed:h*60+mi};}
    if(h===0) return null;
    if(ap==='pm'&&h<12) h+=12;
    if(ap==='am'&&h===12) h=0;
    return {fixed:h*60+mi};
  }
  if(h>12) return {fixed:h*60+mi};
  if(h===0) return {fixed:mi};
  if(h===12) return {fixed:12*60+mi}; // obvious daytime reading: noon, not midnight
  return {am:h*60+mi, pm:(h+12)*60+mi};
}
function hhmm(mins){mins=((mins%1440)+1440)%1440; return String(Math.floor(mins/60)).padStart(2,'0')+':'+String(mins%60).padStart(2,'0');}
function resolve(a,b){
  const A=parseClock(a), B=parseClock(b);
  if(!A||!B) return null;
  const as=A.fixed!=null?[A.fixed]:[A.am,A.pm], bs=B.fixed!=null?[B.fixed]:[B.am,B.pm];
  const cands=[];
  for(let i=0;i<as.length;i++) for(let j=0;j<bs.length;j++){
    const s=as[i], e=bs[j];
    if(e>s&&e-s<=16*60) cands.push([s,e]);
    else if(A.fixed!=null&&B.fixed!=null&&s>=12*60&&e<s&&(1440-s+e)<=16*60) cands.push([s,e]); // explicit overnight only
  }
  if(cands.length!==1) return null; // still two daytime readings, or none: do not guess
  return cands[0];
}
function overlap(slots){
  const s=slots.slice().sort(function(a,b){return a[0]-b[0];});
  for(let i=1;i<s.length;i++) if(s[i][0]<s[i-1][1]) return true;
  return false;
}
function gapOk(g){return !g||/^[\s|,;/\-\u2013\u2014]*$/.test(g);}
function tryParse(original){
  let s=String(original||'').replace(/\s+/g,' ').trim();
  if(!s) return null;
  s=s.replace(LEAD,'').trim();
  const notes=[];
  s=s.replace(/\(([^)]*)\)/g,function(m,inner){
    const t=inner.trim();
    if(/^monthly$/i.test(t)){notes.push('Monthly'); return ' ';}
    if(/^fortnightly$/i.test(t)){notes.push('Fortnightly'); return ' ';}
    return m;
  });
  if(/\([^)]*\)/.test(s)) return null;
  if(/\bmonthly\b/i.test(s)){notes.push('Monthly'); s=s.replace(/\bmonthly\b/ig,' ');}
  if(/\bfortnightly\b/i.test(s)){notes.push('Fortnightly'); s=s.replace(/\bfortnightly\b/ig,' ');}
  if(HARD.test(s)) return null;
  const note=notes.length?' '+notes.filter(function(n,i){return notes.indexOf(n)===i;}).join(' '):'';
  const parts=[]; let pos=0, m;
  CHUNK.lastIndex=0;
  while((m=CHUNK.exec(s))){
    if(!gapOk(s.slice(pos,m.index))){CHUNK.lastIndex=0; return null;}
    const days=formatDays(m[1]);
    if(!days){CHUNK.lastIndex=0; return null;}
    let body;
    if(/^closed$/i.test(m[2])) body='Closed';
    else{
      const slots=[];
      const r1=resolve(m[3],m[4]);
      if(!r1){CHUNK.lastIndex=0; return null;}
      slots.push(r1);
      if(m[5]){
        const r2=resolve(m[5],m[6]);
        if(!r2){CHUNK.lastIndex=0; return null;}
        slots.push(r2);
      }
      if(overlap(slots)){CHUNK.lastIndex=0; return null;}
      body=slots.map(function(r){return hhmm(r[0])+'\u2013'+hhmm(r[1]);}).join(', ');
    }
    parts.push(days+' '+body+note);
    pos=m.index+m[0].length;
    if(m.index===CHUNK.lastIndex) CHUNK.lastIndex++;
  }
  CHUNK.lastIndex=0;
  if(!parts.length||!gapOk(s.slice(pos))) return null;
  return parts;
}
function clean(s){return String(s==null?'':s).replace(/\s+/g,' ').trim();}
function formatLine(raw){
  const original=clean(raw);
  if(!original) return [];
  return tryParse(original)||[original];
}
function lines(arr){
  const out=[], seen={};
  (arr||[]).forEach(function(raw){
    formatLine(raw).forEach(function(p){
      const k=clean(p);
      if(!k||seen[k]) return;
      seen[k]=1; out.push(k);
    });
  });
  return out;
}
window.timesFmt={lines:lines, formatLine:formatLine, tryParse:tryParse};
})();

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
 // null = that day is not listed (unknown). [] = the source says closed. Ranges = open. Never treat a missing day as closed.
 if(layer==='fb'){const t=i.opening_times;if(!t||t.status!=='TIMES_FOUND'||(!t.structured&&!t.all_closed))return null;
  if(t.notes&&Object.values(t.notes).some(n=>/monthly|fortnight/i.test(n)))return null;
  const s={};for(let d=0;d<7;d++)s[d]=null;let known=false;
  const closed=t.all_closed?['mon','tue','wed','thu','fri','sat','sun']:(t.closed||[]);
  for(const k of closed){const d=DI[k];if(d==null)continue;s[d]=[];known=true}
  for(const[k,v]of Object.entries(t.structured||{})){const d=DI[k];if(d==null)continue;s[d]=[];(v||[]).forEach(([a,b])=>{a=hm(a);b=hm(b);if(a!=null&&b!=null)s[d].push([a,b<=a?b+1440:b])});if(s[d].length)known=true}
  return known?s:null}
 const h=i.hours;if(!h)return null;const s={};for(let d=0;d<7;d++)s[d]=null;
 if(typeof h==='object'){let any=false;for(const[k,v]of Object.entries(h)){const d=DI[String(k).toLowerCase().slice(0,3)];if(d==null)continue;if(/monthly|fortnight|alternate|1st|2nd|3rd|last/i.test(v))return null;
  if(/^closed$/i.test(String(v).trim())){s[d]=[];any=true;continue}const r=rng(v);if(!r.length)return null;s[d]=r;any=true}return any?s:null}
 const str=normH(h);if(/^24\/7$/.test(str)){for(let d=0;d<7;d++)s[d]=[[0,1440]];return s}
 if(/PH|SH|week|easter|dawn|dusk|sunrise|sunset|"/i.test(str))return null;let any=false;
 for(const part of str.split(/\s*;\s*/)){const m=/^((?:(?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?,?)+)\s+(.+)$/.exec(part.trim());if(!m)return null;
  const days=[];m[1].split(',').filter(Boolean).forEach(x=>{const[a,b]=x.split('-').map(y=>DI[y.toLowerCase()]);if(b==null)days.push(a);else for(let d=a;;d=(d+1)%7){days.push(d);if(d===b)break}});
  if(/^off|closed$/i.test(m[2].trim())){days.forEach(d=>{s[d]=[]});any=true;continue}
  const r=[];for(const x of m[2].split(',')){const q=/^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$/.exec(x.trim());if(!q)return null;const a=hm(q[1]),b=hm(q[2]);r.push([a,b<=a?b+1440:b])}
  days.forEach(d=>{s[d]=r});any=true}
 return any?s:null}
const p2=n=>String(n).padStart(2,'0'),clk=m=>{m=((m%1440)+1440)%1440;return p2(Math.floor(m/60))+':'+p2(m%60)};
function clockNow(now){return now||(typeof window.pageNow==='function'?window.pageNow():new Date())}
// What the card actually prints. 'table' = a day table, 'text' = free-text lines, false = nothing to show.
function cardShowsTimes(layer,i){
 if(layer==='fb'){const t=i.opening_times;if(!t)return false;
  if(t.status==='TIMES_FOUND'&&((t.structured&&Object.keys(t.structured).length)||t.all_closed))return 'table';
  if(t.status==='TIMES_TEXT_ONLY'&&(t.raw||(t.lines&&t.lines.length)))return 'text';
  return false}
 const h=i.hours;if(!h)return false;
 if(typeof h==='string'){const s=h.trim();if(!s||/^by referral\b|^self-referral\b/i.test(s))return false;return 'text'}
 if(typeof h==='object'&&Object.keys(h).length)return 'table';
 return false}
function dateCaution(layer,i){
 if(layer==='fb'){const n=i.opening_times&&i.opening_times.notes;return !!(n&&Object.values(n).some(x=>/monthly|fortnight/i.test(x)))}
 const h=i.hours;if(!h)return false;const blob=typeof h==='string'?h:Object.values(h).join(' ');return /monthly|fortnight/i.test(blob)}
// Next listed opening when today itself is not in the table. Skips days the source never mentions. Never calls them closed.
function nextListed(s,now){const d=now.getDay();
 for(let k=1;k<=6;k++){const dd=(d+k)%7,slots=s[dd];if(!slots||!slots.length)continue;const c=slots.slice().sort((x,y)=>x[0]-y[0])[0];if(c)return{dd:dd,at:c[0],to:c[1]}}
 return null}
function status(layer,i,now){now=clockNow(now);if(i.upcoming)return{st:'closed',day:null};
 const show=cardShowsTimes(layer,i);
 if(dateCaution(layer,i)&&show)return{st:'unknown',why:'dates'}; // monthly/fortnightly: times are listed, the date is not
 if(i.call_check){const s=sched(layer,i); // carried copy: do not claim open or closed from the clock
  if(show==='table'&&s&&s[now.getDay()]==null){const n=nextListed(s,now);if(n)return{st:'unknown',why:'next',dd:n.dd,at:n.at,to:n.to}}
  if(show)return{st:'unknown',why:'text'};
  return{st:'unknown'}}
 const s=sched(layer,i);if(!s)return show?{st:'unknown',why:'text'}:{st:'unknown'};const d=now.getDay(),m=now.getHours()*60+now.getMinutes();
 const prev=s[(d+6)%7];if(prev)for(const[a,b]of prev)if(b>1440&&m<b-1440)return{st:'open',until:b-1440};
 if(s[d]==null){const n=show==='table'?nextListed(s,now):null;if(n)return{st:'unknown',why:'next',dd:n.dd,at:n.at,to:n.to};return show?{st:'unknown',why:'text'}:{st:'unknown'};}
 for(const[a,b]of s[d])if(m>=a&&m<b)return{st:'open',until:b,next24:b-a>=1440};
 for(let k=0;k<8;k++){const dd=(d+k)%7;if(s[dd]==null)return{st:'closed',day:null};const c=s[dd].filter(([a])=>k>0||a>m).sort((x,y)=>x[0]-y[0])[0];if(c)return{st:'closed',day:k===0?'today':k===1?'tomorrow':dd,dd,at:c[0],to:c[1]}}
 return{st:'closed',day:null}}
function badge(layer,i){if(i&&i.card_type==='referral_hostel')return `<div class="v3st unk" role="note">${B("Referral needed, don't turn up without one",'Angen atgyfeiriad, peidiwch â throi i fyny heb un')}</div>`;let html=_badge(layer,i);if(layer==='sh'&&i&&i.kind==='day_centre')html=html.replace(/open tonight/ig,'open').replace(/\btonight\b/ig,'');return html}
function _badge(layer,i){const r=status(layer,i);
 if(r.st==='open')return `<div class="v3st open" role="note">${r.next24||(r.until===1440&&sched(layer,i)[0][0]&&false)?B('OPEN NOW','AR AGOR NAWR'):B('OPEN NOW until '+clk(r.until),'AR AGOR NAWR tan '+clk(r.until))}</div>`;
 if(r.st==='closed'){if(r.day==null)return `<div class="v3st shut" role="note">${B('Closed','Ar gau')}</div>`;
  const de=r.day==='today'?'today':r.day==='tomorrow'?'tomorrow':DEN[r.day],dc=r.day==='today'?'heddiw':r.day==='tomorrow'?'yfory':DCY[r.day];
  return `<div class="v3st shut" role="note">${B(`Closed · Next open <b>${DEN[r.dd]} ${clk(r.at)}–${clk(r.to)}</b>`,`Ar gau · Ar agor nesaf <b>${DCY[r.dd]} ${clk(r.at)}–${clk(r.to)}</b>`)}</div>`}
 if(layer==='sh'&&i.access_type==='referral_only')return `<div class="v3st unk" role="note">${B('Referral needed / check before you go','Angen atgyfeiriad / gwiriwch cyn mynd')}</div>`;
 if(layer==='sh'&&window.REFONLY&&REFONLY(i))return `<div class="v3st unk" role="note">${B('By referral – call before you go','Drwy atgyfeiriad – ffoniwch cyn mynd')}</div>`;
 if(i.carried_note&&i.carried_since){const cd=esc3(i.last_confirmed||i.carried_since);return `<div class="v3st unk carried" role="note">${B(`Not re-confirmed since ${cd} – call before you go`,`Heb ei ail-gadarnhau ers ${cd} – ffoniwch cyn mynd`)}</div>`}  // carry-forward (Dean 28 Oct)
 if(r.why==='dates')return `<div class="v3st unk" role="note">${B('Check dates – call before you go','Gwiriwch y dyddiadau – ffoniwch cyn mynd')}</div>`;
 if(r.why==='next')return `<div class="v3st unk" role="note">${B(`Next open: ${DEN[r.dd]} ${clk(r.at)}–${clk(r.to)} – call before you go`,`Ar agor nesaf: ${DCY[r.dd]} ${clk(r.at)}–${clk(r.to)} – ffoniwch cyn mynd`)}</div>`;
 if(r.why==='text')return `<div class="v3st unk" role="note">${B('Check times below – call before you go','Gwiriwch yr amseroedd isod – ffoniwch cyn mynd')}</div>`;
 return `<div class="v3st unk" role="note">${B('Times unknown – call before you go','Amseroedd heb eu rhestru – ffoniwch cyn mynd')}</div>`}
const walk=km=>{if(km==null)return'';const min=Math.max(1,Math.round(km*1.3/4.8*60));// est.: straight line x1.3 at 4.8 km/h
 if(min>120)return'';
 return `<div class="v3wk">${IC('walk')}${B(`About ${min} min walk (est.)`,`Tua ${min} munud o gerdded (amcan.)`)}</div>`};
const share=i=>`<button type="button" class="btn v3share" data-n="${e_(i.name)}" data-a="${e_(i.address)}${i.postcode&&!(i.address||'').includes(i.postcode)?', '+e_(i.postcode):''}" data-ll="${i.lat},${i.lng}">${B('Share / text this address','Rhannu / tecstio’r cyfeiriad hwn')}</button>`;
const strip=()=>`<div class="v3sos" role="note">${B('<b>Sleeping rough, or worried about someone who is?</b> In England and Wales, tell StreetLink. <b>In danger? Call 999.</b><span class="sosb"><a class="sosl" href="https://streetlink.org.uk" target="_blank" rel="noopener">streetlink.org.uk</a><a class="sosl s999" href="tel:999">'+IC('phone')+'Call 999</a></span><details class="hlp"><summary>More free helplines</summary><ul><li><b>Shelter</b> housing advice (England): <a href="tel:08088004444" aria-label="Call 0808 800 4444">0808 800 4444</a>, Mon–Fri 8am–5pm</li><li><b>National Domestic Abuse Helpline</b> (England): <a href="tel:08082000247" aria-label="Call 0808 2000 247">0808 2000 247</a>, 24 hours</li><li><b>Live Fear Free</b> (Wales): <a href="tel:08088010100" aria-label="Call 0808 80 10 100">0808 80 10 100</a>, 24 hours</li><li><b>Samaritans</b>: <a href="tel:116123" aria-label="Call 116 123">116 123</a>, 24 hours</li></ul></details>',
 '<b>Yn cysgu allan, neu’n poeni am rywun sydd?</b> Yng Nghymru a Lloegr, rhowch wybod i StreetLink. <b>Mewn perygl? Ffoniwch 999.</b><span class="sosb"><a class="sosl" href="https://streetlink.org.uk" target="_blank" rel="noopener">streetlink.org.uk</a><a class="sosl s999" href="tel:999">'+IC('phone')+'Ffonio 999</a></span><details class="hlp"><summary>Rhagor o linellau cymorth am ddim</summary><ul><li><b>Shelter</b> cyngor tai (Lloegr): <a href="tel:08088004444" aria-label="Ffoniwch 0808 800 4444">0808 800 4444</a>, Llun–Gwener 8am–5pm</li><li><b>Llinell Gymorth Genedlaethol Cam-drin Domestig</b> (Lloegr): <a href="tel:08082000247" aria-label="Ffoniwch 0808 2000 247">0808 2000 247</a>, 24 awr</li><li><b>Byw Heb Ofn</b> (Cymru): <a href="tel:08088010100" aria-label="Ffoniwch 0808 80 10 100">0808 80 10 100</a>, 24 awr</li><li><b>Samaritans</b>: <a href="tel:116123" aria-label="Ffoniwch 116 123">116 123</a>, 24 awr</li></ul></details>')}</div>`;
const shutToday=(layer,i,now)=>{now=clockNow(now);if(i.upcoming)return true;if(i.call_check)return false;const s=sched(layer,i);const day=s&&s[now.getDay()];return !!(day&&!day.length)};  // explicit closed only; a day that is not listed stays on the list. ?testdate= uses pageNow.
const openTodayL=(layer,i,now)=>{now=clockNow(now);if(i.upcoming||i.call_check)return false;const s=sched(layer,i);return !!(s&&(s[now.getDay()]||[]).length)};
window.V3={sched,status,badge,walk,share,strip,shutToday,openTodayL};
// ---- food bank card + pop-up: status first, walking time, share. Donation-only sites get no open/closed badge (no client hours).
const insAfterD=(h,add)=>/<div class="d">[^<]*<\/div>/.test(h)?h.replace(/(<div class="d">[^<]*<\/div>)/,'$1'+add):h.replace(/(<\/h3>)/,'$1'+add);
const oc=window.card;window.card=function(i,d){let h=oc.apply(this,arguments);if(nc(i))return insAfterD(h,walk(d));
 h=badge('fb',i)+insAfterD(h,walk(d));
 /* 28 Oct QA F3: a no-phone card's only contact button (Facebook "Send a message") sat after Share, below the fold of the mobile sheet. It now comes straight after Directions, before Share. */
 const fbm=h.match(/<a class="btn call xfbk"[\s\S]*?<\/a>/);if(fbm)h=h.replace(fbm[0],'');
 return h.replace(/(<a class="btn gm"[^>]*>[^<]*<\/a>)/,'$1'+(fbm?fbm[0]:'')+share(i))};
const op=window.pop;window.pop=function(i){let h=op.apply(this,arguments);return nc(i)?h:h.replace('<div class="pop">','<div class="pop">'+badge('fb',i)).replace(/(<a class="btn gm"[^>]*>[^<]*<\/a>)/,'$1'+share(i))};  // Dean 25 Oct design lock: pop-up has Share too
const on0=window.nearest;window.nearest=function(){const r=on0.apply(this,arguments);try{const l=document.getElementById('list'),cs=[...l.querySelectorAll(':scope>.card')];
 const sc=c=>{const i=items[+c.dataset.k];if(!i||nc(i))return 1;return({open:0,unknown:1,closed:2})[status('fb',i).st]};
 cs.map((c,n)=>({c,n,s:sc(c)})).sort((a,b)=>a.n-b.n).forEach(x=>{x.c.classList.toggle('v3closed',x.s===2);l.append(x.c)})}catch(e){}return r};
// ---- top: three big task buttons; toggle bar + search become secondary
const hdr=document.querySelector('header');const big=document.createElement('div');big.id='v3big';
const NB=[['fb','food','Food bank','Banc bwyd','Collect food','Casglu bwyd'],['ws','mug','Warm space','Man cynnes','Somewhere warm','Rhywle cynnes'],['sh','bed','Shelter','Lloches','A bed tonight','Gwely heno']];
big.setAttribute('role','radiogroup');big.setAttribute('aria-label','Find help near you');
big.innerHTML=NB.map(([k,ic,en,cy,sen,scy])=>`<button type="button" class="v3b" role="radio" data-l="${k}" aria-checked="false" tabindex="-1"><span class="ic" aria-hidden="true">${IC(ic)}</span><span class="v3bt"><span class="v3bl">${B(en,cy)}</span><span class="v3bs">${B(sen,scy)}</span></span><span class="v3tick" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 12.5l5 5 10-11"/></svg></span><span class="v3sr">${B(', selected',', wedi’i ddewis')}</span></button>`).join('');
{const f=document.getElementById('f');if(f){hdr.querySelector('h1').after(f);f.after(big)}else hdr.querySelector('h1').after(big)}
const sos=document.createElement('div');sos.id='v3sos';sos.hidden=true;sos.innerHTML=strip();big.after(sos);
const near=document.getElementById('xnear');if(near)near.hidden=true;
// UK clock (Europe/London) for the night cue and night theme; ?clock=20:00 fakes it for tests
const ukH=()=>{const q=new URLSearchParams(location.search).get('clock');if(q&&/^\d{1,2}:\d{2}$/.test(q))return +q.split(':')[0]+(+q.split(':')[1])/60;
 const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date());return +p.find(x=>x.type==='hour').value+(+p.find(x=>x.type==='minute').value)/60};
window.V3.ukH=ukH;

function mark(k){document.documentElement.dataset.v3k=k;/* 28 Oct QA B1: CSS shows only the chosen type's 'Nearest' list */document.querySelectorAll('.v3b').forEach(b=>{const on=b.dataset.l===k;b.setAttribute('aria-checked',String(on));b.tabIndex=on?0:-1});try{localStorage.setItem('v3layer',k)}catch(e){};document.querySelectorAll('#chips [data-f]').forEach(e=>{e.classList.toggle('v3off',k!=='fb');e.inert=k!=='fb';e.setAttribute('aria-disabled',String(k!=='fb'))});['fwrap','ftab','fhide'].forEach(id=>{const e=document.getElementById(id);if(e){e.inert=false;e.classList.remove('v3off');e.removeAttribute('aria-disabled')}})}  /* 25 Oct live bug: only the food-bank-only chips dim; the ✕ and the Filters tab always work */  // round 4: food bank filters dim (not vanish) for the other types: no blank gap, no shift  // round 2: filter row lives above the results (below the map), so hiding it never moves the buttons or the map
function want(k,noGo){window.v3focus=k;const on=b=>b.getAttribute('aria-pressed')==='true';
 ['fb','sh','ws'].forEach(x=>{const b=document.querySelector(`.xt[data-l=${x}]`);if(b&&on(b)!==(x===k))b.click()});
 mark(k);if(noGo)return;window.__go=false;
 // UX 22 Oct (Dean): a type tap never moves the page or asks for location; it re-runs the current search in place at once (no 900ms delay)
 // and the 'results updated' pill below the buttons says what changed, with a link down to the list
 let s=null;try{s=JSON.parse(localStorage.getItem('lastSearch')||'null')}catch(e){}
 const p=LN()||(s&&typeof s.lat==='number'?[s.lat,s.lng,s.label]:null);
 if(p){busy(k);const ln0=LN(),run=()=>{if(window.v3focus!==k)return;if(LN()!==ln0){busy(null);pill(k);return}  /* 25 Oct: a newer search landed before this deferred re-run (rAF can lag): never overwrite it with the old place */
 const y=scrollY;nearest(p[0],p[1],p[2],p[3]);if(scrollY!==y)scrollTo({top:y,behavior:'auto'});pill(k)};requestAnimationFrame(()=>setTimeout(run,0))}  // round 4: the pressed state paints first, then the list re-runs
 else{busy(null);pill(k)}}  // before any search: just select; the pill line (space always reserved) asks for a postcode
const LN=()=>{try{return typeof lastNear!=='undefined'&&lastNear?lastNear:null}catch(e){return null}};  // index.html's script-level let
// ---- 'results updated' pill (aria-live) + pressed/loading state
const pl=document.createElement('div');pl.id='v3pill';pl.setAttribute('aria-live','polite');pl.setAttribute('role','status');big.after(pl);setTimeout(()=>pill(),0);
let busyT=0;function busy(k){const b=big.querySelector(`.v3b[data-l=${k}]`);big.querySelectorAll('.v3b').forEach(x=>{x.classList.remove('v3busy');x.removeAttribute('aria-busy')});
 if(!b)return;b.classList.add('v3busy');b.setAttribute('aria-busy','true');clearTimeout(busyT);busyT=setTimeout(()=>pill(k),8000)}
const tgt=k=>document.getElementById(k==='fb'?'list':'xlist');
function pill(k,auto){if(auto&&window.__v3err)return;  /* 28 Oct QA B2: list redraws never hide a search error */
 k=k||window.v3focus||'fb';const t=tgt(k);if(!t||!LN()){const W0={fb:['food banks','banc bwyd'],ws:['warm spaces','man cynnes'],sh:['shelters','lloches']}[k];pl.innerHTML=`<span class="v3ph">${B(`Showing ${W0[0]}. Enter a postcode or town above, or tap the pin, to see the nearest.`,`Yn dangos ${W0[1]}. Rhowch god post neu dref uchod, neu tapiwch y pin, i weld y rhai agosaf.`)}</span>`;flash();return}
 const n=t.querySelectorAll('.card').length;if(k!=='fb'&&!n&&!t.textContent.trim())return;  // layer data still loading: stay busy, the observer calls again
 big.querySelectorAll('.v3b').forEach(x=>{x.classList.remove('v3busy');x.removeAttribute('aria-busy')});clearTimeout(busyT);
 const W={fb:['food banks','banc bwyd'],ws:['warm spaces','man cynnes'],sh:['shelters','lloches']}[k];
 {/* Dean 25 Oct 13:32: short status line, never clipped: 'Food banks near you' / 'Food banks near Suffolk' (place ellipsised only if needed) */
 const T={fb:['Food banks','Banciau bwyd'],ws:['Warm spaces','Mannau cynnes'],sh:['Shelters','Llochesi']}[k];let lb='';try{lb=(typeof lastNear!=='undefined'&&lastNear&&lastNear[2])||''}catch(_){}
 lb=v3short(lb);const me=!lb||/^your location$/i.test(lb),P=x=>`<span class="v3plc">${esc3(x)}</span>`;
 pl.innerHTML=`<a href="#${t.id}" class="v3pl">${me?B(`${T[0]} near you`,`${T[1]} yn agos atoch`):B(`${T[0]} near ${P(lb)}`,`${T[1]} ger ${P(lb)}`)}</a>`;pl.dataset.place=me?'':lb;v3fitPill()}flash()}
/* Dean 25 Oct 13:35: fixed font, ONE line, fixed header height, never an ellipsis. If 'Food banks near Place' does not fit,
   show just the place name (the selected type tile already shows the type). The font size is never changed. */
/* Dean 25 Oct 14:09: status line place name. Drop ', County'. Over-long council names use a short form (confirmed by Dean 14:11; edit here). Never cut off. */
const V3SHORT={'Armagh City, Banbridge and Craigavon':'Craigavon','Bournemouth, Christchurch and Poole':'Bournemouth'};
window.v3short=v3short;function v3short(lb){lb=String(lb||'').trim();if(V3SHORT[lb])return V3SHORT[lb];const i=lb.indexOf(',');return i>0?lb.slice(0,i).trim():lb}
function v3fitPill(){const a=pl.querySelector('.v3pl');if(!a||!pl.dataset.place)return;if(a.scrollWidth>a.clientWidth+1)
 a.querySelectorAll('.v-en,.v-cy').forEach(e=>{e.innerHTML=`<span class="v3plc">${esc3(pl.dataset.place)}</span>`})}
addEventListener('resize',()=>{if(window.v3fitPill&&pl.querySelector('.v3pl'))v3fitPill()});
function esc3(x){return String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c])}
function flash(){pl.classList.remove('v3flash');void pl.offsetWidth;pl.classList.add('v3flash');
 ['#list>.lh','#xlist>.lh'].forEach(q=>{const h=document.querySelector(q);if(h){h.classList.remove('v3flash');void h.offsetWidth;h.classList.add('v3flash')}})}  // brief pulse: every update (incl. the same search again or re-tapping the chosen type) is visible
// one shared scroll (Dean 25 Oct): the 'see list' pill, Search/Enter, place picks and Find nearest all land the chosen type's list at the top, no map above it
function scrollList(k){k=k||window.v3focus||'fb';const t=tgt(k);if(!t)return false;const sosE=document.getElementById('v3sos'),h=(k==='sh'&&sosE&&!sosE.hidden)?sosE:(t.querySelector('.lh')||t);h.style.scrollMarginTop='12px';h.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});return true}
window.v3scrollList=scrollList;
pl.addEventListener('click',e=>{const a=e.target.closest('a.v3pl');if(!a)return;e.preventDefault();if(!tgt(window.v3focus))return;scrollList(window.v3focus);
 const c=t.querySelector('.card a,.card button,.card h3');if(c)setTimeout(()=>{(t.querySelector('.lh')||t).setAttribute('tabindex','-1');(t.querySelector('.lh')||t).focus({preventScroll:true})},400)});
{const ob=new MutationObserver(()=>{if(LN())pill(window.v3focus,true)});['list','xlist'].forEach(id=>{const e=document.getElementById(id);if(e)ob.observe(e,{childList:true})})}
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
/* Dean 25 Oct 19:17: if storage is blocked (Instagram in-app browser), a read must be FALSE, never undefined - classList.toggle(c, undefined)
   ADDS the class, which switched 'List only' on and hid the map. */
const pref=(k,v)=>{if(v===undefined){try{return localStorage.getItem(k)==='1'}catch(e){return false}}try{localStorage.setItem(k,v?'1':'0')}catch(e){}};
function setP(id,cls,on){on=on===true;document.documentElement.classList.toggle(cls,on);document.getElementById(id).setAttribute('aria-pressed',String(on));pref(cls,on);if(cls==='nomap'&&!on)setTimeout(()=>window.mapFix?mapFix():map.invalidateSize(),50)}
document.getElementById('v3list').onclick=()=>setP('v3list','nomap',!document.documentElement.classList.contains('nomap'));
document.getElementById('v3light').onclick=()=>setP('v3light','light',!document.documentElement.classList.contains('light'));
setP('v3list','nomap',pref('nomap'));
{let m=null;try{m=localStorage.getItem('light')}catch(e){}
 if(m==='1'||m==='0')setP('v3light','light',m==='1');
 else{/* Dean 25 Oct 17:05: first visit (no saved choice) is always DARK, whatever the phone setting */document.documentElement.classList.remove('light');document.getElementById('v3light').setAttribute('aria-pressed','false')}}
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
// 27 Oct 2026: moving the map into the split runs one frame later, so the header rebuild above and the map move are separate iPhone frames.
requestAnimationFrame(()=>setTimeout(()=>{const m=document.getElementById('map'),sp=document.createElement('div'),col=document.createElement('div');sp.id='v3split';col.id='v3col';m.before(sp);sp.append(m,col);
 let n=sp.nextElementSibling;while(n&&!(n.classList&&n.classList.contains('share'))&&n.tagName!=='FOOTER'){const nx=n.nextElementSibling;col.append(n);n=nx}
 const xb=document.getElementById('xbefore'),fw=document.getElementById('fwrap'),ft=document.getElementById('ftab'),chg=document.getElementById('v3chg');
 col.prepend(chg);  // round 3 (Dean): filters, 'Always call' and List only/Light mode back above the map, right under the type buttons
 {const fl=document.createElement('div');fl.id='v3filt';const r2=document.createElement('div');r2.id='v3row2';const tl=document.getElementById('v3tools');r2.append(...[xb].filter(Boolean));const ot=document.querySelector('label.tog');if(ot)ot.id='v3open';fl.append(...[fw,ot,tl,ft,r2].filter(Boolean));fl.classList.toggle('fclosed',!!window.fbFiltersClosed);{const al=()=>{const o=document.getElementById('v3open'),t=document.getElementById('v3tools');if(o)o.style.removeProperty('margin-left');if(t){t.style.removeProperty('order');t.classList.remove('v3tight')}};setTimeout(al,0);window.v3align=al}  /* header option A (Dean 25 Oct): layout is pure CSS (header.css) */big.after(fl);
    if(ot){const vr=document.getElementById('v3res'),mq=matchMedia('not all'),place=()=>{if(mq.matches){if(ot.parentElement!==vr)vr.prepend(ot)}else if(ot.parentElement!==fl)fl.insertBefore(ot,tl)};place();mq.addEventListener('change',place)}  // MD4: Open today sits with the chips where it fits (>=340px); below 340px it stays above the list so the map isn't pushed down
    const pr=document.createElement('div');pr.id='v3prow';fl.after(pr);pr.append(pl)}  // filters + 'Always call' + tools stay directly under the type buttons (Dean); pill row follows
 const xl=document.getElementById('xlist'),so=document.getElementById('v3sos');if(xl&&so)xl.before(so);
 setTimeout(()=>map.invalidateSize(),0);matchMedia('(min-width:1024px)').addEventListener('change',()=>setTimeout(()=>map.invalidateSize(),50))},0));

// ---- round 4: messages never push the map; offline helpers
(function(){const note=document.createElement('div');note.id='v3note';note.setAttribute('role','status');note.setAttribute('aria-live','polite');
 const chg=document.getElementById('v3chg');(chg||document.getElementById('v3res')).after(note);
 const om=window.msg;window.msg=function(t,err){om.apply(this,arguments);const has=!!t;
  window.__v3err=!!(err&&has);
  if(err&&has){pl.innerHTML=`<span class="v3err" role="alert">${e_(t)}</span>`}  // errors take the reserved pill slot: no layout shift. A failed search clears the old results first (index.html noResults, 28 Oct QA B2)
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

/* Header option A (Dean, 25 Oct 2026): type tiles, then filters, then 'Find nearest', then one info strip
   (see-list line + Always call before you go + Updated). Built once the pieces exist; behaviour unchanged. */
(function(){function h2(){const big=document.getElementById('v3big'),filt=document.getElementById('v3filt'),pill=document.getElementById('v3pill'),xb=document.getElementById('xbefore'),fr=document.querySelector('header .fresh'),near=document.getElementById('xnear');
 if(!big||!filt||!pill||!xb||!fr||!near)return false;if(document.getElementById('h2info'))return true;
 big.after(filt);filt.after(near);const info=document.createElement('div');info.id='h2info';near.after(info);info.append(pill,xb,fr);return true}
 if(h2())return;const mo=new MutationObserver(()=>{if(h2())mo.disconnect()});mo.observe(document.documentElement,{childList:true,subtree:true});setTimeout(()=>{h2();mo.disconnect()},15000)})();
