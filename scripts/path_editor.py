#!/usr/bin/env python3
"""Browser-based course editor for the cribbage board.

Two modes:
  Draw      — freehand: drag to draw the course; the line IS the path
              (a minimum bend radius is enforced when rendering)
  Waypoints — click points; the water-router connects them

Zoom with pinch / ctrl+scroll. "Save & Re-route" runs route_prototype.py and
refreshes the map.

Run: python3 scripts/path_editor.py   ->  http://localhost:8765
"""
import base64, json, os, subprocess, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("PORT", "8765"))
HOST = os.environ.get("HOST", "127.0.0.1")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")   # if set, gate the whole app
# region config (must match route_prototype.py)
_reg = {"bbox": [-68.95, 43.98, -68.44, 44.36]}
try:
    _reg.update(json.load(open(os.path.join(ROOT, "data/region.json"))))
except Exception:
    pass
MINLON, MINLAT, MAXLON, MAXLAT = _reg["bbox"]

run_lock = threading.Lock()

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Deer Isle course editor</title>
<style>
  body { margin:0; background:#14141c; color:#ddd; font:14px -apple-system,sans-serif;
         display:flex; height:100vh; overflow:hidden; }
  #side { width:235px; padding:14px; flex-shrink:0; overflow-y:auto; }
  #side h2 { font-size:15px; margin:0 0 10px; color:#fff; }
  #side p { color:#9a9ab0; font-size:12px; line-height:1.5; }
  button { display:block; width:100%; margin:6px 0; padding:9px; border:0; border-radius:7px;
           background:#2e2e40; color:#eee; font-size:13px; cursor:pointer; }
  button:hover { background:#3a3a52; }
  button.primary { background:#2563eb; } button.primary:hover { background:#3b82f6; }
  button.on { background:#16a34a; }
  .row { display:flex; gap:6px; } .row button { flex:1; }
  label { font-size:12px; color:#9a9ab0; display:block; margin-top:8px; }
  input[type=number] { width:70px; background:#22222e; color:#eee; border:1px solid #3a3a52;
           border-radius:5px; padding:5px; }
  select { width:100%; background:#22222e; color:#eee; border:1px solid #3a3a52;
           border-radius:5px; padding:6px; margin:4px 0 8px; font-size:13px; }
  #status { margin-top:10px; font-size:12px; color:#8fda8f; white-space:pre-wrap; }
  #wrap { flex:1; overflow:auto; position:relative; background:#0a0a10; }
  #stage { position:relative; transform-origin: top left; }
  #map { display:block; user-select:none; -webkit-user-drag:none; }
  canvas { position:absolute; left:0; top:0; cursor:crosshair; }
  #sat { position:absolute; left:0; top:0; width:100%; height:100%; opacity:0; pointer-events:none; }
</style></head><body>
<div id="side">
  <a href="/" style="color:#7dd3fc;font-size:12px;text-decoration:none">&larr; Projects</a>
  <h2>Course editor</h2>
  <select id="regionSel"></select>
  <div class="row">
    <button id="modeDraw">✏️ Draw</button>
    <button id="modeWp">📍 Waypoints</button>
  </div>
  <div class="row">
    <button id="modeCrop">▣ Crop</button>
    <button id="modeLabels">🏷 Labels</button>
  </div>
  <p id="help"></p>
  <div class="row">
    <button id="zin">＋</button><button id="zout">−</button><button id="zfit">Fit</button>
  </div>
  <button id="base">Toggle basemap</button>
  <button id="gmaps">🌍 Compare in Google Maps</button>
  <label>Min bend radius (mm)
    <input type="number" id="radius" value="8" min="3" max="25" step="0.5"></label>
  <div class="row">
    <label>Base (mm)<input type="number" id="baseMm" value="10" min="3" max="30" step="0.5"></label>
    <label>Height ×<input type="number" id="exagX" value="5" min="0.2" max="20" step="0.1"></label>
  </div>
  <div class="row">
    <label>Start holes<select id="optStart"><option>2</option><option>3</option></select></label>
    <label>End mark<select id="optEnd">
      <option value="double">double line</option>
      <option value="end">'END'</option>
      <option value="none">none</option></select></label>
  </div>
  <label style="display:flex;align-items:center;gap:6px">
    <input type="checkbox" id="optStorage" style="width:auto"> Peg storage block</label>
  <label>New place name
    <input type="text" id="newLabel" placeholder="e.g. Zermatt" style="width:100%"></label>
  <button id="addLabel">Add label at view center</button>
  <button id="fetchNames">🗺 Auto-add place names</button>
  <label>Selected label size (mm) — or scroll over a label
    <input type="number" id="labSize" value="9.6" min="3" max="16" step="0.5"></label>
  <div id="satPanel" style="display:none;border:1px solid #3a3a52;border-radius:7px;padding:8px;margin:8px 0">
    <b style="font-size:12px">🛰 Satellite overlay</b>
    <p style="margin:4px 0">Trace missing features (OSM is often incomplete).</p>
    <button id="satLoad">Load / refresh imagery</button>
    <label>opacity <input type="range" id="satOp" min="0" max="100" value="0" style="width:100%"></label>
    <hr style="border-color:#2e2e40">
    <b style="font-size:12px">Detect fairways from satellite</b>
    <p style="margin:4px 0">Tune what mown turf counts as fairway vs rough.</p>
    <label>greenness <span id="gV">12</span><input type="range" id="fGmin" min="0" max="45" value="12" style="width:100%"></label>
    <label>brightness <span id="vV">70</span><input type="range" id="fVmin" min="0" max="160" value="70" style="width:100%"></label>
    <label>corridor width (m) <span id="cV">45</span><input type="range" id="fCorr" min="20" max="90" value="45" style="width:100%"></label>
    <div class="row"><button class="primary" id="fDetect">Detect</button><button id="fClear">Clear</button></div>
    <hr style="border-color:#2e2e40">
    <b style="font-size:12px">Add a feature by hand</b>
    <select id="featType"><option>fairway</option><option>green</option><option>tee</option>
      <option>bunker</option><option>water</option></select>
    <div class="row">
      <button id="featDraw">✏️ Draw polygon</button><button id="featFinish">Finish</button>
    </div>
    <button id="featClear">Clear hand-added</button>
  </div>
  <div id="alignPanel" style="display:none;border:1px solid #3a3a52;border-radius:7px;padding:8px;margin:8px 0">
    <b style="font-size:12px">Align features to terrain</b>
    <p style="margin:4px 0">Nudge the course vectors onto the topography (rail
       embankment, brook channel, green pads). Each click re-renders.</p>
    <div class="row"><label>step (m)<input type="number" id="alStep" value="3" min="0.5" max="30" step="0.5"></label></div>
    <div class="row"><button id="alNW">↖</button><button id="alN">↑</button><button id="alNE">↗</button></div>
    <div class="row"><button id="alW">←</button><button id="alReset">⟳ reset</button><button id="alE">→</button></div>
    <div class="row"><button id="alSW">↙</button><button id="alS">↓</button><button id="alSE">↘</button></div>
    <div class="row">
      <label>lon stretch ×<input type="number" id="alSX" value="1" min="0.8" max="1.2" step="0.002"></label>
      <label>lat stretch ×<input type="number" id="alSY" value="1" min="0.8" max="1.2" step="0.002"></label>
    </div>
    <div class="row">
      <label>rotate°<input type="number" id="alRot" value="0" min="-10" max="10" step="0.25"></label>
      <button id="alSXdn">lon −</button><button id="alSXup">lon +</button>
    </div>
  </div>
  <button class="primary" id="route">Save &amp; Re-route</button>
  <button class="primary" id="build" style="background:#16a34a">🖨 Build &amp; open in Bambu Studio</button>
  <button id="save">Save only</button>
  <button id="undo">Undo stroke</button>
  <button id="nocrop">Clear crop (full map)</button>
  <button id="revert">Revert to saved</button>
  <button id="clear">Clear all</button>
  <div id="status">loaded</div>
</div>
<div id="wrap"><div id="stage">
  <img id="map" src="/map.png">
  <img id="sat">
  <canvas id="cv"></canvas>
</div></div>
<script>
let MINLON=%MINLON%, MAXLON=%MAXLON%, MINLAT=%MINLAT%, MAXLAT=%MAXLAT%;
let wps=[], strokes=[], mode='draw', dragging=-1, drawing=false,
    zoom=1, imgW=0, imgH=0, showingBase=false, crop=null, cropDrag=null,
    labs=[], labOverrides={}, labGrid=null, labMmpp=null, dragLabel=-1,
    customLabels=[], dragCustom=-1, selKind=null, selIdx=-1;
const img=document.getElementById('map'), cv=document.getElementById('cv'),
      ctx=cv.getContext('2d'), status=document.getElementById('status'),
      wrap=document.getElementById('wrap'), stage=document.getElementById('stage'),
      help=document.getElementById('help');
function ll2px(p){ return [ (p[0]-MINLON)/(MAXLON-MINLON)*imgW,
                            (MAXLAT-p[1])/(MAXLAT-MINLAT)*imgH ]; }
function px2ll(x,y){ return [ MINLON + x/imgW*(MAXLON-MINLON),
                              MAXLAT - y/imgH*(MAXLAT-MINLAT) ]; }
function setMode(m){ mode=m;
  document.getElementById('modeDraw').classList.toggle('on', m=='draw');
  document.getElementById('modeWp').classList.toggle('on', m=='wp');
  document.getElementById('modeCrop').classList.toggle('on', m=='crop');
  document.getElementById('modeLabels').classList.toggle('on', m=='labels');
  help.innerHTML = m=='draw'
    ? '<b>Drag</b> to draw the course freehand. Each drag continues the line. '
      + 'The line is the path — land crossings allowed. Close the loop near your start.'
    : m=='wp'
    ? '<b>Click</b>: add waypoint (on a segment: insert)<br><b>Drag</b>: move • '
      + '<b>Right-click</b>: delete<br>The router finds water between points.'
    : m=='crop'
    ? '<b>Drag</b> a rectangle: that area becomes the board, scaled to 255 mm '
      + 'on its long side. Hole spacing is computed at board scale.'
    : m=='feat'
    ? '<b>Click</b> to drop polygon vertices around the missing feature (turn on '
      + 'the satellite overlay to trace). <b>Finish</b> closes &amp; saves it.'
    : '<b>Drag</b> a label to place it by hand (blue = hand-placed, gold = your '
      + 'place names). <b>Right-click</b>: revert auto label / delete place name. '
      + 'The baked-in map text moves after Save &amp; Re-route.';
  draw(); }
function drawCrop(){
  const c = cropDrag || crop;
  if(!c) return;
  const [x0,y0]=ll2px([c[0],c[3]]), [x1,y1]=ll2px([c[2],c[1]]);
  ctx.save();
  ctx.fillStyle='rgba(0,0,0,.45)';
  ctx.beginPath();
  ctx.rect(0,0,cv.width,cv.height);
  ctx.rect(x0,y0,x1-x0,y1-y0);
  ctx.fill('evenodd');
  ctx.strokeStyle='#fff'; ctx.lineWidth=Math.max(1.5,3/zoom);
  ctx.setLineDash([10/zoom,6/zoom]);
  ctx.strokeRect(x0,y0,x1-x0,y1-y0);
  ctx.restore();
}
function labelBox(lb){
  const [x,y]=ll2px([lb.lon,lb.lat]);
  const s = imgW/(labGrid?labGrid[0]:imgW);
  return [x, y, lb.hw*s, lb.hh*s];
}
function customBox(cl){
  const [x,y]=ll2px([cl.lon,cl.lat]);
  const s = imgW/(labGrid?labGrid[0]:imgW);
  const size = cl.size||6.5, mmpp = labMmpp||0.07;
  return [x, y, cl.text.length*size*0.36/mmpp*s, size*0.62/mmpp*s];
}
function drawOneLabel(x,y,hw,hh,text,fill,box){
  ctx.font='bold '+Math.max(8, 2*hh*0.9)+'px sans-serif';
  ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.strokeStyle='rgba(0,0,0,.85)'; ctx.lineWidth=Math.max(2,4/zoom);
  ctx.strokeText(text,x,y);
  ctx.fillStyle=fill; ctx.fillText(text,x,y);
  ctx.strokeStyle=box; ctx.lineWidth=Math.max(1,1.5/zoom);
  ctx.strokeRect(x-hw,y-hh,2*hw,2*hh);
}
function drawLabels(){
  if(mode!='labels') return;
  labs.forEach((lb,i)=>{
    const [x,y,hw,hh]=labelBox(lb);
    const sel = selKind=='auto'&&selIdx==i;
    drawOneLabel(x,y,hw,hh,lb.text,
      labOverrides[lb.text] ? '#7dd3fc' : '#ffffff',
      sel ? '#34d399' : (labOverrides[lb.text] ? 'rgba(125,211,252,.7)' : 'rgba(255,255,255,.35)'));
  });
  customLabels.forEach((cl,i)=>{
    const [x,y,hw,hh]=customBox(cl);
    const sel = selKind=='custom'&&selIdx==i;
    drawOneLabel(x,y,hw,hh,cl.text,'#fbbf24', sel ? '#34d399' : 'rgba(251,191,36,.7)');
  });
}
function setSel(kind,i){ selKind=kind; selIdx=i;
  const inp=document.getElementById('labSize');
  if(kind=='custom') inp.value=customLabels[i].size||6.5;
  else if(kind=='auto') inp.value=labs[i].size||9.6;
  draw(); }
function applySize(v){
  v=Math.min(16,Math.max(3,v));
  document.getElementById('labSize').value=v;
  if(selKind=='custom'&&selIdx>=0){ customLabels[selIdx].size=v; }
  else if(selKind=='auto'&&selIdx>=0){
    const lb=labs[selIdx]; lb.size=v;
    if(labMmpp){ lb.hw=lb.text.length*v*0.36/labMmpp; lb.hh=v*0.62/labMmpp; }
    const o=labOverrides[lb.text];
    labOverrides[lb.text]={pos:(o&&o.pos)||(Array.isArray(o)?o:[lb.lon,lb.lat]), size:v};
  }
  draw(); }
function draw(){
  ctx.clearRect(0,0,cv.width,cv.height);
  drawCrop();
  drawLabels();
  if(mode=='feat' && featPts.length){
    ctx.strokeStyle='#34d399'; ctx.fillStyle='rgba(52,211,153,.25)';
    ctx.lineWidth=Math.max(2,3/zoom); ctx.beginPath(); ctx.moveTo(...featPts[0]);
    featPts.slice(1).forEach(p=>ctx.lineTo(...p)); if(featPts.length>2) ctx.closePath();
    ctx.fill(); ctx.stroke();
    featPts.forEach(p=>{ ctx.beginPath(); ctx.arc(p[0],p[1],Math.max(3,5/zoom),0,7);
      ctx.fillStyle='#34d399'; ctx.fill(); });
  }
  const pts=wps.map(ll2px), lw=Math.max(1.2, 2.2/zoom);
  if(pts.length>1){
    ctx.strokeStyle='rgba(80,220,255,.9)'; ctx.lineWidth=lw;
    if(mode=='wp') ctx.setLineDash([8/zoom,5/zoom]);
    ctx.beginPath(); ctx.moveTo(...pts[0]);
    pts.slice(1).forEach(p=>ctx.lineTo(...p)); ctx.stroke(); ctx.setLineDash([]); }
  if(mode=='wp'){
    const r=Math.max(4, 8/zoom);
    pts.forEach((p,i)=>{ ctx.beginPath(); ctx.arc(p[0],p[1],r,0,7);
      ctx.fillStyle = i==0 ? '#22c55e' : (i==pts.length-1 ? '#f97316' : '#38bdf8');
      ctx.fill(); ctx.strokeStyle='#000'; ctx.lineWidth=1.5/zoom; ctx.stroke();
      ctx.fillStyle='#000'; ctx.font='bold '+Math.max(5,9/zoom)+'px sans-serif';
      ctx.textAlign='center'; ctx.fillText(i+1, p[0], p[1]+3/zoom); });
  } else if(pts.length){
    const r=Math.max(4, 9/zoom);
    [[pts[0],'#22c55e'],[pts[pts.length-1],'#f97316']].forEach(([p,c])=>{
      ctx.beginPath(); ctx.arc(p[0],p[1],r,0,7); ctx.fillStyle=c; ctx.fill();
      ctx.strokeStyle='#000'; ctx.lineWidth=1.5/zoom; ctx.stroke(); });
  }
}
function setZoom(nz,cx,cy){ nz=Math.min(12,Math.max(0.05,nz));
  const px=(wrap.scrollLeft+cx)/zoom, py=(wrap.scrollTop+cy)/zoom;
  zoom=nz; stage.style.transform='scale('+zoom+')';
  wrap.scrollLeft=px*zoom-cx; wrap.scrollTop=py*zoom-cy; draw(); }
function fit(){ if(imgW) setZoom(Math.min(wrap.clientWidth/imgW, wrap.clientHeight/imgH),0,0); }
wrap.addEventListener('wheel', e=>{
  if(mode=='labels' && !e.ctrlKey && !e.metaKey){
    const rc=cv.getBoundingClientRect();
    const x=(e.clientX-rc.left)*(cv.width/rc.width), y=(e.clientY-rc.top)*(cv.height/rc.height);
    const ci=customHit(x,y), ai=ci<0?labelHit(x,y):-1;
    if(ci>=0||ai>=0){
      e.preventDefault();
      if(ci>=0) setSel('custom',ci); else setSel('auto',ai);
      const cur=parseFloat(document.getElementById('labSize').value)||9.6;
      applySize(cur + (e.deltaY<0?0.5:-0.5));
      return; } }
  if(e.ctrlKey||e.metaKey){ e.preventDefault();
  const r=wrap.getBoundingClientRect();
  setZoom(zoom*Math.exp(-e.deltaY*0.012), e.clientX-r.left, e.clientY-r.top); }}, {passive:false});
function evPos(e){ const r=cv.getBoundingClientRect();
  return [(e.clientX-r.left)*(cv.width/r.width), (e.clientY-r.top)*(cv.height/r.height)]; }
function hit(x,y){ const pts=wps.map(ll2px), r=Math.max(5,11/zoom);
  for(let i=0;i<pts.length;i++){ if(Math.hypot(pts[i][0]-x,pts[i][1]-y)<r) return i; } return -1; }
function nearestSeg(x,y){ const pts=wps.map(ll2px); let best=-1, bd=Math.max(5,10/zoom);
  for(let i=0;i<pts.length-1;i++){ const [ax,ay]=pts[i],[bx,by]=pts[i+1];
    const L2=(bx-ax)**2+(by-ay)**2; if(!L2) continue;
    let t=((x-ax)*(bx-ax)+(y-ay)*(by-ay))/L2; t=Math.max(0,Math.min(1,t));
    const d=Math.hypot(x-(ax+t*(bx-ax)), y-(ay+t*(by-ay)));
    if(d<bd){bd=d;best=i;} } return best; }
function labelHit(x,y){
  for(let i=labs.length-1;i>=0;i--){
    const [lx,ly,hw,hh]=labelBox(labs[i]);
    if(Math.abs(x-lx)<hw && Math.abs(y-ly)<hh) return i;
  }
  return -1;
}
function customHit(x,y){
  for(let i=customLabels.length-1;i>=0;i--){
    const [lx,ly,hw,hh]=customBox(customLabels[i]);
    if(Math.abs(x-lx)<hw && Math.abs(y-ly)<hh) return i;
  }
  return -1;
}
cv.addEventListener('mousedown', e=>{ const [x,y]=evPos(e);
  if(mode=='feat'){
    if(e.button==2){ featPts.pop(); } else { featPts.push([x,y]); }
    draw(); return; }
  if(mode=='labels'){
    const ci=customHit(x,y);
    if(e.button==2){
      if(ci>=0){ customLabels.splice(ci,1); }
      else { const i=labelHit(x,y); if(i>=0) delete labOverrides[labs[i].text]; }
      draw(); return; }
    if(ci>=0){ setSel('custom',ci); dragCustom=ci; return; }
    const i=labelHit(x,y);
    if(i>=0){ setSel('auto',i); dragLabel=i; }
    else setSel(null,-1);
    return; }
  if(mode=='crop'){
    if(e.button!=0) return;
    cropDrag=[...px2ll(x,y), ...px2ll(x,y)]; // temp [lon1,lat1,lon2,lat2]
    cropDrag._anchor=[x,y]; draw(); return; }
  if(mode=='draw'){
    if(e.button!=0) return;
    drawing=true; strokes.push(wps.length); wps.push(px2ll(x,y)); draw(); return; }
  if(e.button==2){ const i=hit(x,y); if(i>=0){ wps.splice(i,1); draw(); } return; }
  const i=hit(x,y);
  if(i>=0){ dragging=i; }
  else { const s=nearestSeg(x,y);
    if(s>=0){ wps.splice(s+1,0,px2ll(x,y)); dragging=s+1; }
    else { wps.push(px2ll(x,y)); dragging=wps.length-1; } }
  draw(); });
cv.addEventListener('mousemove', e=>{ const [x,y]=evPos(e);
  if(mode=='labels'){
    if(dragCustom>=0){
      const ll=px2ll(x,y);
      customLabels[dragCustom].lon=ll[0]; customLabels[dragCustom].lat=ll[1];
      draw(); }
    else if(dragLabel>=0){
      const ll=px2ll(x,y);
      const lb=labs[dragLabel];
      lb.lon=ll[0]; lb.lat=ll[1];
      const o=labOverrides[lb.text];
      labOverrides[lb.text]={pos:[ll[0],ll[1]], ...(o&&o.size?{size:o.size}:{})};
      draw(); }
    return; }
  if(mode=='crop' && cropDrag){
    const [ax,ay]=cropDrag._anchor;
    const p1=px2ll(Math.min(ax,x),Math.min(ay,y)), p2=px2ll(Math.max(ax,x),Math.max(ay,y));
    const a2=cropDrag._anchor;
    cropDrag=[Math.min(p1[0],p2[0]), Math.min(p1[1],p2[1]),
              Math.max(p1[0],p2[0]), Math.max(p1[1],p2[1])];
    cropDrag._anchor=a2; draw(); return; }
  if(mode=='draw' && drawing){
    const last=ll2px(wps[wps.length-1]);
    if(Math.hypot(x-last[0],y-last[1]) > 3) { wps.push(px2ll(x,y)); draw(); }
    return; }
  if(dragging>=0){ wps[dragging]=px2ll(x,y); draw(); } });
window.addEventListener('mouseup', ()=>{
  dragLabel=-1; dragCustom=-1;
  if(cropDrag){ if(Math.abs(cropDrag[2]-cropDrag[0])>1e-4) crop=cropDrag.slice(0,4);
    cropDrag=null; draw(); }
  if(drawing){ drawing=false;
    const s=strokes[strokes.length-1];
    if(wps.length-s<2){ wps.length=s; strokes.pop(); } draw(); }
  dragging=-1; });
cv.addEventListener('contextmenu', e=>e.preventDefault());
function payload(){ return JSON.stringify({
  mode: mode=='wp' ? 'waypoints' : 'drawn', waypoints: wps, crop: crop,
  label_overrides: labOverrides, custom_labels: customLabels,
  options: { start_holes: parseInt(document.getElementById('optStart').value)||2,
             end_marker: document.getElementById('optEnd').value,
             peg_storage: document.getElementById('optStorage').checked },
  min_radius_mm: parseFloat(document.getElementById('radius').value)||8 }); }
async function loadLabels(){ try{
  const r=await fetch('/labels'); const d=await r.json();
  labs=(d.labels||[]).filter(l=>!l.custom);
  labGrid=d.grid||null; labMmpp=d.mmpp||null; draw(); }catch(e){} }
document.getElementById('labSize').oninput=e=>{
  const v=parseFloat(e.target.value);
  if(!isNaN(v)) applySize(v); };
document.getElementById('addLabel').onclick=()=>{
  const t=document.getElementById('newLabel').value.trim();
  if(!t) return;
  const cx_=(wrap.scrollLeft+wrap.clientWidth/2)/zoom, cy_=(wrap.scrollTop+wrap.clientHeight/2)/zoom;
  const ll=px2ll(cx_,cy_);
  customLabels.push({text:t, lon:ll[0], lat:ll[1], size:6.5});
  document.getElementById('newLabel').value='';
  setMode('labels'); };
document.getElementById('fetchNames').onclick=async()=>{
  status.textContent='fetching place names from OSM…';
  await fetch('/waypoints',{method:'POST',body:payload()});  // save first
  const r=await fetch('/fetch_names',{method:'POST',body:'{}'});
  const out=await r.json();
  status.textContent=out.log||'done';
  const d=await (await fetch('/waypoints')).json();
  customLabels=d.custom_labels||[];
  setMode('labels'); };
async function loadRegions(){
  const d=await (await fetch('/regions')).json();
  const sel=document.getElementById('regionSel');
  sel.innerHTML=d.names.map(n=>'<option'+(n==d.active?' selected':'')+'>'+n+'</option>').join('');
  [MINLON,MINLAT,MAXLON,MAXLAT]=d.bbox;
  if(d.base_mm!=null) document.getElementById('baseMm').value=d.base_mm;
  if(d.exag!=null) document.getElementById('exagX').value=d.exag;
  window.regionKind=d.kind||'cribbage';
  document.getElementById('alignPanel').style.display = window.regionKind=='golf' ? 'block' : 'none';
  document.getElementById('satPanel').style.display = window.regionKind=='golf' ? 'block' : 'none';
  if(window.regionKind=='golf'){ document.getElementById('sat').src='/sat?'+Date.now(); }
  const ft=d.feature_transform||{};
  align={dx_m:ft.dx_m||0, dy_m:ft.dy_m||0,
         scale_x:ft.scale_x||ft.scale||1, scale_y:ft.scale_y||ft.scale||1, rot_deg:ft.rot_deg||0};
  document.getElementById('alSX').value=align.scale_x;
  document.getElementById('alSY').value=align.scale_y;
  document.getElementById('alRot').value=align.rot_deg;
}
let align={dx_m:0,dy_m:0,scale_x:1,scale_y:1,rot_deg:0};
async function applyAlign(){
  status.textContent='aligning… re-rendering';
  const r=await fetch('/align',{method:'POST',body:JSON.stringify(align)});
  const out=await r.json();
  status.textContent=out.ok ? ('dx '+align.dx_m.toFixed(1)+'m dy '+align.dy_m.toFixed(1)
    +'m  lon×'+align.scale_x.toFixed(3)+' lat×'+align.scale_y.toFixed(3)+' rot '+align.rot_deg+'°')
    : 'FAILED:\\n'+out.log;
  showingBase=false; img.src='/map.png?'+Date.now(); }
function alNudge(ax,ay){ const s=parseFloat(document.getElementById('alStep').value)||3;
  align.dx_m+=ax*s; align.dy_m+=ay*s; applyAlign(); }
for(const [id,ax,ay] of [['alN',0,1],['alS',0,-1],['alE',1,0],['alW',-1,0],
    ['alNE',1,1],['alNW',-1,1],['alSE',1,-1],['alSW',-1,-1]])
  document.getElementById(id).onclick=()=>alNudge(ax,ay);
document.getElementById('alReset').onclick=()=>{ align={dx_m:0,dy_m:0,scale_x:1,scale_y:1,rot_deg:0};
  document.getElementById('alSX').value=1; document.getElementById('alSY').value=1;
  document.getElementById('alRot').value=0; applyAlign(); };
document.getElementById('alSX').onchange=e=>{ align.scale_x=parseFloat(e.target.value)||1; applyAlign(); };
document.getElementById('alSY').onchange=e=>{ align.scale_y=parseFloat(e.target.value)||1; applyAlign(); };
document.getElementById('alRot').onchange=e=>{ align.rot_deg=parseFloat(e.target.value)||0; applyAlign(); };
document.getElementById('alSXup').onclick=()=>{ align.scale_x=+(align.scale_x+0.005).toFixed(3);
  document.getElementById('alSX').value=align.scale_x; applyAlign(); };
document.getElementById('alSXdn').onclick=()=>{ align.scale_x=+(align.scale_x-0.005).toFixed(3);
  document.getElementById('alSX').value=align.scale_x; applyAlign(); };
async function saveRegionParams(){
  const b=parseFloat(document.getElementById('baseMm').value),
        x=parseFloat(document.getElementById('exagX').value);
  if(isNaN(b)||isNaN(x)) return;
  await fetch('/region_params',{method:'POST',body:JSON.stringify({base_mm:b,exag:x})});
  status.textContent='saved base '+b+' mm, height ×'+x+' (applies on next 3MF/STL build)'; }
document.getElementById('baseMm').onchange=saveRegionParams;
document.getElementById('exagX').onchange=saveRegionParams;
document.getElementById('regionSel').onchange = async e=>{
  status.textContent='switching region… (rebuilding map, 1-2 min)';
  const r=await fetch('/region',{method:'POST',body:JSON.stringify({name:e.target.value})});
  const out=await r.json();
  if(out.bbox) [MINLON,MINLAT,MAXLON,MAXLAT]=out.bbox;
  status.textContent=out.log||'switched';
  showingBase=false; img.src='/map.png?'+Date.now();
  await loadRegions(); await load(); };
async function load(){ const r=await fetch('/waypoints'); const d=await r.json();
  wps=d.waypoints||[]; strokes=[]; crop=d.crop||null;
  labOverrides=d.label_overrides||{};
  customLabels=d.custom_labels||[];
  const op=d.options||{};
  document.getElementById('optStart').value=op.start_holes||2;
  document.getElementById('optEnd').value=op.end_marker||'double';
  document.getElementById('optStorage').checked=!!op.peg_storage;
  if(d.min_radius_mm) document.getElementById('radius').value=d.min_radius_mm;
  setMode(d.mode=='drawn'?'draw':'wp'); loadLabels(); }
document.getElementById('satOp').oninput=e=>{ document.getElementById('sat').style.opacity=e.target.value/100; };
let featPts=[], frame=null;
async function loadFrame(){ try{ frame=await (await fetch('/frame')).json(); }catch(e){} }
function px2llGolf(col,row){
  const F=frame; const xmm=col/F.imgW*F.BW, ymm=F.BH*(1-row/F.imgH);
  const uu=F.umin+xmm/F.mm_per_m, vv=F.vmin+ymm/F.mm_per_m;
  const r=F.theta_deg*Math.PI/180, c=Math.cos(r), s=Math.sin(r);
  const e=uu*c-vv*s, n=uu*s+vv*c;
  const mlon=111320*Math.cos(F.clat*Math.PI/180);
  return [F.clon+e/mlon, F.clat+n/111320];
}
document.getElementById('featDraw').onclick=async()=>{ await loadFrame(); featPts=[]; setMode('feat'); };
document.getElementById('featFinish').onclick=async()=>{
  if(featPts.length<3||!frame){ status.textContent='need 3+ vertices'; return; }
  const layer=document.getElementById('featType').value;
  const pts=featPts.map(p=>px2llGolf(p[0],p[1]));
  status.textContent='adding '+layer+'…'; featPts=[];
  const o=await (await fetch('/feature/add',{method:'POST',body:JSON.stringify({layer,pts})})).json();
  status.textContent=o.ok?'added '+layer:'failed'; img.src='/map.png?'+Date.now(); await loadFrame(); draw(); };
document.getElementById('featClear').onclick=async()=>{
  if(!confirm('Remove all hand-added features?'))return;
  await fetch('/feature/clear',{method:'POST',body:'{}'}); featPts=[];
  status.textContent='cleared'; img.src='/map.png?'+Date.now(); draw(); };
for(const [s,v] of [['fGmin','gV'],['fVmin','vV'],['fCorr','cV']])
  document.getElementById(s).oninput=e=>{ document.getElementById(v).textContent=e.target.value; };
document.getElementById('fDetect').onclick=async()=>{
  status.textContent='detecting fairways from satellite…';
  const o=await (await fetch('/detect_fairways',{method:'POST',body:JSON.stringify({
    gmin:+document.getElementById('fGmin').value, vmin:+document.getElementById('fVmin').value,
    corridor_m:+document.getElementById('fCorr').value})})).json();
  status.textContent=o.ok?o.log:'failed: '+o.log; img.src='/map.png?'+Date.now(); };
document.getElementById('fClear').onclick=async()=>{
  await fetch('/detect_fairways',{method:'POST',body:JSON.stringify({clear:true})});
  status.textContent='cleared detected fairways'; img.src='/map.png?'+Date.now(); };
document.getElementById('satLoad').onclick=async()=>{
  status.textContent='fetching satellite imagery…';
  const o=await (await fetch('/satellite',{method:'POST',body:'{}'})).json();
  status.textContent=o.ok?'satellite loaded':'failed: '+o.log;
  if(o.ok){ const s=document.getElementById('sat'); s.src='/sat?'+Date.now();
    if(+document.getElementById('satOp').value===0){ document.getElementById('satOp').value=70; s.style.opacity=0.7; } } };
document.getElementById('modeDraw').onclick=()=>setMode('draw');
document.getElementById('modeWp').onclick=()=>setMode('wp');
document.getElementById('modeCrop').onclick=()=>setMode('crop');
document.getElementById('modeLabels').onclick=()=>setMode('labels');
document.getElementById('nocrop').onclick=()=>{ crop=null; draw(); };
document.getElementById('zin').onclick=()=>setZoom(zoom*1.5, wrap.clientWidth/2, wrap.clientHeight/2);
document.getElementById('zout').onclick=()=>setZoom(zoom/1.5, wrap.clientWidth/2, wrap.clientHeight/2);
document.getElementById('zfit').onclick=fit;
document.getElementById('base').onclick=()=>{ showingBase=!showingBase;
  img.src=(showingBase?'/base.png?':'/map.png?')+Date.now(); };
document.getElementById('gmaps').onclick=()=>{
  const cx_=(wrap.scrollLeft+wrap.clientWidth/2)/zoom, cy_=(wrap.scrollTop+wrap.clientHeight/2)/zoom;
  const ll=px2ll(Math.min(Math.max(cx_,0),imgW), Math.min(Math.max(cy_,0),imgH));
  // match zoom: meters per screen px here vs Google's 156543*cos(lat)/2^z
  const mPerImgPx=(MAXLAT-MINLAT)*111320/imgH;
  const z=Math.min(18, Math.max(5, Math.round(
    Math.log2(156543.03*Math.cos(ll[1]*Math.PI/180)/(mPerImgPx/zoom)))));
  window.open('https://www.google.com/maps/@?api=1&map_action=map&center='
    +ll[1].toFixed(5)+','+ll[0].toFixed(5)+'&zoom='+z+'&basemap=terrain','_blank'); };
document.getElementById('undo').onclick=()=>{
  if(strokes.length){ wps.length=strokes.pop(); } else { wps.pop(); } draw(); };
document.getElementById('save').onclick = async ()=>{
  await fetch('/waypoints',{method:'POST',body:payload()});
  status.textContent='saved ('+wps.length+' points)'; };
document.getElementById('revert').onclick = load;
document.getElementById('clear').onclick = ()=>{ wps=[]; strokes=[]; draw(); };
document.getElementById('build').onclick = async ()=>{
  status.textContent='building 3MF… (1-2 min)';
  const r=await fetch('/build',{method:'POST',body:'{}'});
  const out=await r.json();
  if(out.ok){ status.textContent='built → downloading 3MF'; window.location=out.download; }
  else status.textContent='FAILED:\\n'+out.log; };
document.getElementById('route').onclick = async ()=>{
  status.textContent='routing… (1-2 min)';
  const r=await fetch('/run',{method:'POST',body:payload()});
  const out=await r.json();
  status.textContent=out.ok ? out.log : 'FAILED:\\n'+out.log;
  showingBase=false; img.src='/map.png?'+Date.now(); loadLabels(); };
let first=true;
img.onload = ()=>{ imgW=img.naturalWidth; imgH=img.naturalHeight;
  cv.width=imgW; cv.height=imgH; if(first){ first=false; fit(); } draw(); };
(async()=>{ await loadRegions(); await load(); })();
</script></body></html>"""

HTML = (HTML.replace("%MINLON%", str(MINLON)).replace("%MAXLON%", str(MAXLON))
            .replace("%MINLAT%", str(MINLAT)).replace("%MAXLAT%", str(MAXLAT)))

DASH_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Terrain Boards</title>
<style>
  body { margin:0; background:#14141c; color:#ddd; font:14px -apple-system,sans-serif; }
  header { padding:18px 26px; border-bottom:1px solid #2a2a3a; display:flex; align-items:center; gap:16px; }
  header h1 { font-size:19px; margin:0; color:#fff; }
  #status { color:#8fda8f; font-size:13px; }
  #grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:18px; padding:24px; }
  .card { background:#1d1d28; border:1px solid #2e2e40; border-radius:10px; overflow:hidden; }
  .card.active { border-color:#2563eb; }
  .thumb { width:100%; height:200px; object-fit:cover; background:#0c0c12; display:block; cursor:pointer; }
  .thumb.ph { display:flex; align-items:center; justify-content:center; color:#555; font-size:12px; }
  .meta { padding:10px 12px; }
  .meta h3 { margin:0 0 4px; font-size:15px; color:#fff; }
  .badge { font-size:11px; padding:2px 7px; border-radius:10px; background:#2e2e40; color:#bcd; }
  .badge.golf { background:#1f4d2e; color:#9f9; } .badge.cribbage { background:#3a2f4d; color:#caf; }
  .acts { display:flex; flex-wrap:wrap; gap:5px; padding:0 12px 12px; }
  button { border:0; border-radius:6px; background:#2e2e40; color:#eee; font-size:12px; padding:6px 9px; cursor:pointer; }
  button:hover { background:#3a3a52; } button.p { background:#2563eb; } button.p:hover { background:#3b82f6; }
  .newcard { border:2px dashed #3a3a52; border-radius:10px; display:flex; align-items:center;
             justify-content:center; min-height:260px; cursor:pointer; color:#8a8aa0; font-size:15px; }
  .newcard:hover { border-color:#2563eb; color:#cdf; }
  #modal { position:fixed; inset:0; background:rgba(0,0,0,.6); display:none; align-items:center; justify-content:center; }
  #panel { background:#1d1d28; border:1px solid #2e2e40; border-radius:12px; padding:22px; width:440px; max-height:86vh; overflow:auto; }
  #panel h2 { margin:0 0 14px; font-size:17px; }
  label { display:block; font-size:12px; color:#9a9ab0; margin:10px 0 3px; }
  input, select { width:100%; box-sizing:border-box; background:#22222e; color:#eee; border:1px solid #3a3a52; border-radius:6px; padding:8px; }
  .row { display:flex; gap:8px; } .row>* { flex:1; }
  .geo { max-height:150px; overflow:auto; margin-top:6px; }
  .geo div { padding:6px 8px; border-radius:5px; cursor:pointer; font-size:12px; color:#bcd; }
  .geo div:hover { background:#2e2e40; }
</style></head><body>
<header><h1>🗺 Terrain Boards</h1><span id="status">loading…</span></header>
<div id="grid"></div>
<div id="modal"><div id="panel">
  <h2>New project</h2>
  <label>Name<input id="nName" placeholder="e.g. pebble-beach"></label>
  <div class="row">
    <div><label>Type<select id="nKind"><option value="golf">golf course</option><option value="cribbage">cribbage board</option></select></label></div>
    <div><label>Terrain<select id="nSrc"><option value="usgs">USGS 3DEP (US land)</option><option value="noaa">NOAA CUDEM (US coast)</option><option value="terrarium">Terrarium (global)</option></select></label></div>
  </div>
  <label>Search a place</label>
  <div class="row"><input id="nQ" placeholder="course or place name"><button onclick="geo()">Find</button></div>
  <div class="geo" id="nGeo"></div>
  <label>Bounding box (W,S,E,N)</label>
  <input id="nBox" placeholder="-75.32,39.99,-75.30,40.01">
  <div style="margin-top:16px;display:flex;gap:8px;justify-content:flex-end">
    <button onclick="closeModal()">Cancel</button>
    <button class="p" id="nGo" onclick="create()">Create &amp; fetch terrain</button>
  </div>
</div></div>
<script>
const S=document.getElementById('status');
async function load(){
  const d=await (await fetch('/projects')).json();
  const g=document.getElementById('grid'); g.innerHTML='';
  for(const p of d.projects){
    const c=document.createElement('div'); c.className='card'+(p.active?' active':'');
    const th=p.thumb ? `<img class=thumb src="/thumb/${p.name}?${Date.now()}" onclick="openP('${p.name}')">`
                     : `<div class="thumb ph" onclick="openP('${p.name}')">no preview yet</div>`;
    c.innerHTML=th+`<div class=meta><h3>${p.name}</h3>
      <span class="badge ${p.kind}">${p.kind}</span> <span class=badge>${p.source}</span></div>
      <div class=acts>
        <button class=p onclick="openP('${p.name}')">Open</button>
        <button onclick="build('${p.name}')">Build</button>
        <button onclick="dup('${p.name}')">Duplicate</button>
        <button onclick="ren('${p.name}')">Rename</button>
        <button onclick="del('${p.name}')">Delete</button>
      </div>`;
    g.appendChild(c);
  }
  const nc=document.createElement('div'); nc.className='newcard'; nc.textContent='+ New project';
  nc.onclick=openModal; g.appendChild(nc);
  S.textContent=d.projects.length+' projects';
}
async function openP(n){ S.textContent='opening '+n+'…';
  await fetch('/region',{method:'POST',body:JSON.stringify({name:n})}); location='/editor'; }
async function build(n){ S.textContent='building '+n+'… (1-2 min)';
  await fetch('/region',{method:'POST',body:JSON.stringify({name:n})});
  const o=await (await fetch('/build',{method:'POST',body:'{}'})).json();
  if(o.ok){ S.textContent='built '+n+' → downloading 3MF'; window.location=o.download; }
  else S.textContent='build failed: '+o.log; load(); }
async function dup(n){ const nn=prompt('Duplicate "'+n+'" as:',n+'-copy'); if(!nn)return;
  const o=await (await fetch('/project/duplicate',{method:'POST',body:JSON.stringify({name:n,newname:nn})})).json();
  S.textContent=o.ok?'duplicated':'failed: '+o.log; load(); }
async function ren(n){ const nn=prompt('Rename "'+n+'" to:',n); if(!nn||nn===n)return;
  const o=await (await fetch('/project/rename',{method:'POST',body:JSON.stringify({name:n,newname:nn})})).json();
  S.textContent=o.ok?'renamed':'failed: '+o.log; load(); }
async function del(n){ if(!confirm('Delete "'+n+'" and its data?'))return;
  const o=await (await fetch('/project/delete',{method:'POST',body:JSON.stringify({name:n})})).json();
  S.textContent=o.ok?'deleted':'failed: '+o.log; load(); }
function openModal(){ document.getElementById('modal').style.display='flex'; }
function closeModal(){ document.getElementById('modal').style.display='none'; }
async function geo(){ const q=document.getElementById('nQ').value;
  const r=await (await fetch('/geocode?q='+encodeURIComponent(q))).json();
  const el=document.getElementById('nGeo'); el.innerHTML='';
  r.forEach(x=>{ const d=document.createElement('div'); d.textContent=x.name;
    d.onclick=()=>{ document.getElementById('nBox').value=x.bbox.map(v=>v.toFixed(5)).join(','); }; el.appendChild(d); }); }
async function create(){
  const name=document.getElementById('nName').value.trim();
  const box=document.getElementById('nBox').value.split(',').map(Number);
  if(!name||box.length!==4||box.some(isNaN)){ alert('need a name and a valid W,S,E,N bbox'); return; }
  document.getElementById('nGo').disabled=true; S.textContent='creating '+name+'… fetching terrain (up to ~1 min)';
  const o=await (await fetch('/project/create',{method:'POST',body:JSON.stringify({
    name, kind:document.getElementById('nKind').value, source:document.getElementById('nSrc').value, bbox:box})})).json();
  document.getElementById('nGo').disabled=false;
  if(o.ok){ closeModal(); S.textContent='created '+o.name; load(); }
  else S.textContent='create failed: '+o.log;
}
load();
</script></body></html>"""


def _regions_cfg():
    return json.load(open(os.path.join(ROOT, "data/regions.json")))

def _active():
    try:
        return _regions_cfg()["active"]
    except Exception:
        return "deer-isle"

def _wp_path():
    return os.path.join(ROOT, f"data/waypoints_{_active()}.json")

def _kind():
    try:
        cfg = _regions_cfg()
        return cfg["regions"][cfg["active"]].get("kind", "cribbage")
    except Exception:
        return "cribbage"

def _render_script():
    return "scripts/preview_golf.py" if _kind() == "golf" else "scripts/route_prototype.py"

def _build_script():
    return "scripts/make_golf_3mf.py" if _kind() == "golf" else "scripts/make_board_3mf.py"

def _save_thumb(name):
    src = os.path.join(ROOT, "data/route_prototype.png")
    if os.path.exists(src):
        import shutil
        shutil.copy(src, os.path.join(ROOT, f"data/preview_{name}.png"))

def _geocode(q):
    if not q.strip():
        return []
    import urllib.parse, urllib.request
    u = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 6})
    req = urllib.request.Request(u, headers={"User-Agent": "terrain-cribbage/1.0 (jakepevans@gmail.com)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
    except Exception:
        return []
    out = []
    for x in res:
        bb = x.get("boundingbox")  # [s, n, w, e]
        if not bb:
            continue
        out.append({"name": x.get("display_name", "")[:70],
                    "bbox": [float(bb[2]), float(bb[0]), float(bb[3]), float(bb[1])]})
    return out

def _run(script, timeout=900):
    env = dict(os.environ, PYTHONPATH=".pydeps")
    r = subprocess.run(["python3"] + script.split(), cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0, "\n".join((r.stdout + r.stderr).strip().splitlines()[-6:])

def _ensure_dem(name):
    """Fetch terrain (and golf features) the first time a seeded project is used
    on a fresh deploy — DEMs are too large to ship in the image."""
    cfg = _regions_cfg(); reg = cfg["regions"].get(name, {})
    src = reg.get("src_file")
    if src and not os.path.exists(os.path.join(ROOT, src)):
        _run(f"scripts/fetch_dem.py {name} 3000", timeout=600)
        if reg.get("kind") == "golf" and not os.path.exists(
                os.path.join(ROOT, f"data/golf_{name}.json")):
            _run("scripts/fetch_golf.py")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode())

    def _png(self, name, fallback=None):
        p = os.path.join(ROOT, "data", name)
        if not os.path.exists(p) and fallback:
            p = os.path.join(ROOT, "data", fallback)
        with open(p, "rb") as f:
            self._send(200, f.read(), "image/png")

    def _auth_ok(self):
        if not APP_PASSWORD:
            return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                _, pw = base64.b64decode(h[6:]).decode().split(":", 1)
                if pw == APP_PASSWORD:
                    return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Terrain Boards"')
        self.end_headers()
        return False

    def do_GET(self):
        if not self._auth_ok():
            return
        if self.path == "/":
            self._send(200, DASH_HTML, "text/html")
        elif self.path == "/editor":
            self._send(200, HTML, "text/html")
        elif self.path.startswith("/thumb/"):
            name = self.path[len("/thumb/"):].split("?")[0]
            p = os.path.join(ROOT, f"data/preview_{name}.png")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    self._send(200, f.read(), "image/png")
            else:
                self._send(404, b"not found", "text/plain")
        elif self.path == "/projects":
            cfg = _regions_cfg(); act = cfg["active"]
            out = []
            for nm, r in sorted(cfg["regions"].items()):
                out.append({"name": nm, "kind": r.get("kind", "cribbage"),
                            "source": r.get("source", "?"), "bbox": r["bbox"],
                            "active": nm == act,
                            "thumb": os.path.exists(os.path.join(ROOT, f"data/preview_{nm}.png"))})
            self._send(200, json.dumps({"projects": out, "active": act}))
        elif self.path.startswith("/geocode"):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._send(200, json.dumps(_geocode(q)))
        elif self.path.startswith("/map.png"):
            self._png("route_prototype.png")
        elif self.path.startswith("/base.png"):
            self._png("basemap.png", fallback="route_prototype.png")
        elif self.path.startswith("/sat"):
            p = os.path.join(ROOT, f"data/sat_{_active()}.png")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    self._send(200, f.read(), "image/png")
            else:
                self._send(404, b"no satellite", "text/plain")
        elif self.path.startswith("/download"):
            act = _active()
            p = os.path.join(ROOT, f"data/board_{act}.3mf")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "model/3mf")
                self.send_header("Content-Disposition", f'attachment; filename="{act}.3mf"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._send(404, b"no build yet - Build first", "text/plain")
        elif self.path == "/waypoints":
            p = _wp_path()
            self._send(200, open(p).read() if os.path.exists(p) else '{"waypoints":[]}')
        elif self.path == "/frame":
            try:
                import sys
                sys.path.insert(0, os.path.join(ROOT, "scripts"))
                from golf_common import board_frame, transform_golf, merge_extra
                from PIL import Image as _Im
                cfg = _regions_cfg(); act = cfg["active"]; reg = cfg["regions"][act]
                g = transform_golf(merge_extra(
                    json.load(open(os.path.join(ROOT, f"data/golf_{act}.json"))), act), reg)
                fr = board_frame(reg, g)
                im = _Im.open(os.path.join(ROOT, "data/route_prototype.png"))
                self._send(200, json.dumps({k: fr[k] for k in
                    ("BW", "BH", "mm_per_m", "theta_deg", "clon", "clat", "umin", "vmin")}
                    | {"imgW": im.size[0], "imgH": im.size[1]}))
            except Exception as e:
                self._send(200, json.dumps({"error": str(e)}))
        elif self.path == "/regions":
            cfg = _regions_cfg()
            act = cfg["active"]
            reg = cfg["regions"][act]
            self._send(200, json.dumps({"active": act,
                                        "names": sorted(cfg["regions"].keys()),
                                        "bbox": reg["bbox"],
                                        "kind": reg.get("kind", "cribbage"),
                                        "feature_transform": reg.get("feature_transform",
                                            {"dx_m": 0, "dy_m": 0, "scale_x": 1.0, "scale_y": 1.0, "rot_deg": 0}),
                                        "base_mm": reg.get("base_mm", 10.0),
                                        "exag": reg.get("exag", 5.0)}))
        elif self.path == "/labels":
            p = os.path.join(ROOT, "data/route_lanes.json")
            if not os.path.exists(p):
                self._send(200, '{"labels":[]}')
                return
            rl = json.load(open(p))
            cfg = _regions_cfg()
            act = cfg["active"]
            if rl.get("region", act) != act:   # stale layout from another region
                self._send(200, '{"labels":[]}')
                return
            lo, la0, hi, la1 = cfg["regions"][act]["bbox"]
            W, Hg = rl["grid"]
            mmpp = rl["mm_per_px"]
            out = []
            for lb in rl.get("labels", []):
                size = lb.get("size", 9.6)
                out.append({
                    "text": lb["text"],
                    "custom": lb.get("custom", False),
                    "size": size,
                    "lon": lo + lb["x"] / W * (hi - lo),
                    "lat": la1 - lb["y"] / Hg * (la1 - la0),
                    "hw": len(lb["text"]) * size * 0.36 / mmpp,
                    "hh": size * 0.62 / mmpp})
            self._send(200, json.dumps({"labels": out, "grid": [W, Hg], "mmpp": mmpp}))
        else:
            self._send(404, "{}")

    def do_POST(self):
        if not self._auth_ok():
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        path = _wp_path()
        if self.path == "/waypoints":
            json.dump(body, open(path, "w"), indent=1)
            self._send(200, '{"ok":true}')
        elif self.path in ("/project/rename", "/project/duplicate", "/project/delete"):
            import shutil, glob
            cfg = _regions_cfg()
            name = body.get("name")
            if name not in cfg["regions"]:
                self._send(400, json.dumps({"ok": False, "log": "unknown project"})); return
            if self.path == "/project/delete":
                if len(cfg["regions"]) <= 1:
                    self._send(400, json.dumps({"ok": False, "log": "can't delete the last project"})); return
                cfg["regions"].pop(name)
                if cfg["active"] == name:
                    cfg["active"] = sorted(cfg["regions"])[0]
                for f in glob.glob(os.path.join(ROOT, f"data/*_{name}.*")) + \
                         glob.glob(os.path.join(ROOT, f"data/dem_{name}.tif")):
                    try: os.remove(f)
                    except OSError: pass
                json.dump(cfg, open(os.path.join(ROOT, "data/regions.json"), "w"), indent=1)
                self._send(200, json.dumps({"ok": True})); return
            new = (body.get("newname") or "").strip().replace(" ", "-").lower()
            if not new or new in cfg["regions"]:
                self._send(400, json.dumps({"ok": False, "log": "bad or duplicate name"})); return
            if self.path == "/project/rename":
                cfg["regions"][new] = cfg["regions"].pop(name)
                if cfg["active"] == name:
                    cfg["active"] = new
            else:  # duplicate
                import copy
                cfg["regions"][new] = copy.deepcopy(cfg["regions"][name])
            # move/copy per-project data files (dem, golf, waypoints, features, preview)
            op = shutil.move if self.path == "/project/rename" else shutil.copy
            for suf in (f"dem_{name}.tif", f"golf_{name}.json", f"waypoints_{name}.json",
                        f"features_{name}.json", f"preview_{name}.png"):
                src = os.path.join(ROOT, "data", suf)
                if os.path.exists(src):
                    try: op(src, os.path.join(ROOT, "data", suf.replace(name, new, 1)))
                    except OSError: pass
            if self.path == "/project/rename" and "src_file" in cfg["regions"][new]:
                cfg["regions"][new]["src_file"] = f"data/dem_{new}.tif"
            elif self.path == "/project/duplicate":
                cfg["regions"][new]["src_file"] = f"data/dem_{new}.tif"
            json.dump(cfg, open(os.path.join(ROOT, "data/regions.json"), "w"), indent=1)
            self._send(200, json.dumps({"ok": True, "name": new}))
        elif self.path == "/project/create":
            import math as _m
            name = (body.get("name") or "").strip().replace(" ", "-").lower()
            cfg = _regions_cfg()
            if not name or name in cfg["regions"]:
                self._send(400, json.dumps({"ok": False, "log": "bad or duplicate name"})); return
            bbox = body["bbox"]; kind = body.get("kind", "golf"); source = body.get("source", "usgs")
            reg = {"bbox": bbox, "source": source, "src_file": f"data/dem_{name}.tif",
                   "src_m_per_px": None, "datum_m": 0, "kind": kind,
                   "exag": 4.0 if kind == "golf" else 5.0,
                   "base_mm": 8.0 if kind == "golf" else 10.0, "landmarks": []}
            if kind == "golf":
                reg["board_rotation_deg"] = None  # auto-fit
                reg["feature_transform"] = {"dx_m": 0, "dy_m": 0, "scale_x": 1.0, "scale_y": 1.0, "rot_deg": 0}
            prev_active = cfg["active"]
            cfg["regions"][name] = reg; cfg["active"] = name
            json.dump(cfg, open(os.path.join(ROOT, "data/regions.json"), "w"), indent=1)
            if not run_lock.acquire(blocking=False):
                self._send(409, json.dumps({"ok": False, "log": "busy"})); return
            try:
                ok, log = _run(f"scripts/fetch_dem.py {name} 3000", timeout=600)
                if not ok:   # roll back the half-made project
                    c = _regions_cfg(); c["regions"].pop(name, None); c["active"] = prev_active
                    json.dump(c, open(os.path.join(ROOT, "data/regions.json"), "w"), indent=1)
                    self._send(200, json.dumps({"ok": False, "log": "terrain fetch failed:\n" + log}))
                    return
                created = ok
                if ok and kind == "golf":
                    # datum at course low point, then fetch features + preview
                    import numpy as np
                    from PIL import Image as _Im
                    a = np.array(_Im.open(os.path.join(ROOT, reg["src_file"])), float)
                    a = a[a > -1e30]
                    cfg = _regions_cfg(); cfg["regions"][name]["datum_m"] = float(_m.floor(a.min()))
                    json.dump(cfg, open(os.path.join(ROOT, "data/regions.json"), "w"), indent=1)
                    ok, log = _run("scripts/fetch_golf.py")
                    if ok:
                        ok, log = _run(_render_script())
                    created = ok
                elif ok:
                    _run(_render_script())  # cribbage: writes a basemap even w/o a course
                if os.path.exists(os.path.join(ROOT, "data/route_prototype.png")):
                    _save_thumb(name)
                self._send(200, json.dumps({"ok": created, "log": log, "name": name}))
            finally:
                run_lock.release()
        elif self.path == "/build":
            act = _active()
            if _kind() != "golf":
                try:
                    rl = json.load(open(os.path.join(ROOT, "data/route_lanes.json")))
                    if rl.get("region") != act:
                        self._send(200, json.dumps({"ok": False,
                            "log": f"layout is for '{rl.get('region')}' — Save & Re-route first"}))
                        return
                except Exception:
                    self._send(200, json.dumps({"ok": False, "log": "no layout yet — Save & Re-route first"}))
                    return
            if not run_lock.acquire(blocking=False):
                self._send(409, json.dumps({"ok": False, "log": "a run is already in progress"}))
                return
            try:
                _ensure_dem(act)
                env = dict(os.environ, PYTHONPATH=".pydeps")
                r = subprocess.run(["python3", _build_script()], cwd=ROOT, env=env,
                                   capture_output=True, text=True, timeout=900)
                log = "\n".join((r.stdout + r.stderr).strip().splitlines()[-6:])
                ok = r.returncode == 0
                if ok:
                    _save_thumb(act)
                    import sys as _sys
                    if _sys.platform == "darwin":   # local dev: open in Bambu Studio
                        subprocess.run(["open", os.path.join(ROOT, f"data/board_{act}.3mf")])
                self._send(200, json.dumps({"ok": ok, "log": log, "download": "/download"}))
            finally:
                run_lock.release()
        elif self.path == "/align":
            cfg = _regions_cfg()
            reg = cfg["regions"][cfg["active"]]
            reg["feature_transform"] = {
                "dx_m": float(body.get("dx_m", 0.0)), "dy_m": float(body.get("dy_m", 0.0)),
                "scale_x": float(body.get("scale_x", 1.0)), "scale_y": float(body.get("scale_y", 1.0)),
                "rot_deg": float(body.get("rot_deg", 0.0))}
            json.dump(cfg, open(os.path.join(ROOT, "data/regions.json"), "w"), indent=1)
            if not run_lock.acquire(blocking=False):
                self._send(409, json.dumps({"ok": False, "log": "a run is in progress"}))
                return
            try:
                r = subprocess.run(["python3", "scripts/preview_golf.py"], cwd=ROOT,
                                   capture_output=True, text=True, timeout=300)
                if r.returncode == 0:
                    _save_thumb(_active())
                self._send(200, json.dumps({"ok": r.returncode == 0,
                    "log": "\n".join((r.stdout + r.stderr).strip().splitlines()[-3:])}))
            finally:
                run_lock.release()
        elif self.path == "/region_params":
            cfg = _regions_cfg()
            reg = cfg["regions"][cfg["active"]]
            if "base_mm" in body:
                reg["base_mm"] = float(body["base_mm"])
            if "exag" in body:
                reg["exag"] = float(body["exag"])
            json.dump(cfg, open(os.path.join(ROOT, "data/regions.json"), "w"), indent=1)
            self._send(200, '{"ok":true}')
        elif self.path == "/satellite":
            if not run_lock.acquire(blocking=False):
                self._send(409, json.dumps({"ok": False, "log": "busy"})); return
            try:
                ok, log = _run("scripts/fetch_satellite.py", timeout=200)
                self._send(200, json.dumps({"ok": ok, "log": log}))
            finally:
                run_lock.release()
        elif self.path in ("/feature/add", "/feature/clear"):
            act = _active()
            mp = os.path.join(ROOT, f"data/golf_manual_{act}.json")
            man = json.load(open(mp)) if os.path.exists(mp) else {"features": {}}
            if self.path == "/feature/clear":
                man = {"features": {}}
            else:
                layer = body["layer"]; pts = body["pts"]
                if len(pts) >= 3:
                    man.setdefault("features", {}).setdefault(layer, []).append({"pts": pts})
            json.dump(man, open(mp, "w"))
            if not run_lock.acquire(blocking=False):
                self._send(200, json.dumps({"ok": True, "log": "saved (render busy)"})); return
            try:
                ok, _ = _run("scripts/preview_golf.py")
                if ok:
                    _save_thumb(act)
                self._send(200, json.dumps({"ok": ok}))
            finally:
                run_lock.release()
        elif self.path == "/detect_fairways":
            act = _active()
            if not run_lock.acquire(blocking=False):
                self._send(409, json.dumps({"ok": False, "log": "busy"})); return
            try:
                if body.get("clear"):
                    p = os.path.join(ROOT, f"data/fwmask_{act}.png")
                    if os.path.exists(p):
                        os.remove(p)
                    ok, log = _run(_render_script())
                elif not os.path.exists(os.path.join(ROOT, f"data/sat_{act}.png")):
                    self._send(200, json.dumps({"ok": False, "log": "Load satellite first"})); return
                else:
                    gmin = body.get("gmin", 12); vmin = body.get("vmin", 70); corr = body.get("corridor_m", 45)
                    ok, log = _run(f"scripts/detect_fairways.py {gmin} {vmin} {corr}", timeout=200)
                    if ok:
                        ok, _ = _run(_render_script())
                if ok:
                    _save_thumb(act)
                self._send(200, json.dumps({"ok": ok, "log": log}))
            finally:
                run_lock.release()
        elif self.path == "/autofill":
            if not run_lock.acquire(blocking=False):
                self._send(409, json.dumps({"ok": False, "log": "busy"})); return
            try:
                ok, log = _run("scripts/autofill_fairways.py", timeout=120)
                if ok:
                    ok, _ = _run(_render_script())
                    _save_thumb(_active())
                self._send(200, json.dumps({"ok": ok, "log": log}))
            finally:
                run_lock.release()
        elif self.path == "/fetch_names":
            if not run_lock.acquire(blocking=False):
                self._send(409, json.dumps({"ok": False, "log": "a run is in progress"}))
                return
            try:
                r = subprocess.run(["python3", "scripts/fetch_names.py"], cwd=ROOT,
                                   capture_output=True, text=True, timeout=300)
                log = "\n".join((r.stdout + r.stderr).strip().splitlines()[-4:])
                self._send(200, json.dumps({"ok": r.returncode == 0, "log": log}))
            finally:
                run_lock.release()
        elif self.path == "/region":
            cfg = _regions_cfg()
            name = body.get("name")
            if name not in cfg["regions"]:
                self._send(400, json.dumps({"ok": False, "log": f"unknown region {name}"}))
                return
            cfg["active"] = name
            json.dump(cfg, open(os.path.join(ROOT, "data/regions.json"), "w"), indent=1)
            if not run_lock.acquire(blocking=False):
                self._send(200, json.dumps({"ok": True, "log": "switched (a run is in progress)",
                                            "bbox": cfg["regions"][name]["bbox"]}))
                return
            try:
                _ensure_dem(name)
                env = dict(os.environ, PYTHONPATH=".pydeps")
                r = subprocess.run(["python3", _render_script()], cwd=ROOT, env=env,
                                   capture_output=True, text=True, timeout=900)
                log = "\n".join((r.stdout + r.stderr).strip().splitlines()[-6:])
                if r.returncode == 0:
                    _save_thumb(name)
                self._send(200, json.dumps({"ok": True, "log": log,
                                            "bbox": cfg["regions"][name]["bbox"]}))
            finally:
                run_lock.release()
        elif self.path == "/run":
            if not run_lock.acquire(blocking=False):
                self._send(409, json.dumps({"ok": False, "log": "a run is already in progress"}))
                return
            try:
                json.dump(body, open(path, "w"), indent=1)
                _ensure_dem(_active())
                env = dict(os.environ, PYTHONPATH=".pydeps")
                r = subprocess.run(["python3", _render_script()], cwd=ROOT, env=env,
                                   capture_output=True, text=True, timeout=900)
                log = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
                if r.returncode == 0:
                    _save_thumb(_active())
                self._send(200, json.dumps({"ok": r.returncode == 0, "log": log}))
            finally:
                run_lock.release()
        else:
            self._send(404, "{}")


if __name__ == "__main__":
    print(f"terrain boards: http://{HOST}:{PORT}  (auth {'on' if APP_PASSWORD else 'off'})")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
