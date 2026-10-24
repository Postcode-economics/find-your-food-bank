/* New look (Dean's mockups, 24 Oct 2026). Display only: rearranges rendered cards, never changes data. */
(function(){
const NL={};
// UK phone display: 07803259452 -> 07803 259452, 02392825673 -> 023 9282 5673
NL.fmt=function(raw){const d=String(raw||'').replace(/[^\d]/g,'');if(!/^0\d{9,10}$/.test(d))return String(raw||'').trim();
 if(d.length===10)return d.slice(0,5)+' '+d.slice(5);
 if(/^02/.test(d))return d.slice(0,3)+' '+d.slice(3,7)+' '+d.slice(7);
 if(/^01\d1|^011/.test(d)||/^0[3589]/.test(d))return d.slice(0,4)+' '+d.slice(4,7)+' '+d.slice(7);
 return d.slice(0,5)+' '+d.slice(5)};
// Contact rule (Dean 24 Oct): venue phone -> green call button; Facebook 'Send a message' only when there is no venue phone.
NL.contact=function(tel,fb){return tel?'call':fb?'fb':null};
NL.domain=function(u){return String(u||'').replace(/^https?:\/\/(www\.)?/i,'').split(/[\/?#]/)[0]};
NL.type=function(c){const r=c.querySelector('.rpb[data-rl]');if(r)return r.dataset.rl;if(c.classList.contains('xsh'))return'sh';if(c.classList.contains('xws'))return'ws';return c.querySelector('.tag,.ncb')?'fb':''};
const TAG={sh:['Shelter','Lloches'],ws:['Warm space','Man cynnes']};
function apply(c){if(c.dataset.nl)return;c.dataset.nl='1';const ty=NL.type(c);if(ty)c.classList.add('nl-'+ty);
 const cy=document.documentElement.lang==='cy';
 // type tag for shelters / warm spaces (food banks already have one)
 if((ty==='sh'||ty==='ws')&&!c.querySelector('.nltag')){const t=document.createElement('div');t.className='tag nltag nltag-'+ty;t.textContent=TAG[ty][cy?1:0];
  const top=c.querySelector('.xunv,.xacc');(top?top.parentNode:c).insertBefore(t,c.firstChild)}
 // status line under the address
 const st=c.querySelector(':scope>.v3st'),ad=[...c.querySelectorAll(':scope>p')].find(p=>!p.classList.contains('sub')&&!p.classList.contains('xw'));
 const sos=c.querySelector(':scope>.v3sos');if(sos&&ad)sos.before(ad);
 if(st&&ad)ad.after(st);
 // buttons: [Directions][contact] then [Share][Website]
 const gm=c.querySelector(':scope>a.btn.gm');if(!gm)return;
 const call=c.querySelector(':scope>a.btn.call:not(.xfb)'),fbb=[...c.querySelectorAll(':scope>a.btn.web')].find(a=>/facebook\.com/i.test(a.href)),
  share=c.querySelector(':scope>.v3share:not(a)'),web=[...c.querySelectorAll(':scope>a.btn.web')].find(a=>!/facebook\.com/i.test(a.href));
 const r1=document.createElement('div');r1.className='nlrow';gm.before(r1);r1.append(gm);
 const kind=NL.contact(call,fbb);
 if(kind==='call'){const num=call.getAttribute('href').replace(/^tel:/,'');const ic=call.querySelector('svg');call.textContent='';if(ic)call.append(ic);call.append(NL.fmt(num));call.setAttribute('aria-label',(cy?'Ffonio ':'Call ')+NL.fmt(num));call.classList.add('nlcall');r1.append(call)}
 else if(kind==='fb'){fbb.classList.remove('v3share');fbb.classList.add('nlfb');const ic=fbb.querySelector('svg');fbb.textContent='';if(ic)fbb.append(ic);fbb.append(cy?'Anfon neges':'Send a message');r1.append(fbb)}
 if(fbb&&kind!=='fb')fbb.remove();
 if(share||web){const r2=document.createElement('div');r2.className='nlrow nlrow2';r1.after(r2);if(share)r2.append(share);
  if(web){const dm=NL.domain(web.href);web.innerHTML=`<span>${cy?'Gwefan':'Website'}</span><small>${dm.replace(/[&<>]/g,'')}</small>`;web.classList.add('nlweb');r2.append(web)}
  if(r2.children.length===1)r2.classList.add('one')}
 const ps=c.querySelector(':scope>small.psrc');if(ps)(r1.nextElementSibling&&r1.nextElementSibling.classList.contains('nlrow2')?r1.nextElementSibling:r1).after(ps)}
NL.apply=apply;
if(typeof document!=='undefined'){
 // food bank cards: rearrange at render time so scroll positions worked out by the list code stay right
 if(typeof window.card==='function'){const oc=window.card;window.card=function(){const h=oc.apply(this,arguments);try{const t=document.createElement('div');t.className='card';t.innerHTML=h;apply(t);return t.innerHTML}catch(e){return h}}}
 // keep whatever is on screen in place while cards are rearranged (scroll targets were set before this ran)
 const run=()=>{const todo=[...document.querySelectorAll('.card:not([data-nl])')];if(!todo.length)return;
  const a=[...document.querySelectorAll('#xlist .lh,#list .lh,#xlist .card,#list .card')].find(e=>{const r=e.getBoundingClientRect();return r.height&&r.bottom>0});
  const t0=a?a.getBoundingClientRect().top:null;todo.forEach(apply);
  if(a){const d=a.getBoundingClientRect().top-t0;if(Math.abs(d)>1)window.scrollBy(0,d)}};
 new MutationObserver(run).observe(document.body,{childList:true,subtree:true});run()}
if(typeof module!=='undefined')module.exports=NL;else window.NL=NL;
})();
