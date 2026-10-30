"""Frozen interoperability contracts shared by independent engine adapters.

This module describes orchestration and never computes scientific quantities.
"""
from __future__ import annotations
import hashlib
import json
import math
import re

PROJECT_SCHEMA = 'sqe.project.v1'
ARTIFACT_SCHEMA = 'sqe.artifact.v1'
JOB_SCHEMA = 'sqe.job.v1'
STEP_IDS = ('intent', 'schematic', 'layout', 'em', 'quantum', 'results', 'fabrication')
STEPS = (
    {'id':'intent','label':'Specifications','icon':'target'},
    {'id':'schematic','label':'Schematic','icon':'circuit'},
    {'id':'layout','label':'Layout','icon':'layers'},
    {'id':'em','label':'EM analysis','icon':'waves'},
    {'id':'quantum','label':'Quantum models','icon':'atom'},
    {'id':'results','label':'Results','icon':'chart'},
    {'id':'fabrication','label':'Fabrication','icon':'chip'},
)
ENGINES = ('quantum_metal', 'sqdmetal_palace', 'scqubits', 'josephson_circuits')
LABEL = re.compile(r'^[A-Za-z][A-Za-z0-9_ -]{0,79}$')
IDENT = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,47}$')

class ValidationError(ValueError):
    pass

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')).hexdigest()

def _numbers_safe(obj, depth=0):
    if depth > 20:
        raise ValidationError('Object nesting exceeds 20')
    if isinstance(obj, dict):
        if len(obj) > 1024 or any(not isinstance(k,str) or len(k)>128 for k in obj):
            raise ValidationError('Invalid object keys')
        for v in obj.values(): _numbers_safe(v, depth+1)
    elif isinstance(obj, list):
        if len(obj) > 2048: raise ValidationError('Array exceeds limit')
        for v in obj: _numbers_safe(v, depth+1)
    elif isinstance(obj, float):
        if not math.isfinite(obj): raise ValidationError('Nonfinite numeric value')
    elif obj is not None and type(obj) not in (str, bool, int):
        raise ValidationError('Unsupported value type')

def fresh_project(name, family):
    if not isinstance(name,str) or not LABEL.fullmatch(name): raise ValidationError('Invalid project name')
    if family not in ('generic','transmon','fluxonium','resonator','amplifier','multi_qubit'):
        raise ValidationError('Unsupported project family')
    model={'schema':PROJECT_SCHEMA,'name':name,'family':family,
      'intent':{'targets':[],'notes':''},
      'schematic':{'nodes':[],'elements':[],'ports':[]},
      'process':{'source':'unverified','stack':[],'rules':{}},
      'layout':{'engine':'quantum_metal','chip':{'width_mm':5,'height_mm':5,'thickness_um':500},'components':[]},
      'studies':[], 'notes':''}
    if family in ('transmon','multi_qubit'):
        model['layout']['components']=[{'kind':'TransmonPocket','name':'Q1','x_mm':0,'y_mm':0}]
    return model

def validate_project(model):
    if not isinstance(model,dict) or set(model) != {'schema','name','family','intent','schematic','process','layout','studies','notes'}:
        raise ValidationError('Project fields/schema mismatch')
    if model['schema']!=PROJECT_SCHEMA: raise ValidationError('Unknown project schema')
    if not isinstance(model['name'],str) or not LABEL.fullmatch(model['name']): raise ValidationError('Invalid project name')
    if model['family'] not in ('generic','transmon','fluxonium','resonator','amplifier','multi_qubit'): raise ValidationError('Invalid circuit family')
    if any(not isinstance(model[k],dict) for k in ('intent','schematic','process','layout')) or not isinstance(model['studies'],list):
        raise ValidationError('Invalid project sections')
    if not isinstance(model['notes'],str) or len(model['notes'])>10000: raise ValidationError('Invalid notes')
    for key in ('nodes','elements','ports'):
        if not isinstance(model['schematic'].get(key),list): raise ValidationError('Schematic requires '+key)
    if not isinstance(model['intent'].get('targets'),list): raise ValidationError('Targets must be a list')
    if model['layout'].get('engine')!='quantum_metal': raise ValidationError('Quantum Metal is mandatory for layout')
    if not isinstance(model['layout'].get('components'),list) or not isinstance(model['layout'].get('chip'),dict):
        raise ValidationError('Invalid layout specification')
    if len(model['studies'])>30: raise ValidationError('Maximum 30 studies per revision')
    study_ids=set()
    for study in model['studies']:
        if not isinstance(study,dict) or set(study)!={'id','engine','kind','inputs'} or not IDENT.fullmatch(str(study['id'])):
            raise ValidationError('Study requires id, engine, kind, inputs')
        if study['id'] in study_ids or study['engine'] not in ENGINES or not isinstance(study['inputs'],dict):
            raise ValidationError('Duplicate study ID or unsupported engine')
        study_ids.add(study['id'])
    _numbers_safe(model)
    if len(json.dumps(model,allow_nan=False).encode())>256*1024: raise ValidationError('Project exceeds 256 KiB')
    return model

def stage_status(model, successful_engine_ids=()):
    """Draft presence is not scientific gate qualification."""
    success=set(successful_engine_ids)
    data={'intent':bool(model['intent'].get('targets')),
        'schematic':bool(model['schematic'].get('elements')),
        'layout':bool(model['layout'].get('components')),
        'em':any(s['engine']=='sqdmetal_palace' for s in model['studies']),
        'quantum':any(s['engine'] in ('scqubits','josephson_circuits') for s in model['studies']),
        'results':bool(success), 'fabrication': 'quantum_metal' in success}
    return {k:('draft_saved' if v else 'not_started') for k,v in data.items()}
