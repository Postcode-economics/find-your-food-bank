/* Emergency shelter preview. Runs only after index.html adds html.em-preview for ?preview=emergency.
   House pictogram: UN OCHA Humanitarian Icons, House.svg, CC0 1.0.
   https://github.com/UN-OCHA/humanitarian-icons */
(function(){
if(!document.documentElement.classList.contains('em-preview'))return;
var HOUSE='M18.66437.2525a1.00028,1.00028,0,0,0-1.32874,0l-17.008,15.45A1,1,0,0,0,0,16.44266v27.5574H14v-10a2.00588,2.00588,0,0,1,2-2h4a2.00588,2.00588,0,0,1,2,2v10H36V16.44266a1,1,0,0,0-.32761-.7402Z';
var TERMS=['emergency shelter','rest centre','power cut','emergency','evacuation','evacuate','earthquake','flood','storm','fire','gas'];
var PHONE='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1C10.61 21 3 13.39 3 4c0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg>';
var qs=new URLSearchParams(location.search);
var sample=qs.get('sample')==='1';
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function pin(){return '<svg class="em-pin" width="34" height="44" viewBox="0 0 34 44" role="img" aria-label="Emergency shelter"><path d="M17 1C8 1 1 8 1 17c0 11 16 26 16 26s16-15 16-26C33 8 26 1 17 1z" fill="#FF3B30" stroke="#FFFFFF" stroke-width="2"/><g transform="translate(8.5,6.2) scale(0.47)"><path fill="#FFFFFF" d="'+HOUSE+'"/></g></svg>'}
function emergencySearch(q){q=String(q||'').toLowerCase();return TERMS.some(function(t){return q.indexOf(t)>=0})}
function isNI(postcode,nation){if(nation&&String(nation).toLowerCase().replace(/ /g,'')==='northernireland')return true;return String(postcode||'').toUpperCase().replace(/ /g,'').indexOf('BT')===0}
function flood(postcode,nation){return isNI(postcode,nation)?['Flooding NI','0300 2000 100']:['Floodline','0345 988 1188']}
function hideExpired(root){var now=Date.now();root.querySelectorAll('[data-open-until]').forEach(function(el){var t=Date.parse(el.getAttribute('data-open-until'));if(!isNaN(t)&&now>=t)el.hidden=true})}
function row(label,value){if(value==null||value==='')return '';return '<dt>'+esc(label)+'</dt><dd>'+esc(value)+'</dd>'}
function buttons(c,example){var call=c.phone?'<a class="em-call" href="tel:'+esc(String(c.phone).replace(/[^\d+]/g,''))+'">'+PHONE+esc(c.phone)+(example?' (example)':'')+'</a>':'';
 var dir=c.lat!=null&&c.lng!=null?'<a class="em-dir" href="https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(c.lat+','+c.lng)+'&travelmode=walking">Directions</a>':(example?'<a class="em-dir" href="#em-root">Directions</a>':'');
 return '<a class="em-999" href="tel:999">'+PHONE+'999 Emergency services</a>'+(call||dir?'<div class="em-row">'+call+dir+'</div>':'')}
function listCard(c,example){var fl=flood(c.postcode,c.nation),sw=c.swep_badge?'<div class="em-swep">'+esc(c.swep_badge)+'</div>':'';
 var dl=row('Opened by',c.opened_by)+row('Opened for',c.opened_for)+row('Open until',c.open_until_label)+row('Pets',c.pets)+row('Access',c.access)+row('Beds',c.beds)+row('Last checked',c.last_checked);
 var src=c.source_url?'<p class="em-src"><a href="'+esc(c.source_url)+'">Council update</a></p>':'';
 return '<article class="em-card" data-open-until="'+esc(c.open_until||'')+'"><span class="em-badge">Emergency shelter</span>'+sw+'<h3 class="em-title">'+esc(c.name)+'</h3>'+(dl?'<dl class="em-dl">'+dl+'</dl>':'')+buttons(c,example)+'<div class="em-flood"><span>'+esc(fl[0])+'</span><span>'+esc(fl[1])+'</span></div>'+src+'</article>'}
function popCard(c,example){return '<article class="em-card em-pop" data-open-until="'+esc(c.open_until||'')+'"><span class="em-badge">Emergency shelter</span><h3 class="em-title">'+esc(c.name)+'</h3><p class="em-sub">Open until '+esc(c.open_until_label||'')+'</p>'+buttons(c,example)+'</article>'}
var root=document.createElement('div');root.id='em-root';
var banner=document.createElement('div');banner.id='em-banner';banner.setAttribute('role','status');banner.hidden=true;
var msg=document.getElementById('msg');if(msg)msg.insertAdjacentElement('afterend',banner);
var col=document.getElementById('v3col')||document.getElementById('list');
if(col)col.insertAdjacentElement('afterbegin',root);else document.body.appendChild(root);
function setKey(on){var leg=document.getElementById('em-keyleg');if(!on){if(leg)leg.remove();return}
 if(leg)return;var host=document.getElementById('xupd');if(!host)return;leg=document.createElement('span');leg.id='em-keyleg';
 leg.innerHTML='<b>Emergency shelter</b> <small>rest centre, wording needs Dean’s OK</small>';host.appendChild(leg)}
function showBanner(text,extra){banner.hidden=!text;banner.innerHTML=text?esc(text)+(extra||''):''}
if(sample){var fl=flood();
 banner.hidden=false;
 banner.innerHTML='EXAMPLE · PREVIEW ONLY, NOT DEPLOYED. '+esc('Severe weather warning for Example area (example). If you are in danger, call 999. Flood advice: Floodline 0345 988 1188. Emergency shelters near you are shown in red. Source: Met Office, updated 20:10 (example).')+' <a href="emergency.txt">Text-only list</a>';
 root.innerHTML='<p class="em-kicker">EXAMPLE MAP PIN</p><div class="em-pinrow">'+pin()+'Emergency shelter</div>'
  +'<p class="em-kicker">EXAMPLE LIST CARD</p>'+listCard({name:'Example Leisure Centre (example)',opened_by:'Example District Council (example)',opened_for:'Flooding (only if the source says so)',open_until:'2099-01-01T08:00:00+00:00',open_until_label:'08:00 Mon 26 Oct (example)',last_checked:'20:10 (example)',phone:'01234 000000',swep_badge:'Severe weather: open tonight',postcode:'BN17 5AA'},true)
  +'<p class="em-kicker">EXAMPLE MAP POP-UP CARD</p>'+popCard({name:'Example Community Hall (example)',open_until:'2099-01-01T23:00:00+00:00',open_until_label:'23:00 (example)',phone:'01234 000000'},true)
  +'<div class="em-key"><b>Map key, 4th entry.</b> Emergency shelter: a rest centre opened by the council in an emergency, such as a flood, fire, evacuation or power loss. Wording needs Dean’s OK before this goes live. Floodline '+esc(fl[1])+'.</div>';
 setKey(true)}
else root.innerHTML='<p class="em-quiet">Emergency shelter preview. No council rest centre is listed. The live map is unchanged for everyone else. <a href="emergency.txt">Text-only list</a></p>';
function applySearch(){var q=document.getElementById('q');document.documentElement.classList.toggle('em-only',emergencySearch(q&&q.value))}
var form=document.getElementById('f');if(form)form.addEventListener('submit',function(){setTimeout(applySearch,0)},true);
hideExpired(root);setInterval(function(){hideExpired(root)},30000);
window.emPreview={hideExpired:function(){hideExpired(root)},emergencySearch:emergencySearch};
fetch('reports/emergency_preview.json',{cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(data){
 if(!data||sample)return;var cards=(data.cards||[]).filter(function(c){return c&&c.live&&!c.example});
 if(!cards.length)return;root.innerHTML=cards.map(function(c){return listCard(c,false)+popCard(c,false)}).join('');
 setKey(true);hideExpired(root)}).catch(function(){});
})();
