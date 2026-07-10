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
const ready = init().catch(e=>{ postMessage({type:'error',msg:'engine failed to load: '+e.message}); throw e; });

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
                'https://overpass.private.coffee/api/interpreter',
                'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
                'https://overpass.osm.ch/api/interpreter'];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function overpass(ql){
  let last;
  for(let round=0; round<3; round++){               // retry the whole pool; mirrors recover quickly
    for(const ep of OVERPASS){
      try{
        const ctl=new AbortController(), to=setTimeout(()=>ctl.abort(),30000);
        const r=await fetch(ep,{method:'POST',body:'data='+encodeURIComponent(ql),signal:ctl.signal});
        clearTimeout(to); if(!r.ok) throw new Error('HTTP '+r.status); return await r.json();
      }catch(e){ last=e; postMessage({type:'progress',msg:'Overpass '+ep.split('/')[2]+' busy, trying next…'}); }
    }
    await sleep(1500*(round+1));
  }
  throw new Error('all Overpass mirrors busy — try again in a moment ('+(last&&last.message)+')');
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
  const bb=`(${s},${w},${n},${e})`;
  const ql=`[out:json][timeout:25];(way["golf"]${bb};way["highway"]${bb};way["railway"]${bb};way["natural"="water"]${bb};way["leisure"="golf_course"]${bb};relation["leisure"="golf_course"]${bb};);out geom;`;
  const j=await overpass(ql); const f={}, holes=[], courses=[];
  for(const el of (j.elements||[])){
    const t=el.tags||{};
    if(t.leisure==='golf_course'){        // course boundary polygons: group holes by course
      if(el.geometry) courses.push({name:t.name||'unnamed course', poly:el.geometry.map(p=>[p.lon,p.lat])});
      else if(el.members) el.members.forEach(m=>{ if(m.type==='way'&&m.geometry&&m.role!=='inner')
        courses.push({name:t.name||'unnamed course', poly:m.geometry.map(p=>[p.lon,p.lat])}); });
      continue;
    }
    if(!el.geometry) continue;
    if(t.golf==='hole'){ holes.push({pts:el.geometry.map(p=>[p.lon,p.lat]), num:(t.ref||t.name||'').toString().replace(/[^0-9]/g,''),
      name:(t.name||t.description||'').toString()}); continue; }
    const L=classify(t); if(!L) continue;
    (f[L]=f[L]||[]).push(el.geometry.map(p=>[p.lon,p.lat]));}
  return {feats:f, holes, courses};
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

let lastGen=null;                    // bbox/exag of the last full build (dem_bytes etc. persist as pyodide globals)
onmessage = async (ev)=>{
  const m=ev.data;
  if(m.type==='route'){              // live thickness/height: remesh only the ribbon
    await ready;
    if(!lastGen) return;
    try{
      const [w,s,e,n]=lastGen.bbox;
      const res=pyodide.runPython(`route_layer(dem_bytes,0,0,[${w},${s},${e},${n}],${lastGen.exag},8.0,route_json,${+m.routeW||2.4},${+m.routeH||1})`);
      const out=res.toJs(); res.destroy();
      const verts=out.get('verts').buffer, tris=out.get('tris').buffer;
      postMessage({type:'route', verts, tris, routeH:+m.routeH||1}, [verts,tris]);
    }catch(err){ postMessage({type:'error',msg:err.message}); }
    return;
  }
  if(m.type==='features'){           // for the pre-render edit step (plan + holes), no build
    await ready;
    try{ const [w,s,e,n]=m.bbox; const ff=await fetchFeatures(w,s,e,n);
      postMessage({type:'features', feats:ff.feats, holes:ff.holes, courses:ff.courses, bbox:m.bbox}); }
    catch(err){ postMessage({type:'error', msg:err.message}); }
    return;
  }
  if(m.type!=='generate') return;
  await ready;
  const t0=Date.now();
  try{
    const [w,s,e,n]=m.bbox;
    postMessage({type:'progress',msg:'fetching terrain + OSM…',pct:6});
    const [dem,ff]=await Promise.all([fetchDEM(w,s,e,n), fetchFeatures(w,s,e,n)]);
    const route=m.route||[], kind=m.kind||'bike', hide=m.hide||[], routeW=+m.routeW||2.4, routeH=+m.routeH||1.0;
    hide.forEach(k=>{ delete ff.feats[k]; });        // excluded features never reach the mesher
    // m.holes = user-edited labels from the edit step; ride boards never get golf numbers
    const holes=route.length ? (m.holes||[]) : (m.holes||ff.holes);
    const counts=Object.fromEntries(Object.entries(ff.feats).map(([k,v])=>[k,v.length]));
    postMessage({type:'progress',msg:`DEM ${dem.W}x${dem.H}, ${holes.length} holes, ${JSON.stringify(counts)} (${((Date.now()-t0)/1000).toFixed(1)}s)`,pct:30});
    const t1=Date.now();
    pyodide.globals.set('dem_bytes',dem.bytes);
    pyodide.globals.set('feats_json',JSON.stringify(ff.feats));
    pyodide.globals.set('holes_json',JSON.stringify(holes));
    pyodide.globals.set('font_bytes',FONT);
    pyodide.globals.set('route_json',JSON.stringify(route));
    pyodide.globals.set('hide_json',JSON.stringify(hide));
    pyodide.globals.set('title_s',(m.title||'').toString());
    pyodide.globals.set('subtitle_s',(m.subtitle||'').toString());
    const finePitch=+m.pitch?+m.pitch:'None';
    const call=p=>`golf_board(dem_bytes,0,0,[${w},${s},${e},${n}],feats_json,${m.exag},8.0,holes_json,font_bytes,${p},route_json,'${kind}',hide_json,${routeW},${routeH},title_s,subtitle_s)`;
    postMessage({type:'progress',msg:'meshing the board…',pct:35});
    const res=pyodide.runPython(call(finePitch));
    const out=res.toJs(); res.destroy();
    postMessage({type:'progress',msg:'building preview…',pct:78});
    const objects=out.get('objects').map(o=>({
      name:o.get('name'), color:o.get('color'), ntri:o.get('ntri'),
      verts:o.get('verts').buffer, tris:o.get('tris').buffer}));
    const tmf=out.get('tmf').buffer;
    // coarse preview mesh for the gallery (small, instant to view) — reuses fetched data
    const pres=pyodide.runPython(call('0.5'));
    const pout=pres.toJs(); pres.destroy();
    const preview=packMesh(pout.get('objects'));
    lastGen={bbox:m.bbox, exag:m.exag};
    const transfer=objects.flatMap(o=>[o.verts,o.tris]); transfer.push(tmf, preview);
    postMessage({type:'done', objects, tmf, preview, board:out.get('board'),
                 buildMs:Date.now()-t1}, transfer);
  }catch(err){ postMessage({type:'error', msg:err.message}); }
};
