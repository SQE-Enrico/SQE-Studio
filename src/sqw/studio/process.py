"""Versioned process inputs, real mask candidates and wafer placement (never auto sign-off)."""
import copy
import math
from dataclasses import asdict
from pathlib import Path
from scipy.constants import e, h, hbar

from .. import cad, circuit, config, geometry
from ..geometry import Rect
from ..io import write_csv, write_json

DEFAULT_PROCESS = {'name': 'Al / high-resistivity Si', 'version': 'draft-1',
 'chip_width_um': 7000., 'chip_height_um': 7000., 'wafer_diameter_mm': 100.,
 'wafer_edge_exclusion_mm': 3., 'dicing_street_um': 100., 'write_field_width_um': 1000., 'write_field_height_um': 1000., 'min_metal_width_um': 1.,
 'min_metal_gap_um': 1., 'min_junction_width_nm': 80., 'overlay_tolerance_nm': 30.,
 'junction_width_nm': 240., 'junction_overlap_nm': 240., 'junction_bridge_um': 3.,
 'junction_kind': 'overlap', 'junction_asset_id': '', 'junction_cell': 'LAB_JJ',
 'junction_left_anchor_x_um': -4., 'junction_right_anchor_x_um': 4., 'junction_contact_y_um': 0.,
 'junction_declared_Ic_nA': 29.193, 'junction_declared_Cj_fF': 2.6274,
 'junction_layer_a': 2, 'junction_layer_b': 3, 'Jc_A_per_cm2': 50.,
 'specific_C_fF_per_um2': 45., 'qualified': False,
 'marker_size_um': 80., 'marker_width_um': 8., 'annotation_layer': 90,
 'text': 'SQE', 'text_height_um': 50., 'text_x_um': -2800., 'text_y_um': -2700.,
 'logo_asset_id': '', 'logo_width_um': 500., 'logo_x_um': 2200., 'logo_y_um': -2800.}


def document():
    return {'schema_version': 1, 'config': config.validate({}), 'process': copy.deepcopy(DEFAULT_PROCESS),
            'backends': {'cad': 'native', 'quantum': 'scipy', 'dynamics': 'scipy'},
            'readout_mode': None, 'notes': '', 'macro_parameters': {}}


def resolve(doc):
    p = {**DEFAULT_PROCESS, **doc.get('process', {})}
    errors = []
    for key, default in DEFAULT_PROCESS.items():
        value = p[key]
        if isinstance(default, bool):
            if type(value) is not bool: errors.append(f'{key}: expected boolean')
        elif isinstance(default, (float, int)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f'{key}: expected a finite number')
            elif key not in ('text_x_um','text_y_um','logo_x_um','logo_y_um','junction_left_anchor_x_um','junction_right_anchor_x_um','junction_contact_y_um') and value<=0:
                errors.append(f'{key}: must be positive')
        elif not isinstance(value, str): errors.append(f'{key}: expected text')
    if errors: raise ValueError('; '.join(errors))
    if p['junction_kind'] not in ('overlap','lab_gds'): raise ValueError('Choose overlap geometry or a laboratory GDS cell')
    if p['wafer_edge_exclusion_mm']*2 >= p['wafer_diameter_mm']: raise ValueError('No usable wafer remains')
    if p['wafer_diameter_mm']>450: raise ValueError('Wafer diameter above 450 mm requires a dedicated wafer provider')
    if min(p['min_metal_width_um'],p['min_metal_gap_um'])<.001 or p['min_junction_width_nm']<1:
        raise ValueError('Minimum features cannot be smaller than the 1 nm GDS database unit')
    if min(p['chip_width_um'],p['chip_height_um']) <= 2*100: raise ValueError('Chip is too small for the edge setback')
    for key in ('junction_layer_a','junction_layer_b','annotation_layer'):
        if int(p[key]) != p[key] or not 1<=p[key]<=32767: raise ValueError(f'{key}: invalid GDS layer')
    if len({1,p['junction_layer_a'],p['junction_layer_b'],p['annotation_layer'],97,98,99}) != 7:
        raise ValueError('Metal, junction, annotation and outline layers must be distinct')
    cfg = copy.deepcopy(doc.get('config', {}))
    cfg.setdefault('layout', {}).update(chip_size_um=p['chip_width_um'], chip_height_um=p['chip_height_um'])
    cfg.setdefault('materials', {}).update(junction_Jc_A_per_cm2=p['Jc_A_per_cm2'],
                                          junction_specific_C_fF_per_um2=p['specific_C_fF_per_um2'])
    area=p['junction_width_nm']*p['junction_overlap_nm']/1e6
    ic=(p['Jc_A_per_cm2']*area*1e-8 if p['junction_kind']=='overlap' else p['junction_declared_Ic_nA']*1e-9)
    cfg.setdefault('circuit', {}).update(EJ_GHz=hbar*ic/(2*e*h*1e9),
        Cj_fF_override=0. if p['junction_kind']=='overlap' else p['junction_declared_Cj_fF'])
    cfg = config.validate(cfg)
    if p['junction_kind']=='overlap': junction_rectangles(cfg,p)
    if cfg['layout']['cpw_width_um'] < p['min_metal_width_um']: raise ValueError('CPW width is below the process minimum')
    if min(cfg['layout']['cpw_gap_um'],cfg['layout']['pad_gap_um']) < p['min_metal_gap_um']:
        raise ValueError('CPW or pad gap is below the process minimum')
    return cfg,p


def wafer_positions(p):
    radius = (p['wafer_diameter_mm']/2-p['wafer_edge_exclusion_mm'])*1000
    w,h = p['chip_width_um'],p['chip_height_um']
    px,py = w+p['dicing_street_um'],h+p['dicing_street_um']
    nx,ny = int(radius/px)+1,int(radius/py)+1
    if (2*nx+1)*(2*ny+1)>20000: raise ValueError('Wafer preview exceeds the bounded placement grid')
    result = []
    for j in range(-ny,ny+1):
        for i in range(-nx,nx+1):
            x,y = i*px,j*py
            # Include half a street around every die, including at the circular edge.
            if math.hypot(abs(x)+px/2,abs(y)+py/2) <= radius:
                result.append({'id': f'D{len(result)+1:04d}', 'column': i, 'row': j, 'x_um': x, 'y_um': y})
    if len(result)>2000: raise ValueError('More than 2000 dies; use a dedicated wafer-layout provider')
    return result


def raster_rectangles(image, width_um, x, y):
    from PIL import Image
    image = image.convert('RGBA')
    if image.width*image.height>4_000_000: raise ValueError('Raster is too large')
    background = Image.new('RGBA',image.size,'white')
    background.alpha_composite(image)
    mask = background.convert('L')
    mask.thumbnail((128,128))
    scale = width_um/mask.width
    pixels = mask.load()
    rects = []
    for row in range(mask.height):
        column = 0
        while column<mask.width:
            if pixels[column,row] >= 128:
                column += 1
                continue
            start = column
            while column<mask.width and pixels[column,row]<128: column+=1
            rects.append(Rect(x+start*scale,y+(mask.height-row-1)*scale,
                              x+column*scale,y+(mask.height-row)*scale))
    return rects


def accessories(p, asset_path=None):
    from PIL import Image, ImageDraw, ImageFont
    rects = []
    layer = int(p['annotation_layer'])
    inset = max(p['marker_size_um'],100)*1.5
    for x in (-p['chip_width_um']/2+inset,p['chip_width_um']/2-inset):
        for y in (-p['chip_height_um']/2+inset,p['chip_height_um']/2-inset):
            s,t = p['marker_size_um']/2,p['marker_width_um']/2
            rects.extend([(Rect(x-s,y-t,x+s,y+t),layer,0),(Rect(x-t,y-s,x+t,y+s),layer,0)])
    if p['text']:
        text = str(p['text'])[:64]
        font = ImageFont.load_default(size=16)
        bounds = font.getbbox(text)
        image = Image.new('L',(max(1,bounds[2]-bounds[0]+2),max(1,bounds[3]-bounds[1]+2)),255)
        ImageDraw.Draw(image).text((1-bounds[0],1-bounds[1]),text,font=font,fill=0)
        width = p['text_height_um']*image.width/image.height
        rects.extend((r,layer,0) for r in raster_rectangles(image,width,p['text_x_um'],p['text_y_um']))
    if asset_path:
        with Image.open(asset_path) as image:
            rects.extend((r,layer,0) for r in raster_rectangles(image,p['logo_width_um'],p['logo_x_um'],p['logo_y_um']))
    for r,_,_ in rects:
        if min(r.x1-r.x0,r.y1-r.y0)<p['min_metal_width_um']:
            raise ValueError('An accessory feature is below the minimum metal width; increase its size')
        if r.x0 < -p['chip_width_um']/2 or r.x1>p['chip_width_um']/2 or r.y0 < -p['chip_height_um']/2 or r.y1>p['chip_height_um']/2:
            raise ValueError('An accessory extends outside the chip')
    return rects


def junction_rectangles(cfg,p):
    if min(p['junction_width_nm'],p['junction_overlap_nm']) < p['min_junction_width_nm']:
        raise ValueError('Junction geometry is below the lithographic minimum')
    w,o = p['junction_width_nm']/1000,p['junction_overlap_nm']/1000
    gap,bridge,y,lead = (cfg['layout'][k] for k in ('pad_gap_um','junction_em_gap_um','pad_y_um','junction_lead_width_um'))
    span = p['junction_bridge_um']
    if not bridge<span<gap: raise ValueError('Junction bridge must fit between the coarse contacts')
    if w>lead or o>=span: raise ValueError('Junction linewidth/overlap must fit inside the declared bridge and coarse leads')
    return [(Rect(-gap/2,y-lead/2,-span/2,y+lead/2),int(p['junction_layer_a']),0),
            (Rect(-span/2,y-w/2,o/2,y+w/2),int(p['junction_layer_a']),0),
            (Rect(span/2,y-lead/2,gap/2,y+lead/2),int(p['junction_layer_b']),0),
            (Rect(-o/2,y-w/2,span/2,y+w/2),int(p['junction_layer_b']),0)]


def export(doc,run,out,asset_path=None,junction_path=None):
    cfg,p = resolve(doc)
    from ..io import read_json
    geo = read_json(Path(run)/'layout/geometry.json')
    out = Path(out)
    out.mkdir(parents=True,exist_ok=True)
    rects = [(Rect(**r),1,0) for values in geo['metal'].values() for r in values]
    rects += accessories(p,asset_path)
    if p['junction_kind']=='overlap': rects += junction_rectangles(cfg,p)
    chip = Rect(**geo['chip'])
    for r in (Rect(chip.x0,chip.y0,chip.x1,chip.y0+2),Rect(chip.x0,chip.y1-2,chip.x1,chip.y1),
              Rect(chip.x0,chip.y0,chip.x0+2,chip.y1),Rect(chip.x1-2,chip.y0,chip.x1,chip.y1)):
        rects.append((r,99,0))
    positions = wafer_positions(p)
    if not positions: raise ValueError('No chip fits inside the usable wafer')
    cad.write_library(out/'chip_candidate.gds',[{'name':'SQE_CHIP','rectangles':rects}])
    refs = [('SQE_CHIP',d['x_um'],d['y_um']) for d in positions]
    wafer_rects = []
    radius = p['wafer_diameter_mm']*500
    # Fine rectangular marks approximate the wafer perimeter on an annotation layer.
    for i in range(360):
        theta = i*math.pi/180
        x,y = radius*math.cos(theta),radius*math.sin(theta)
        wafer_rects.append((Rect(x-10,y-10,x+10,y+10),97,0))
    cad.write_library(out/'wafer_candidate.gds',[{'name':'SQE_CHIP','rectangles':rects},
        {'name':'SQE_WAFER','rectangles':wafer_rects,'references':refs}])
    if p['junction_kind']=='lab_gds':
        if junction_path is None: raise ValueError('Select an uploaded laboratory junction GDS')
        import shutil
        import klayout.db as kdb
        from .. import assembly
        from ..io import sha256
        shutil.copy2(junction_path,out/'lab_junction.gds')
        manifest={'schema_version':1,'process_name':p['name'],'process_version':p['version'],
          'junction_gds':'lab_junction.gds','junction_cell':p['junction_cell'],
          'junction_gds_sha256':sha256(out/'lab_junction.gds'),
          'contact_layers':[[int(p['junction_layer_a']),0],[int(p['junction_layer_b']),0]],
          'left_anchor_um':[p['junction_left_anchor_x_um'],p['junction_contact_y_um']],
          'right_anchor_um':[p['junction_right_anchor_x_um'],p['junction_contact_y_um']],
          'Ic_nA':p['junction_declared_Ic_nA'],'Cj_fF':p['junction_declared_Cj_fF'],
          'electrical_tolerance_relative':.05}
        write_json(out/'cell_manifest.json',manifest)
        assembly.assemble(run,out/'cell_manifest.json',out/'cell_validation')
        target,source=kdb.Layout(),kdb.Layout()
        target.read(str(out/'chip_candidate.gds')); source.read(str(out/'lab_junction.gds'))
        chip=target.top_cell(); junction=target.create_cell('LAB_JJ')
        junction.copy_tree(source.cell(p['junction_cell']))
        chip.insert(kdb.CellInstArray(junction.cell_index(),kdb.Trans(0,round(cfg['layout']['pad_y_um']/target.dbu))))
        target.write(str(out/'chip_candidate.gds'))
        wafer=target.create_cell('SQE_WAFER')
        for die in positions:
            wafer.insert(kdb.CellInstArray(chip.cell_index(),kdb.Trans(round(die['x_um']/target.dbu),round(die['y_um']/target.dbu))))
        for r,layer,datatype in wafer_rects:
            wafer.shapes(target.layer(layer,datatype)).insert(kdb.Box(*(round(v/target.dbu) for v in (r.x0,r.y0,r.x1,r.y1))))
        target.write(str(out/'wafer_candidate.gds'))
    write_csv(out/'wafer_map.csv',{key:[r[key] for r in positions] for key in positions[0]})
    fields=[]
    nx,ny=math.ceil(p['chip_width_um']/p['write_field_width_um']),math.ceil(p['chip_height_um']/p['write_field_height_um'])
    if nx*ny>20000: raise ValueError('More than 20000 write fields require a dedicated planning provider')
    for j in range(ny):
        for i in range(nx):
            fields.append({'field':len(fields)+1,'x_um':-p['chip_width_um']/2+(i+.5)*p['write_field_width_um'],'y_um':-p['chip_height_um']/2+(j+.5)*p['write_field_height_um']})
    write_csv(out/'write_field_plan.csv',{key:[f[key] for f in fields] for key in fields[0]})
    electrical = circuit.junction(cfg)
    area = p['junction_width_nm']*p['junction_overlap_nm']/1e6
    result = {'status':'PROCESS_REVIEW_REQUIRED','process':p,'die_count':len(positions),
       'junction_source':p['junction_kind'],
       'junction_design_area_um2':area if p['junction_kind']=='overlap' else None,
       'junction_design_Ic_nA':p['Jc_A_per_cm2']*area*10 if p['junction_kind']=='overlap' else p['junction_declared_Ic_nA'],
       'junction_electrical_target':electrical,
       'scope':'Plan-view electrode design intent. No evaporation stencil, resist undercut, dose or oxidation qualification is implied.',
       'annotations_in_em':False,'qualified_input_flag':p['qualified']}
    write_json(out/'process_review.json',result)
    return result
