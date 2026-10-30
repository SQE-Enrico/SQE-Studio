"""Bounded display-only extraction of already verified native Palace output.

Never infers mode identity, Hamiltonian, loss or convergence. Call only AFTER
verify_manifest for the same saved revision and declared file contents.
"""
from __future__ import annotations
import csv
import math
from pathlib import Path
from ..orchestration.artifacts import safe_file

class NativeDisplayError(ValueError):
    pass

def palace_eigenmodes(folder: Path, manifest: dict):
    declared = {item['name'] for item in manifest.get('artifacts', [])}
    if manifest.get('engine') != 'sqdmetal_palace' or manifest.get('kind') != 'eigenmode' or 'sqe_em/outputFiles/eig.csv' not in declared:
        return None
    path = safe_file(folder, 'sqe_em/outputFiles/eig.csv')
    if path.stat().st_size > 2_000_000:
        raise NativeDisplayError('Native eigenmode table is oversized')
    with path.open(newline='',encoding='utf-8-sig') as f:
        rows = csv.reader(f)
        head = next(rows, [])
        if len(head)<2 or 'ghz' not in head[1].lower() or 'f' not in head[1].lower():
            raise NativeDisplayError('Palace eigenfrequency column requires GHz units')
        result=[]
        for row in rows:
            if len(row) != len(head) or len(result) >= 32:
                raise NativeDisplayError('Malformed or oversized Palace native table')
            try:
                index=int(row[0]); freq=float(row[1])
            except (TypeError,ValueError,IndexError) as exc:
                raise NativeDisplayError('Invalid Palace native eigenfrequency') from exc
            if index != len(result)+1 or not math.isfinite(freq) or not 0 < freq <= 1000:
                raise NativeDisplayError('Nonfinite, reordered or nonpositive Palace eigenmode')
            result.append({'mode_index':index,'frequency_GHz':freq})
    if not result:
        raise NativeDisplayError('Palace eigenmode table empty')
    return {'source':'palace.native_eig.csv','units':'GHz','modes':result,
            'mode_matching':'not_established','convergence':'not_established',
            'scientific_qualification':'not_established'}
