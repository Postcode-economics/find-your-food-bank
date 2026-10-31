/* Incident rest centres: preview (?preview=emergency) or live (incident_rest_centre_live.json). Red pins only for incident rest centres.
   House pictogram: UN OCHA Humanitarian Icons, House.svg, CC0 1.0. */
(function(){
var isPreview=document.documentElement.classList.contains('em-preview');
var isLive=document.documentElement.classList.contains('em-live');
if(!isPreview&&!isLive)return;
var HOUSE='M18.66437.2525a1.00028,1.00028,0,0,0-1.32874,0l-17.008,15.45A1,1,0,0,0,0,16.44266v27.5574H14v-10a2.00588,2.00588,0,0,1,2-2h4a2.00588,2.00588,0,0,1,2,2v10H36V16.44266a1,1,0,0,0-.32761-.7402Z';
var TERMS=['rest centre','reception centre','power cut','emergency shelter','emergency','evacuation','evacuate','earthquake','flood','storm','fire','gas'];
var BADGE='Rest centre (council-run)';
var PHONE='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1C10.61 21 3 13.39 3 4c0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg>';
var qs=new URLSearchParams(location.search);
var sample=qs.get('sample')==='1'&&isPreview;
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function pin(){return '<svg class="em-pin" width="34" height="44" viewBox="0 0 34 44" role="img" aria-label="'+esc(BADGE)+'"><path d="M17 1C8 1 1 8 1 17c0 11 16 26 16 26s16-15 16-26C33 8 26 1 17 1z" fill="#FF3B30" stroke="#FFFFFF" stroke-width="2"/><g transform="translate(8.5,6.2) scale(0.47)"><path fill="#FFFFFF" d="'+HOUSE+'"/></g></svg>'}
function emergencySearch(q){q=String(q||'').toLowerCase();return TERMS.some(function(t){return q.indexOf(t)>=0})}
function isNI(postcode,nation){if(nation&&String(nation).toLowerCase().replace(/ /g,'')==='northernireland')return true;return String(postcode||'').toUpperCase().replace(/ /g,'').indexOf('BT')===0}
function flood(postcode,nation){return isNI(postcode,nation)?['Flooding NI','0300 2000 100']:['Floodline','0345 988 1188']}
function passed(until){var t=Date.parse(until||'');return !isNaN(t)&&Date.now()>=t}
var emMarkers={};
function hideExpired(root){var now=Date.now();root.querySelectorAll('[data-open-until]').forEach(function(el){var t=Date.parse(el.getAttribute('data-open-until'));if(!isNaN(t)&&now>=t){el.hidden=true;var id=el.getAttribute('data-em');if(id&&emMarkers[id]&&hideExpired.layer){hideExpired.layer.removeLayer(emMarkers[id]);delete emMarkers[id]}}})}
function row(label,value){if(value==null||value==='')return '';return '<dt>'+esc(label)+'</dt><dd>'+esc(value)+'</dd>'}
function buttons(c,example){var call=c.phone?'<a class="em-call" href="tel:'+esc(String(c.phone).replace(/[^\d+]/g,''))+'">'+PHONE+esc(c.phone)+(example?' (example)':'')+'</a>':'';
 var dir=example?'<a class="em-dir" href="#em-root">Directions</a>':(c.lat!=null&&c.lng!=null?'<a class="em-dir" href="https://www.google.com/maps/dir/?api=1&destination='+encodeURIComponent(c.lat+','+c.lng)+'&travelmode=walking">Directions</a>':'');
 return '<a class="em-999" href="tel:999">'+PHONE+'999 Emergency services</a>'+(call||dir?'<div class="em-row">'+dir+call+'</div>':'')}
function attrs(c){var id=c.id||c.name||'';return ' data-em="'+esc(id)+'" data-lat="'+(c.lat==null?'':esc(c.lat))+'" data-lng="'+(c.lng==null?'':esc(c.lng))+'" data-open-until="'+esc(c.open_until||'')+'" data-lad="'+esc(c.lad||'')+'"'}
function listCard(c,example){var fl=flood(c.postcode,c.nation);
 var quote=c.quote?'<p class="em-quote">'+esc(c.quote)+'</p>':'';
 var when=checkedLabel(c.last_checked||c.checked_at);
 var dl=row('Opened by',c.opened_by||c.council)+row('Opened for',c.opened_for)+row('Open until',c.open_until_label)+row('Pets',c.pets)+row('Access',c.access)+row('Beds',c.beds)+row('Checked',when.replace(/^Checked\s+/,''));
 var src=c.source_url?'<p class="em-src"><a href="'+esc(c.source_url)+'">Council page</a></p>':'';
 return '<article class="em-card"'+attrs(c)+'><span class="em-badge">'+esc(BADGE)+'</span><h3 class="em-title">'+esc(c.name)+'</h3>'+quote+(dl?'<dl class="em-dl">'+dl+'</dl>':'')+buttons(c,example)+'<div class="em-flood"><span>'+esc(fl[0])+'</span><span>'+esc(fl[1])+'</span></div>'+src+'</article>'}
function popCard(c,example){return '<article class="em-card em-pop"'+attrs(c)+'><span class="em-badge">'+esc(BADGE)+'</span><h3 class="em-title">'+esc(c.name)+'</h3><p class="em-sub">Open until '+esc(c.open_until_label||'')+'</p>'+buttons(c,example)+'</article>'}
var root=document.createElement('div');root.id='em-root';
var banner=document.createElement('div');banner.id='em-banner';banner.hidden=true;
var hit=document.createElement('button');hit.type='button';hit.className='em-hit';hit.setAttribute('aria-label','Go to nearest open rest centre');banner.appendChild(hit);
var msg=document.getElementById('msg');if(msg)msg.insertAdjacentElement('afterend',banner);
var col=document.getElementById('v3col')||document.getElementById('list');
if(col)col.insertAdjacentElement('afterbegin',root);else document.body.appendChild(root);
function setKey(on){var leg=document.getElementById('em-keyleg');if(!on){if(leg)leg.remove();return}
 if(leg)return;var host=document.getElementById('xupd');if(!host)return;leg=document.createElement('span');leg.id='em-keyleg';
 leg.innerHTML='<b>'+esc(BADGE)+'</b>';host.appendChild(leg)}
function iconHtml(){return '<span class="em-ico" aria-hidden="true">'+pin()+'</span>'}
function fillBanner(html){banner.hidden=!html;if(!html){hit.innerHTML='';var old=banner.querySelector('a.em-text');if(old)old.remove();return}
 hit.innerHTML='<span class="em-top">'+iconHtml()+'<span class="em-cta">Nearest rest centre</span></span><span class="em-body">'+html+'</span>';
 if(!banner.querySelector('a.em-text')){var a=document.createElement('a');a.className='em-text';a.href='emergency.txt';a.textContent='Text-only list';banner.appendChild(a)}}
function visitorLad(){try{if(window.__visitorLad)return window.__visitorLad}catch(e){}return null}
function centreAllowed(c,lad){if(!isLive)return true;if(!lad)return false;var cl=c.lad||'';return cl&&cl===lad}
function centresForArea(data,lad){return ((data&&data.cards)||[]).filter(function(c){if(!c||c.kind==='day_centre'||c.service==='day_centre')return false;if(!(c.live!==false&&!c.example))return false;if(isLive&&passed(c.open_until))return false;return centreAllowed(c,lad)})}
function openCards(){return [].filter.call(root.querySelectorAll('.em-card'),function(el){if(el.hidden)return false;return !passed(el.getAttribute('data-open-until'))})}
function hav(lat1,lng1,lat2,lng2){var r=function(x){return x*Math.PI/180},R=6371,x=Math.sin(r(lat2-lat1)/2),y=Math.sin(r(lng2-lng1)/2),h=x*x+Math.cos(r(lat1))*Math.cos(r(lat2))*y*y;return 2*R*Math.asin(Math.min(1,Math.sqrt(h)))}
function choose(loc){var cards=openCards();if(!cards.length)return null;if(!loc)return cards[0];var best=null,bestD=Infinity,any=false;cards.forEach(function(el){var la=parseFloat(el.getAttribute('data-lat')),ln=parseFloat(el.getAttribute('data-lng'));if(!isFinite(la)||!isFinite(ln))return;any=true;var d=hav(loc.lat,loc.lng,la,ln);if(d<bestD){bestD=d;best=el}});return any?best:cards[0]}
function plot(cards,example){emMarkers={};if(typeof L==='undefined'||typeof map==='undefined')return;if(!plot.layer)plot.layer=L.layerGroup().addTo(map);hideExpired.layer=plot.layer;plot.layer.clearLayers();(cards||[]).forEach(function(c){if(c.lat==null||c.lng==null||passed(c.open_until))return;var id=c.id||c.name;var m=L.marker([+c.lat,+c.lng],{icon:L.divIcon({className:'em-pinwrap',html:pin(),iconSize:[34,44],iconAnchor:[17,43],popupAnchor:[0,-40]}),title:c.name,keyboard:true,zIndexOffset:800});m.bindPopup(popCard(c,!!example),{maxWidth:320,autoPan:true,autoPanPadding:[12,12]});emMarkers[id]=m;plot.layer.addLayer(m)})}
function reveal(card){if(!card)return;root.querySelectorAll('.em-card.em-go').forEach(function(el){el.classList.remove('em-go')});card.classList.add('em-go');if(!card.hasAttribute('tabindex'))card.setAttribute('tabindex','-1');
 var reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;try{card.scrollIntoView({block:'center',behavior:reduce?'auto':'smooth'})}catch(e){card.scrollIntoView()}
 try{card.focus({preventScroll:true})}catch(e){try{card.focus()}catch(e2){}}
 var m=emMarkers[card.getAttribute('data-em')];if(!m||typeof map==='undefined')return;try{map.closePopup()}catch(e){}
 try{clearTimeout(window._refitT)}catch(e){}var z=Math.max(map.getZoom?map.getZoom():12,12);try{map.setView(m.getLatLng(),z,{animate:!reduce})}catch(e){try{map.panTo(m.getLatLng(),{animate:!reduce})}catch(e2){}}m.openPopup()}
function readSearched(){try{if(typeof lastNear!=='undefined'&&lastNear&&isFinite(+lastNear[0])&&isFinite(+lastNear[1]))return {lat:+lastNear[0],lng:+lastNear[1]}}catch(e){}return null}
function locationReady(){var known=readSearched();if(known)return Promise.resolve(known);
 try{if(!navigator.geolocation||!navigator.permissions||!navigator.permissions.query)return Promise.resolve(null);
  return navigator.permissions.query({name:'geolocation'}).then(function(p){if(!p||p.state!=='granted')return null;
   return new Promise(function(res){navigator.geolocation.getCurrentPosition(function(pos){
    var lat=pos.coords.latitude,lng=pos.coords.longitude;
    fetch('https://api.postcodes.io/postcodes?lon='+encodeURIComponent(lng)+'&lat='+encodeURIComponent(lat)+'&limit=1').then(function(r){return r.json()}).then(function(j){
     try{var c=j.result&&j.result[0]&&j.result[0].codes;if(c&&c.admin_district)window.__visitorLad=c.admin_district}catch(e){}
     res({lat:lat,lng:lng})}).catch(function(){res({lat:lat,lng:lng})})
   },function(){res(null)},{maximumAge:600000,timeout:4000})})}).catch(function(){return null})}
 catch(e){return Promise.resolve(null)}}
function goNearest(){return locationReady().then(function(loc){reveal(choose(loc))})}
hit.addEventListener('click',function(e){e.preventDefault();goNearest()});
banner.addEventListener('click',function(e){var a=e.target&&e.target.closest?e.target.closest('a'):null;if(a)return;if(e.target.closest&&e.target.closest('.em-hit'))return;goNearest()});
function checkedLabel(raw){var s=String(raw==null?'':raw).trim();if(!s)return '';
 if(/^Checked\s+\d{1,2}:\d{2}(am|pm),/i.test(s))return 'Checked '+s.replace(/^Checked\s+/i,'');
 if(!/^\d{4}-\d{2}-\d{2}/.test(s))return s;
 var d=new Date(s);if(isNaN(d.getTime()))return s;
 var parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit',hourCycle:'h23',weekday:'short',day:'numeric',month:'short'}).formatToParts(d);
 var g={};parts.forEach(function(p){if(p.type!=='literal')g[p.type]=p.value});
 var h24=parseInt(g.hour,10);if(isNaN(h24)||!g.minute)return s;
 var ap=h24<12?'am':'pm',h=h24%12||12;
 return 'Checked '+h+':'+g.minute+ap+', '+g.weekday+' '+g.day+' '+g.month}
function liveBannerText(cards,data){if(!cards.length)return '';
 var c=cards[0], council=c.opened_by||c.council||'The council', incident=c.opened_for||'an incident', src=c.source_url||'', chk=checkedLabel(c.last_checked||c.checked_at||data.generated||'');
 var lead='Rest centre open: '+council+' has opened a rest centre for people affected by '+incident+'.';
 var meta='Information from '+(src?'<a href="'+esc(src)+'">the council page</a>':'the council')+(chk?', '+esc(chk):'')+'. Follow advice from the emergency services and the council. In danger, call 999.';
 return esc(lead)+'<br>'+meta}
function applyData(data){var lad=visitorLad();var cards=centresForArea(data,lad);if(isLive&&!lad){banner.hidden=true;root.innerHTML='';setKey(false);return}
 if(!cards.length){if(isLive){banner.hidden=true;root.innerHTML='';setKey(false)}return}
 root.innerHTML=cards.map(function(c){return listCard(c,false)}).join('');
 var bannerHtml;
 if(isPreview&&!sample){bannerHtml='If you are in danger, call 999. Every open rest centre is listed below.'}
 else if(isPreview&&sample){bannerHtml=''}
 else{bannerHtml=liveBannerText(cards,data)}
 fillBanner(bannerHtml||liveBannerText(cards,data));
 setKey(true);hideExpired(root);plot(cards,false)}
if(sample){var fl=flood();
 var leisure={id:'example-leisure',name:'Example Leisure Centre (example)',opened_by:'Example District Council (example)',opened_for:'Flooding (only if the source says so)',open_until:'2099-01-01T08:00:00+00:00',open_until_label:'08:00 Mon 26 Oct (example)',last_checked:'20:10 (example)',phone:'01234 000000',postcode:'BN17 5AA',lat:50.8092,lng:-0.5406,quote:'Example council wording (example).'};
 var hall={id:'example-hall',name:'Example Community Hall (example)',open_until:'2099-01-01T23:00:00+00:00',open_until_label:'23:00 (example)',phone:'01234 000000',lat:51.5074,lng:-0.1278};
 fillBanner('EXAMPLE · PREVIEW ONLY. '+esc('Rest centre open: Example District Council (example) has opened a rest centre for people affected by flooding (example).'));
 root.innerHTML='<p class="em-kicker">EXAMPLE MAP PIN</p><div class="em-pinrow">'+pin()+esc(BADGE)+'</div>'
  +'<p class="em-kicker">EXAMPLE LIST CARD</p>'+listCard(leisure,true)
  +'<p class="em-kicker">EXAMPLE MAP POP-UP CARD</p>'+popCard(hall,true);
 setKey(true);plot([leisure,hall],true)}
else if(isPreview)root.innerHTML='<p class="em-quiet">Incident rest centre preview. No council rest centre is listed. <a href="emergency.txt">Text-only list</a></p>';
function applySearch(){var q=document.getElementById('q');document.documentElement.classList.toggle('em-only',emergencySearch(q&&q.value))}
var form=document.getElementById('f');if(form)form.addEventListener('submit',function(){setTimeout(applySearch,0)},true);
hideExpired(root);setInterval(function(){hideExpired(root)},30000);
window.emPreview={hideExpired:function(){hideExpired(root)},emergencySearch:emergencySearch,goNearest:goNearest,centresForArea:centresForArea,centresForEveryone:function(d){return centresForArea(d,null)},applyData:applyData};
var liveData=null;
function load(){var url=isLive?'incident_rest_centre_live.json':'reports/emergency_preview.json';
 var bust=location.search.indexOf('fresh=1')>=0?('?t='+Date.now()):'';
 fetch(url+bust,{cache:'no-store'}).then(function(r){return r.ok?r.json():null}).then(function(data){if(!data||sample)return;if(isLive&&!data.public)return;if(isLive)liveData=data;applyData(data)}).catch(function(){});}
if(!sample)load();
document.addEventListener('helpmap-search',function(){if(!isLive)return;if(liveData)applyData(liveData);else load()});
})();
