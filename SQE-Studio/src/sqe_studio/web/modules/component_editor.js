/* Generic property inspectors for the SAME project. No simulator or preview geometry here. */
const numeric=(id,description,number)=>field(description,id,number===undefined?'':number,'number');
const selection=(id,label,items,value)=>`<label class="form-field"><span>${esc(label)}</span><select id="${id}">${items.map(item=>{const [v,t]=Array.isArray(item)?item:[item,item];return `<option value="${esc(v)}" ${v===value?'selected':''}>${esc(t)}</option>`}).join('')}</select></label>`;
const optionalNumber=(id,label,value)=>numeric(id,label,value);
const readNumber=(id,{optional=false,integer=false,min=-Infinity,max=Infinity}={})=>{
 const raw=$(id)?.value.trim();if(raw===''&&optional)return undefined;
 if(raw==='')throw Error(`${id}: enter a number`);
 const v=Number(raw);if(!Number.isFinite(v)||v<min||v>max||(integer&&!Number.isInteger(v)))throw Error(`${id}: invalid numeric value`);return v;
};
const readText=(id,required=true)=>{const text=$(id)?.value.trim()||'';if(required&&!text)throw Error(`${id}: required`);return text};
const componentInfo=kind=>componentCatalog.find(c=>c.kind===kind);
const isRoute=kind=>!!componentInfo(kind)?.route;
function componentDialog(index,kind){
 const c=index>=0?activeModel().layout.components[index]:{kind,name:'',x_mm:0,y_mm:0};kind=c.kind||kind;
 const info=componentInfo(kind);if(!info)return toast('Unknown reviewed component type',true);
 const base=`<p class="helper">${esc(kind)} · Quantum Metal will generate the actual geometry from this validated, declarative recipe.</p>
 <div class="row">${field('Component ID','editPartName',c.name||'')}${numeric('editPartLayer','QGeometry layer',c.layer??1)}</div>`;
 let form;
 if(isRoute(kind)){
 const endpoint=(label,prefix,value)=>`<div class="row">${selection(prefix+'Component',label+' component',activeModel().layout.components.filter(p=>!isRoute(p.kind)).map(p=>p.name),value?.component)}${field(label+' pin',prefix+'Pin',value?.pin||'')}</div>`;
 form=`${base}${field('Net identity','editPartNet',c.net||'')}${endpoint('Start','editPartStart',c.start)}${endpoint('End','editPartEnd',c.end)}
 <div class="row">${optionalNumber('editPartTraceWidth','Trace width · µm',c.trace_width_um)}${optionalNumber('editPartTraceGap','Trace gap · µm',c.trace_gap_um)}${optionalNumber('editPartFillet','Fillet · µm',c.fillet_um)}</div>
 ${kind==='RouteMeander'?`<div class="row">${optionalNumber('editPartLength','Total length · mm',c.total_length_mm)}${optionalNumber('editPartSpacing','Meander spacing · µm',c.meander?.spacing_um)}</div>`:''}
 ${kind==='RouteAnchors'||kind==='RoutePathfinder'?textarea('Anchors · one x_mm,y_mm per line','editPartAnchors',(c.anchors||[]).map(a=>a.x_mm+','+a.y_mm).join('\n')):''}
 ${kind==='RoutePathfinder'?optionalNumber('editPartStep','Route step · µm',c.step_size_um):''}`;
 } else {
  form=`${base}<div class="row">${numeric('editPartX','X · mm',c.x_mm)}${numeric('editPartY','Y · mm',c.y_mm)}${numeric('editPartAngle','Rotation · degrees',c.orientation_deg??0)}</div>
  ${(info.options||[]).length?`<details class="config-details" open><summary>Parametric QComponent dimensions · µm</summary><div class="form-grid">${info.options.map(o=>optionalNumber('partOpt_'+o,o.replaceAll('_',' '),c.options?.[o+'_um'])).join('')}</div></details>`:''}
  ${info.requires_subtract_layer?numeric('editPartSubtract','Subtraction layer',c.subtract_layer??2):''}`;
 }
 openDialog(index>=0?'Edit QComponent':'Add QComponent',`${form}<p class="helper">Review the pin identities and physical distances in the installed Quantum Metal geometry before any EM analysis. These controls do not imply GDS/DRC approval.</p><button class="primary full" id="confirmPart">${index>=0?'Update component':'Add component'}</button>`);
 $('confirmPart').onclick=()=>{try{
  const name=readText('editPartName');if(!/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(name))throw Error('Use an ASCII QComponent ID (1–40 characters)');
  if(activeModel().layout.components.some((x,i)=>x.name===name&&i!==index))throw Error('Duplicate QComponent ID');
  const out={kind,name};const layer=readNumber('editPartLayer',{integer:true,min:1,max:255});if(layer!==1||c.layer!==undefined)out.layer=layer;
  if(isRoute(kind)){
   out.net=readText('editPartNet');out.start={component:readText('editPartStartComponent'),pin:readText('editPartStartPin')};out.end={component:readText('editPartEndComponent'),pin:readText('editPartEndPin')};
   for(const [id,key] of [['editPartTraceWidth','trace_width_um'],['editPartTraceGap','trace_gap_um'],['editPartFillet','fillet_um']]){const v=readNumber(id,{optional:true,min:0});if(v!==undefined)out[key]=v}
   if(kind==='RouteMeander'){
    const length=readNumber('editPartLength',{optional:true,min:0.01});if(length!==undefined)out.total_length_mm=length;
    const spacing=readNumber('editPartSpacing',{optional:true,min:1});if(spacing!==undefined)out.meander={spacing_um:spacing};
   }
   if(kind==='RouteAnchors'||kind==='RoutePathfinder'){
    const raw=readText('editPartAnchors',false);if(raw){out.anchors=raw.split(/\n/).map(line=>{const parts=line.split(',');if(parts.length!==2||parts.some(s=>!s.trim()||!Number.isFinite(Number(s))))throw Error('Anchors require one numeric x,y pair per line');return {x_mm:Number(parts[0]),y_mm:Number(parts[1])}})}
   }
   if(kind==='RoutePathfinder'){
    out.constraints={avoid_collision:true};const size=readNumber('editPartStep',{optional:true,min:1});if(size!==undefined)out.step_size_um=size;
   }
  }else{
   out.x_mm=readNumber('editPartX',{min:-100,max:100});out.y_mm=readNumber('editPartY',{min:-100,max:100});
   const orientation=readNumber('editPartAngle',{min:-360,max:360});if(orientation)out.orientation_deg=orientation;
   const options={};for(const o of info.options){const value=readNumber('partOpt_'+o,{optional:true,min:0.01,max:100000});if(value!==undefined)options[o+'_um']=value};if(Object.keys(options).length)out.options=options;
   if(info.requires_subtract_layer)out.subtract_layer=readNumber('editPartSubtract',{integer:true,min:1,max:255});
   // Retain reviewed advanced pad/junction configuration until explicitly edited in expert schema.
   for(const key of ['connection_pads','junction_cell','n_turns'])if(c[key]!==undefined)out[key]=c[key];
  }
  if(index>=0)activeModel().layout.components[index]=out;else activeModel().layout.components.push(out);
  clearPhysicalReview();markDirty();closeDialog();render();
 }catch(e){toast(e.message,true)}};
}
function clearPhysicalReview(){if(activeModel().process?.source==='reviewed'){
 activeModel().process.source='unverified';delete activeModel().process.rules?.gui_review;
}}
function blankEMStudy(){return {id:'EM1',engine:'sqdmetal_palace',kind:'eigenmode',inputs:{em:{
 ground:{kind:'qdesign_ground_plane',layer:1,verified:false},
 boundaries:{x_neg_um:300,x_pos_um:300,y_neg_um:300,y_pos_um:300,z_neg_um:0,z_pos_um:500,farfield:'pec'},
 ports:[],mesh:{min_um:12,max_um:120,refinement_levels:[0,1],relative_tolerance:0.02},
 execution:'deck_only',solver:{order:1,tolerance:1e-7,max_iterations:100,num_cpus:2,start_hz:5e9,modes:1}
 }}}}
function selectedEMStudy(){return activeModel().studies.find(s=>s.engine==='sqdmetal_palace'&&s.id===emSelectedId&&s.inputs?.em?.ground)||activeModel().studies.find(s=>s.engine==='sqdmetal_palace'&&s.inputs?.em?.ground)||null}
// M2 A14: all choices originate from the exact saved-study input, not matrix indices.
