from dataclasses import dataclass
import os
from pathlib import Path


@dataclass
class Settings:
    root: Path
    origin: str = 'http://127.0.0.1:8000'
    development: bool = True
    max_jobs: int = 2
    total_cpus: int = 4
    total_memory_gb: int = 8
    session_hours: int = 12
    max_upload_mb: int = 32
    max_capsule_mb: int = 512
    max_expanded_mb: int = 8192
    palace: str = 'palace'

    @classmethod
    def from_env(cls):
        origin = os.getenv('SQE_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')
        dev = os.getenv('SQE_DEVELOPMENT', '0') == '1'
        if not dev and not origin.startswith('https://'):
            raise ValueError('Set SQE_ORIGIN to your HTTPS URL, or SQE_DEVELOPMENT=1 for loopback development')
        return cls(Path(os.getenv('SQE_DATA', './studio-data')).resolve(), origin, dev,
                   int(os.getenv('SQE_MAX_JOBS', '2')), int(os.getenv('SQE_TOTAL_CPUS', '4')),
                   int(os.getenv('SQE_MEMORY_GB', '8')), palace=os.getenv('SQE_PALACE', 'palace'),
                   max_capsule_mb=int(os.getenv('SQE_MAX_CAPSULE_MB', '512')),
                   max_expanded_mb=int(os.getenv('SQE_MAX_EXPANDED_MB', '8192')))

    def validate(self):
        if min(self.max_jobs, self.total_cpus, self.total_memory_gb,
               self.max_capsule_mb, self.max_expanded_mb) < 1:
            raise ValueError('Worker capacity must be positive')
        self.root = Path(self.root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
