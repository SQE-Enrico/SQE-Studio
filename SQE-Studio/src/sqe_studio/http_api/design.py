"""Design; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from .common import ApiError
from sqe_studio.adapters.base import EngineBlocked
from sqe_studio.adapters.quantum_metal_adapter import validate_recipe
from sqe_studio.adapters.sqdmetal_palace_adapter import preflight as em_preflight
from sqe_studio.contracts import ENGINES
from sqe_studio.contracts import STEPS
from sqe_studio.contracts import validate_project
from sqe_studio.design_library import component_catalog
from sqe_studio.design_library import list_templates
from sqe_studio.design_library import use_case_catalog
from sqe_studio.eda.capabilities import list_capabilities
from sqe_studio.eda.scientific_references import list_reference_cases

def engines(self,request):
    return self.send_json({'engines':self.app.engines()})


def workflow(self,request):
    return self.send_json({'stages':STEPS,'engines':ENGINES})


def templates(self,request):
    return self.send_json({'templates':list_templates()})


def capabilities(self,request):
    return self.send_json({'schema':'sqe.eda-capability-map.v1',
                           'edges':list_capabilities()})


def use_cases(self,request):
    return self.send_json({'schema':'sqe.design-cases.v1','cases':use_case_catalog()})


def scientific_references(self,request):
    return self.send_json({'schema':'sqe.scientific-reference-catalog.m8.v1',
                           'cases':list_reference_cases()})


def components(self,request):
    return self.send_json(component_catalog())


def check(self,request):
    obj=self.json_body()
    if set(obj) != {'model'}:raise ApiError('Check requires a project model',422)
    model=validate_project(obj['model'])
    result={'schema':'sqe.design-check.v1','layout':{'ready':False},
            'em':[],'scientific_status':'not_qualified','fabrication_status':'HOLD'}
    try:
        validate_recipe(model['layout'])
        result['layout']={'ready':True,'message':'Reviewed recipe syntax; native geometry not yet built'}
    except (ValueError,TypeError,EngineBlocked) as exc:
        result['layout']={'ready':False,'message':str(exc)[:300]}
    for study in model['studies']:
        if study['engine'] != 'sqdmetal_palace':continue
        try:
            if not result['layout']['ready']:
                raise ValueError('Native layout recipe must pass its own validation first')
            em_preflight(study, model)
            check={'study_id':study['id'],'ready':True,
                   'message':'Physical mapping schema accepted; no native mesh, solver or scientific validation performed'}
        except (ValueError,TypeError,EngineBlocked) as exc:
            check={'study_id':study['id'],'ready':False,'message':str(exc)[:300]}
        result['em'].append(check)
    return self.send_json(result)

