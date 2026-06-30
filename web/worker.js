// Pyodide worker: fetches terrain + OSM and builds the board off the main thread,
// so the 3D view keeps rendering/rotating during generation. Posts geometry back.
let pyodide, FONT;
async function init(){
  importScripts('https://cdn.jsdelivr.net/pyodide/v0.26.2/full/pyodide.js');
  pyodide = await loadPyodide();
  await pyodide.loadPackage(['numpy','pillow']);
  pyodide.runPython(await (await fetch('board_lib.py')).text());
  FONT = new Uint8Array(await (await fetch('font.ttf')).arrayBuffer());
  postMessage({type:'ready'});
}
const ready = init();

// ---- NOAA NCEI topobathy DEM (float TIFF, CORS-open): land + real ocean depth ----
async function fetchDEM(w,s,e,n){
  const clat=(s+n)/2*Math.PI/180, Wm=(e-w)*111320*Math.cos(clat), Hm=(n-s)*111320, LONG=1600;
  let W,H; if(Wm>=Hm){W=LONG;H=Math.max(2,Math.round(LONG*Hm/Wm));}else{H=LONG;W=Math.max(2,Math.round(LONG*Wm/Hm));}
  const url=`https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_all/ImageServer/exportImage`
    +`?bbox=${w},${s},${e},${n}&bboxSR=4326&imageSR=4326&size=${W},${H}`
    +`&format=tiff&pixelType=F32&interpolation=RSP_BilinearInterpolation&adjustAspectRatio=false&f=image`;
  const r=await fetch(url); if(!r.ok) throw new Error('NOAA DEM HTTP '+r.status);
  return {bytes:new Uint8Array(await r.arrayBuffer()), W, H};
}
// ---- OSM Overpass (mirrors, fall through on timeout) ----
const OVERPASS=['https://overpass-api.de/api/interpreter',
                'https://overpass.kumi.systems/api/interpreter',
                'https://overpass.private.coffee/api/interpreter'];
async function overpass(ql){
  let last;
  for(const ep of OVERPASS){
    try{
      const ctl=new AbortController(), to=setTimeout(()=>ctl.abort(),30000);
      const r=await fetch(ep,{method:'POST',body:'data='+encodeURIComponent(ql),signal:ctl.signal});
      clearTimeout(to); if(!r.ok) throw new Error('HTTP '+r.status); return await r.json();
    }catch(e){ last=e; postMessage({type:'progress',msg:'Overpass '+ep.split('/')[2]+' failed, trying next'}); }
  }
  throw new Error('all Overpass mirrors failed ('+(last&&last.message)+')');
}
const LAYER={fairway:'fairway',tee:'tee',green:'green',bunker:'bunker',water_hazard:'water',lateral_water_hazard:'water'};
const RAIL=['rail','light_rail','tram','narrow_gauge','subway'];
const PATHY=['footway','path','track','cycleway','steps','bridleway'];
function classify(t){
  if(!t) return null;
  if(LAYER[t.golf]) return LAYER[t.golf];
  if(t.golf==='cartpath'||t.golf==='path') return 'cartpath';
  if(t.natural==='water'||t.waterway) return 'water';
  if(RAIL.includes(t.railway)) return 'rail';
  if(t.highway) return PATHY.includes(t.highway) ? 'cartpath' : 'road';
  return null;
}
async function fetchFeatures(w,s,e,n){
  const ql=`[out:json][timeout:25];(way["golf"](${s},${w},${n},${e});way["highway"](${s},${w},${n},${e});way["railway"](${s},${w},${n},${e});way["natural"="water"](${s},${w},${n},${e}););out geom;`;
  const j=await overpass(ql); const f={}, holes=[];
  for(const el of (j.elements||[])){ if(!el.geometry) continue;
    const t=el.tags||{};
    if(t.golf==='hole'){ holes.push({pts:el.geometry.map(p=>[p.lon,p.lat]), num:(t.ref||t.name||'').toString().replace(/[^0-9]/g,'')}); continue; }
    const L=classify(t); if(!L) continue;
    (f[L]=f[L]||[]).push(el.geometry.map(p=>[p.lon,p.lat]));}
  return {feats:f, holes};
}

// pack render objects -> compact binary (uint32 header len | header JSON | verts+tris blobs)
function packMesh(objsMap){
  const arr=objsMap.map(o=>({color:o.get('color'),verts:o.get('verts').buffer,tris:o.get('tris').buffer}));
  const header={objects:arr.map(o=>({color:o.color,v:o.verts.byteLength,t:o.tris.byteLength}))};
  const hj=new TextEncoder().encode(JSON.stringify(header));
  let total=4+hj.length; arr.forEach(o=>total+=o.verts.byteLength+o.tris.byteLength);
  const out=new ArrayBuffer(total), dv=new DataView(out), u8=new Uint8Array(out);
  dv.setUint32(0,hj.length,true); u8.set(hj,4); let off=4+hj.length;
  arr.forEach(o=>{u8.set(new Uint8Array(o.verts),off);off+=o.verts.byteLength;u8.set(new Uint8Array(o.tris),off);off+=o.tris.byteLength;});
  return out;
}

onmessage = async (ev)=>{
  const m=ev.data; if(m.type!=='generate') return;
  await ready;
  const t0=Date.now();
  try{
    const [w,s,e,n]=m.bbox;
    postMessage({type:'progress',msg:'fetching terrain + OSM…'});
    const [dem,ff]=await Promise.all([fetchDEM(w,s,e,n), fetchFeatures(w,s,e,n)]);
    const counts=Object.fromEntries(Object.entries(ff.feats).map(([k,v])=>[k,v.length]));
    postMessage({type:'progress',msg:`DEM ${dem.W}x${dem.H}, ${ff.holes.length} holes, ${JSON.stringify(counts)} (${((Date.now()-t0)/1000).toFixed(1)}s)`});
    const t1=Date.now();
    pyodide.globals.set('dem_bytes',dem.bytes);
    pyodide.globals.set('feats_json',JSON.stringify(ff.feats));
    pyodide.globals.set('holes_json',JSON.stringify(ff.holes));
    pyodide.globals.set('font_bytes',FONT);
    const res=pyodide.runPython(`golf_board(dem_bytes,0,0,[${w},${s},${e},${n}],feats_json,${m.exag},8.0,holes_json,font_bytes)`);
    const out=res.toJs(); res.destroy();
    const objects=out.get('objects').map(o=>({
      name:o.get('name'), color:o.get('color'), ntri:o.get('ntri'),
      verts:o.get('verts').buffer, tris:o.get('tris').buffer}));
    const tmf=out.get('tmf').buffer;
    // coarse preview mesh for the gallery (small, instant to view) — reuses fetched data
    const pres=pyodide.runPython(`golf_board(dem_bytes,0,0,[${w},${s},${e},${n}],feats_json,${m.exag},8.0,holes_json,font_bytes,0.5)`);
    const pout=pres.toJs(); pres.destroy();
    const preview=packMesh(pout.get('objects'));
    const transfer=objects.flatMap(o=>[o.verts,o.tris]); transfer.push(tmf, preview);
    postMessage({type:'done', objects, tmf, preview, board:out.get('board'),
                 buildMs:Date.now()-t1}, transfer);
  }catch(err){ postMessage({type:'error', msg:err.message}); }
};
