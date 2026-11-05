"""Allowlisted route matching; authentication/CSRF live in handler.py."""
from dataclasses import dataclass
from urllib.parse import SplitResult
from .common import ApiError,HEX_ID
from . import comparisons, design, extraction, fields, projects, public, quantum, results, runs, session, sweeps

@dataclass(frozen=True)
class Request:
    method: str
    parsed: SplitResult
    user: dict | None = None
    @property
    def path(self):return self.parsed.path
    @property
    def parts(self):return self.path.strip('/').split('/')
    @property
    def uid(self):return self.user['user_id']
    @property
    def pid(self):return self.parts[2]


def public_route(handler,request):
    method,path=request.method,request.path
    if method == 'GET' and path in ('/', '/index.html', '/app.js', '/style.css'):
        public.assets(handler,request)
        return True
    if method == 'GET' and path == '/api/status':
        public.status(handler,request)
        return True
    if method == 'POST' and path == '/api/setup':
        public.setup(handler,request)
        return True
    if method == 'POST' and path == '/api/login':
        public.login(handler,request)
        return True
    return False


def authenticated_route(handler,request):
    method,path,parts=request.method,request.path,request.parts
    if method == 'GET' and path == '/api/me':
        session.me(handler,request)
        return True
    if method == 'POST' and path == '/api/logout':
        session.logout(handler,request)
        return True
    if method == 'POST' and path == '/api/password':
        session.password(handler,request)
        return True
    if method == 'GET' and path == '/api/engines':
        design.engines(handler,request)
        return True
    if method == 'GET' and path == '/api/workflow':
        design.workflow(handler,request)
        return True
    if method == 'GET' and path == '/api/projects':
        projects.list_projects(handler,request)
        return True
    if method == 'GET' and path == '/api/design/templates':
        design.templates(handler,request)
        return True
    if method == 'GET' and path == '/api/design/capabilities':
        design.capabilities(handler,request)
        return True
    if method == 'GET' and path == '/api/design/use-cases':
        design.use_cases(handler,request)
        return True
    if method == 'GET' and path == '/api/design/scientific-references':
        design.scientific_references(handler,request)
        return True
    if method == 'GET' and path == '/api/design/components':
        design.components(handler,request)
        return True
    if method == 'POST' and path == '/api/design/check':
        design.check(handler,request)
        return True
    if method == 'POST' and path == '/api/projects':
        projects.create(handler,request)
        return True
    if len(parts)>=3 and parts[:2]==['api','projects']:
        pid=request.pid
        if not HEX_ID.fullmatch(pid):raise ApiError('Project not found',404)
        if len(parts) == 3 and method == 'GET':
            projects.read(handler,request)
            return True
        if len(parts) == 4 and parts[3] == 'revisions' and (method == 'GET'):
            projects.revisions(handler,request)
            return True
        if len(parts) == 5 and parts[3] == 'revisions' and (method == 'GET'):
            projects.revision(handler,request)
            return True
        if len(parts) == 4 and parts[3] == 'independent-transmon' and (method == 'POST'):
            quantum.declare_independent(handler,request)
            return True
        if len(parts) == 5 and parts[3] == 'independent-transmon' and (parts[4] in ('preflight', 'execute')) and (method == 'POST'):
            quantum.independent_execution(handler,request)
            return True
        if len(parts) == 6 and parts[3] == 'runs' and (parts[5] == 'extraction') and (method == 'POST'):
            extraction.extract(handler,request)
            return True
        if len(parts) == 4 and parts[3] == 'commit' and (method == 'POST'):
            projects.commit(handler,request)
            return True
        if len(parts) == 4 and parts[3] == 'runs' and (method == 'GET'):
            runs.list_runs(handler,request)
            return True
        if len(parts) == 4 and parts[3] == 'compare' and (method == 'GET'):
            comparisons.compare(handler,request)
            return True
        if len(parts) == 4 and parts[3] == 'runs' and (method == 'POST'):
            runs.create(handler,request)
            return True
        if len(parts) == 4 and parts[3] == 'sweeps' and (method == 'POST'):
            sweeps.create(handler,request)
            return True
        if len(parts) == 6 and parts[3] == 'runs' and (parts[5] == 'sweep') and (method == 'GET'):
            sweeps.inspect(handler,request)
            return True
        if len(parts) == 4 and parts[3] == 'compare-fields' and (method == 'POST'):
            fields.compare(handler,request)
            return True
        if len(parts) == 6 and parts[3] == 'runs' and (parts[5] == 'upstream-field-probe') and (method == 'POST'):
            fields.probe(handler,request)
            return True
        if len(parts) == 6 and parts[3] == 'runs' and (parts[5] in ('result', 'download')) and (method == 'GET'):
            results.inspect(handler,request)
            return True
    return False
