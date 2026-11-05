"""Service; extracted from the tested dev78 HTTP service."""
from __future__ import annotations
from sqe_studio.jobs import Jobs
from sqe_studio.store import Store
import importlib.util
import os
import secrets
import threading
import time

class Service:
    def __init__(self,data):
        self.store=Store(data)
        self.jobs=Jobs(self.store)
        self.setup_file=self.store.root/'setup.token'
        if self.setup_file.is_symlink():raise ValueError('Unsafe first-run token file')
        if self.store.has_account():
            # In a crash between first account creation and token deletion,
            # never leave a reusable bootstrap credential on disk.
            self.setup_file.unlink(missing_ok=True)
        elif not self.setup_file.exists():
            try:
                fd=os.open(self.setup_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'w',encoding='ascii') as out:
                    out.write(secrets.token_urlsafe(32))
            except FileExistsError:raise ValueError('First-run setup token race') from None
        self._login_lock=threading.Lock()
        self.field_comparison_lock=threading.Lock()
        self._failures=[]
    def login_allowed(self):
        with self._login_lock:
            now=time.monotonic()
            self._failures=[t for t in self._failures if now-t<300]
            return len(self._failures)<12
    def login_result(self,successful):
        with self._login_lock:
            if successful:self._failures.clear()
            else:self._failures.append(time.monotonic())
    def engines(self):
        def available(x):
            try:return importlib.util.find_spec(x) is not None
            except (ImportError,ValueError,AttributeError):return False
        return [
          {'id':'quantum_metal','name':'Quantum Metal','available':available('qiskit_metal'),'capability':'Native QDesign + GDS renderer','mode':'native'},
          {'id':'sqdmetal_palace','name':'SQDMetal / Gmsh / Palace','available':available('SQDMetal') and available('gmsh') and available('qiskit_metal'), 'capability':'3D EM workflow · reviewed physical setup required','mode':'native_conditional'},
          {'id':'scqubits','name':'scqubits','available':available('scqubits'),'capability':'Quantum spectra','mode':'native'},
          {'id':'josephson_circuits','name':'JosephsonCircuits.jl','available':False,'capability':'Julia circuit/RF','mode':'blocked_pending_reviewed_adapter'},
        ]
