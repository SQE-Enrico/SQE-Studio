/* Graphs visualize the saved declarative model only; NOT a QGeometry or LVS result. */
function gridLines(){return Array.from({length:17},(_,i)=>`<path class="canvas-grid" d="M ${i*32} 0 V 300"/>`).join('')+Array.from({length:10},(_,i)=>`<path class="canvas-grid" d="M 0 ${i*32} H 520"/>`).join('')}
function svgFrame(label,body,caption){return `<div class="canvas-shell"><div class="canvas-toolbar"><strong>${esc(label)}</strong><span>DECLARATIVE PREVIEW · NOT VERIFIED</span></div><svg class="design-canvas" viewBox="0 0 520 300" role="group" aria-label="${esc(label)}. ${esc(caption)}" xmlns="http://www.w3.org/2000/svg">${gridLines()}${body}</svg><p class="canvas-caption">${esc(caption)}</p></div><div id="canvasDetail" class="canvas-detail" aria-live="polite">Select a visual item for its exact model values. Keyboard: Tab then Enter or Space.</div>`}
function schematicCanvas(schematic){
 const nodes=[...new Set([...(schematic.nodes||[]),...schematic.elements.flatMap(e=>[e.a,e.b])])].slice(0,9);
 if(!schematic.elements.length)return svgFrame('Schematic connectivity',`<text class="canvas-empty" x="260" y="150" text-anchor="middle">No circuit elements defined</text>`,'Add a circuit element to preview logical connectivity. No electrical equivalence is inferred.');
 const coords=new Map(nodes.map((n,i)=>[n,{x:65+(i%3)*194,y:61+Math.floor(i/3)*93}]));
 const elems=schematic.elements.slice(0,12);
 const wires=elems.map((e,i)=>{
  const a=coords.get(e.a),b=coords.get(e.b);if(!a||!b)return '';
  const x=(a.x+b.x)/2,y=(a.y+b.y)/2+(i%3-1)*12;
  return `<path class="canvas-wire" d="M ${a.x} ${a.y} L ${b.x} ${b.y}"/><g class="canvas-action" role="button" tabindex="0" data-canvas="element" data-index="${i}" aria-label="Inspect ${esc(e.id)}, ${esc(e.type)}"><rect class="canvas-part" x="${x-28}" y="${y-14}" width="56" height="28" rx="6"/><text class="canvas-part-label" text-anchor="middle" x="${x}" y="${y+4}">${esc(e.id.slice(0,7))}</text></g>`;
 }).join('');
 const circles=nodes.map(n=>{const p=coords.get(n);return `<circle class="canvas-node" cx="${p.x}" cy="${p.y}" r="7"/><text class="canvas-node-label" x="${p.x+12}" y="${p.y-10}">${esc(n.slice(0,17))}</text>`}).join('');
 const extra=schematic.elements.length>12||[...new Set([...(schematic.nodes||[]),...schematic.elements.flatMap(e=>[e.a,e.b])])].length>9;
 return svgFrame('Schematic connectivity',wires+circles+(extra?`<text class="canvas-key" x="16" y="286">Subset shown · see table for full model</text>`:''),'Schematic node/element intent only. Lines are logical connections; no routing, netlist validation, LVS or electrical solving.');
}
function layoutCanvas(layout){
 const chip=layout.chip||{},w=Number(chip.width_mm),h=Number(chip.height_mm);
 const valid=Number.isFinite(w)&&Number.isFinite(h)&&w>0&&h>0;
 if(!valid)return svgFrame('Quantum Metal placement',`<text class="canvas-empty" x="260" y="150" text-anchor="middle">Enter positive chip dimensions</text>`,'Cannot preview an invalid chip. No native Quantum Metal geometry exists here.');
 const scale=Math.min(348/w,218/h),cw=w*scale,ch=h*scale,x0=260-cw/2,y0=152-ch/2;
 const chipShape=`<rect class="canvas-chip" x="${x0}" y="${y0}" width="${cw}" height="${ch}" rx="3"/><text class="canvas-title" x="${x0}" y="${Math.max(14,y0-12)}">${esc(w)} × ${esc(h)} mm · chip outline</text>`;
 const componentByName=new Map(layout.components.filter(c=>!isRoute(c.kind)).map(c=>[c.name,c]));
 const routes=layout.components.filter(c=>isRoute(c.kind)).slice(0,32).map(c=>{
  const a=componentByName.get(c.start?.component),b=componentByName.get(c.end?.component);
  if(!a||!b)return '';
  const x1=x0+cw/2+a.x_mm*scale,y1=y0+ch/2-a.y_mm*scale;
  const x2=x0+cw/2+b.x_mm*scale,y2=y0+ch/2-b.y_mm*scale;
  return `<g><path d="M ${x1} ${y1} L ${x2} ${y2}" class="canvas-route-intent"/><text x="${(x1+x2)/2}" y="${(y1+y2)/2-8}" class="canvas-key" text-anchor="middle">${esc(c.name)}</text></g>`;
 }).join('');
 const markers=layout.components.map((c,i)=>({c,i})).filter(x=>!isRoute(x.c.kind)).slice(0,32).map(({c,i})=>{
  const x=x0+cw/2+Number(c.x_mm)*scale,y=y0+ch/2-Number(c.y_mm)*scale;
  if(!Number.isFinite(x)||!Number.isFinite(y))return '';
  const px=Math.max(16,Math.min(502,x)),py=Math.max(20,Math.min(282,y));
  return `<g class="canvas-action" role="button" tabindex="0" data-canvas="layout" data-index="${i}" aria-label="Inspect ${esc(c.name)} placement"><circle class="canvas-part" cx="${px}" cy="${py}" r="10"/><path class="canvas-wire" d="M ${px-4} ${py} h 8 M ${px} ${py-4} v 8"/><text class="canvas-part-label" x="${px+14}" y="${py-12}">${esc(c.name.slice(0,12))}</text></g>`;
 }).join('');
 const extra=layout.components.length>32?`<text class="canvas-key" x="14" y="286">First 32 placements shown</text>`:'';
 return svgFrame('Quantum Metal placement intent',chipShape+routes+markers+extra,'Symbols and dashed lines denote connectivity/placement intent only — not native QGeometry, routed bends, dimensions, DRC, or GDS.');
}
function wireCanvas(){document.querySelectorAll('[data-canvas]').forEach(el=>{
  const activate=()=>{const index=Number(el.dataset.index);const data=el.dataset.canvas==='element'?activeModel().schematic.elements[index]:activeModel().layout.components[index];if(!data)return;
   document.querySelectorAll('[data-canvas] .canvas-part').forEach(p=>p.classList.remove('selected'));
   el.querySelector('.canvas-part')?.classList.add('selected');$('canvasDetail').textContent=`${el.dataset.canvas==='element'?'Electrical intent':'Placement intent'} · ${Object.entries(data).map(([k,v])=>k+': '+String(v)).join('  |  ')} · NOT VERIFIED`;};
  el.addEventListener('click',activate);el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate()}});
 })}
