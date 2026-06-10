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
import json, os, subprocess, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8765
# must match route_prototype.py
MINLON, MAXLON, MINLAT, MAXLAT = -68.95, -68.44, 43.98, 44.36

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
  #status { margin-top:10px; font-size:12px; color:#8fda8f; white-space:pre-wrap; }
  #wrap { flex:1; overflow:auto; position:relative; background:#0a0a10; }
  #stage { position:relative; transform-origin: top left; }
  #map { display:block; user-select:none; -webkit-user-drag:none; }
  canvas { position:absolute; left:0; top:0; cursor:crosshair; }
</style></head><body>
<div id="side">
  <h2>Course editor</h2>
  <div class="row">
    <button id="modeDraw">✏️ Draw</button>
    <button id="modeWp">📍 Waypoints</button>
    <button id="modeCrop">▣ Crop</button>
  </div>
  <p id="help"></p>
  <div class="row">
    <button id="zin">＋</button><button id="zout">−</button><button id="zfit">Fit</button>
  </div>
  <button id="base">Toggle basemap</button>
  <label>Min bend radius (mm)
    <input type="number" id="radius" value="8" min="3" max="25" step="0.5"></label>
  <button class="primary" id="route">Save &amp; Re-route</button>
  <button id="save">Save only</button>
  <button id="undo">Undo stroke</button>
  <button id="nocrop">Clear crop (full map)</button>
  <button id="revert">Revert to saved</button>
  <button id="clear">Clear all</button>
  <div id="status">loaded</div>
</div>
<div id="wrap"><div id="stage">
  <img id="map" src="/map.png">
  <canvas id="cv"></canvas>
</div></div>
<script>
const MINLON=%MINLON%, MAXLON=%MAXLON%, MINLAT=%MINLAT%, MAXLAT=%MAXLAT%;
let wps=[], strokes=[], mode='draw', dragging=-1, drawing=false,
    zoom=1, imgW=0, imgH=0, showingBase=false, crop=null, cropDrag=null;
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
  help.innerHTML = m=='draw'
    ? '<b>Drag</b> to draw the course freehand. Each drag continues the line. '
      + 'The line is the path — land crossings allowed. Close the loop near your start.'
    : m=='wp'
    ? '<b>Click</b>: add waypoint (on a segment: insert)<br><b>Drag</b>: move • '
      + '<b>Right-click</b>: delete<br>The router finds water between points.'
    : '<b>Drag</b> a rectangle: that area becomes the board, scaled to 255 mm '
      + 'on its long side. Hole spacing is computed at board scale.';
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
function draw(){
  ctx.clearRect(0,0,cv.width,cv.height);
  drawCrop();
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
wrap.addEventListener('wheel', e=>{ if(e.ctrlKey||e.metaKey){ e.preventDefault();
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
cv.addEventListener('mousedown', e=>{ const [x,y]=evPos(e);
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
  if(cropDrag){ if(Math.abs(cropDrag[2]-cropDrag[0])>1e-4) crop=cropDrag.slice(0,4);
    cropDrag=null; draw(); }
  if(drawing){ drawing=false;
    const s=strokes[strokes.length-1];
    if(wps.length-s<2){ wps.length=s; strokes.pop(); } draw(); }
  dragging=-1; });
cv.addEventListener('contextmenu', e=>e.preventDefault());
function payload(){ return JSON.stringify({
  mode: mode=='wp' ? 'waypoints' : 'drawn', waypoints: wps, crop: crop,
  min_radius_mm: parseFloat(document.getElementById('radius').value)||8 }); }
async function load(){ const r=await fetch('/waypoints'); const d=await r.json();
  wps=d.waypoints||[]; strokes=[]; crop=d.crop||null;
  if(d.min_radius_mm) document.getElementById('radius').value=d.min_radius_mm;
  setMode(d.mode=='drawn'?'draw':'wp'); }
document.getElementById('modeDraw').onclick=()=>setMode('draw');
document.getElementById('modeWp').onclick=()=>setMode('wp');
document.getElementById('modeCrop').onclick=()=>setMode('crop');
document.getElementById('nocrop').onclick=()=>{ crop=null; draw(); };
document.getElementById('zin').onclick=()=>setZoom(zoom*1.5, wrap.clientWidth/2, wrap.clientHeight/2);
document.getElementById('zout').onclick=()=>setZoom(zoom/1.5, wrap.clientWidth/2, wrap.clientHeight/2);
document.getElementById('zfit').onclick=fit;
document.getElementById('base').onclick=()=>{ showingBase=!showingBase;
  img.src=(showingBase?'/base.png?':'/map.png?')+Date.now(); };
document.getElementById('undo').onclick=()=>{
  if(strokes.length){ wps.length=strokes.pop(); } else { wps.pop(); } draw(); };
document.getElementById('save').onclick = async ()=>{
  await fetch('/waypoints',{method:'POST',body:payload()});
  status.textContent='saved ('+wps.length+' points)'; };
document.getElementById('revert').onclick = load;
document.getElementById('clear').onclick = ()=>{ wps=[]; strokes=[]; draw(); };
document.getElementById('route').onclick = async ()=>{
  status.textContent='routing… (1-2 min)';
  const r=await fetch('/run',{method:'POST',body:payload()});
  const out=await r.json();
  status.textContent=out.ok ? out.log : 'FAILED:\\n'+out.log;
  showingBase=false; img.src='/map.png?'+Date.now(); };
let first=true;
img.onload = ()=>{ imgW=img.naturalWidth; imgH=img.naturalHeight;
  cv.width=imgW; cv.height=imgH; if(first){ first=false; fit(); } draw(); };
load();
</script></body></html>"""

HTML = (HTML.replace("%MINLON%", str(MINLON)).replace("%MAXLON%", str(MAXLON))
            .replace("%MINLAT%", str(MINLAT)).replace("%MAXLAT%", str(MAXLAT)))


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

    def do_GET(self):
        if self.path == "/":
            self._send(200, HTML, "text/html")
        elif self.path.startswith("/map.png"):
            self._png("route_prototype.png")
        elif self.path.startswith("/base.png"):
            self._png("basemap.png", fallback="route_prototype.png")
        elif self.path == "/waypoints":
            p = os.path.join(ROOT, "data/waypoints.json")
            self._send(200, open(p).read() if os.path.exists(p) else '{"waypoints":[]}')
        else:
            self._send(404, "{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        path = os.path.join(ROOT, "data/waypoints.json")
        if self.path == "/waypoints":
            json.dump(body, open(path, "w"), indent=1)
            self._send(200, '{"ok":true}')
        elif self.path == "/run":
            if not run_lock.acquire(blocking=False):
                self._send(409, json.dumps({"ok": False, "log": "a run is already in progress"}))
                return
            try:
                json.dump(body, open(path, "w"), indent=1)
                r = subprocess.run(["python3", "scripts/route_prototype.py"], cwd=ROOT,
                                   capture_output=True, text=True, timeout=900)
                log = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
                self._send(200, json.dumps({"ok": r.returncode == 0, "log": log}))
            finally:
                run_lock.release()
        else:
            self._send(404, "{}")


if __name__ == "__main__":
    print(f"course editor: http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
