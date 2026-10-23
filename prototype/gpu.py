"""Local CUDA DLL registration and isolated native-runtime smoke test."""
import os
import site
import subprocess
import sys
from pathlib import Path

_handles = []
_configured = False

def configure_dlls():
    global _configured
    if _configured or os.name != 'nt':
        return
    directories = []
    for base in site.getsitepackages():
        for component in ('cudnn', 'cublas', 'cuda_runtime'):
            directory = Path(base) / 'nvidia' / component / 'bin'
            if directory.is_dir():
                directories.append(str(directory))
                _handles.append(os.add_dll_directory(str(directory)))
    os.environ['PATH'] = os.pathsep.join(directories + [os.environ.get('PATH', '')])
    _configured = True

def check_cuda(model_directory):
    # Some missing native libraries abort Python: probe in a separate process.
    try:
        result = subprocess.run([sys.executable, '-m', 'prototype.gpu', str(Path(model_directory).resolve())],
            cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise SystemExit('CUDA check timed out. Start with --device cpu or check the NVIDIA driver.')
    if result.returncode:
        raise SystemExit('CUDA check failed before starting the workspace.\n' + result.stderr[-3000:] +
            '\nInstall requirements-cuda.txt into this venv and update your NVIDIA driver.\n'
            'CPU fallback: python review.py --device cpu')

if __name__ == '__main__':
    configure_dlls()
    os.environ['HF_HUB_OFFLINE'] = '1'
    from faster_whisper import WhisperModel
    import numpy as np
    model = WhisperModel(sys.argv[1], device='cuda', compute_type='float16', local_files_only=True)
    segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language='en', vad_filter=False, beam_size=1)
    list(segments)
    print('CUDA float16 inference passed')
