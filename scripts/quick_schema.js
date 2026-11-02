// Quick-lane schema check (see scripts/quick_check.py). Usage: node scripts/quick_schema.js FILE.js...
const vm=require('vm'),fs=require('fs');const ctx={window:{},document:{}};ctx.self=ctx.window;vm.createContext(ctx);
for(const f of process.argv.slice(2)){vm.runInContext(fs.readFileSync(f,'utf8'),ctx,{filename:f});}
const g=Object.assign({},ctx.window,ctx);const out={};
for(const k of ['FB_DATA','SHELTERS','WARMSPACES']){const v=g[k];if(!v||!Array.isArray(v.items)){out[k]={missing:true};continue}
const bad=[],seen=new Set(),dup=[];v.items.forEach((it,i)=>{const hasC=it.lat!=null&&it.lng!=null&&it.lat!==''&&it.lng!=='';const lat=+it.lat,lng=+it.lng;
if(!it.name||it.id==null||it.id===''||(hasC&&!(lat>49&&lat<61.1&&lng>-8.8&&lng<2.1)))bad.push(String(it.id??i)+' '+(it.name||'')+' '+it.lat+','+it.lng);
const id=String(it.id);if(seen.has(id))dup.push(id);seen.add(id)});out[k]={n:v.items.length,nbad:bad.length,bad:bad.slice(0,20),dup:dup.slice(0,20)}}
console.log(JSON.stringify(out));
