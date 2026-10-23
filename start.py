"""One entry point for setup, local review, tests, and the assignment demo.

Uses only Python's standard library so it can create its own environment before
any model libraries are installed. All subprocesses use argument lists (no shell).
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENVIRONMENT = ROOT / ".venv"
SETTINGS = ROOT / "local-settings.json"


def environment_python():
    """Never depend on shell activation or whichever pip happens to be on PATH."""
    return ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(arguments, environment=None):
    """Fail at the first unsuccessful command; do not launch half-installed code."""
    subprocess.run(
        [str(value) for value in arguments], cwd=ROOT, env=environment, check=True
    )


def saved_device():
    if not SETTINGS.exists():
        return "cpu"
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    if settings.get("device") not in ("cpu", "cuda"):
        raise ValueError("Invalid local-settings.json device; use cpu or cuda.")
    return settings["device"]


def runtime_environment(python):
    """Set Linux loader paths BEFORE starting the process that imports Whisper.

    Changing LD_LIBRARY_PATH inside an already-running inference process is too
    late. Windows DLL registration is handled separately by prototype/gpu.py.
    Preserve the caller's environment, including an existing library search path.
    """
    environment = os.environ.copy()
    if sys.platform.startswith("linux"):
        result = subprocess.check_output(
            [
                str(python),
                "-c",
                "import json,site; print(json.dumps(site.getsitepackages()))",
            ],
            text=True,
            cwd=ROOT,
        )
        directories = [
            str(Path(base) / "nvidia" / component / "lib")
            for base in json.loads(result)
            for component in ("cudnn", "cublas", "cuda_runtime")
            if (Path(base) / "nvidia" / component / "lib").is_dir()
        ]
        existing = environment.get("LD_LIBRARY_PATH")
        if existing:
            directories.append(existing)
        if directories:
            environment["LD_LIBRARY_PATH"] = os.pathsep.join(directories)
    return environment


def check_media_tools():
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise RuntimeError(
            "Missing " + ", ".join(missing) + ".\n"
            "Ubuntu/Debian: sudo apt install ffmpeg python3-venv\n"
            "Windows: winget install --id Gyan.FFmpeg -e, then reopen the terminal.\n"
            "Other Linux distributions: install FFmpeg with your package manager."
        )


def setup(device):
    """Download dependencies/models only during an explicitly selected setup."""
    if not (3, 10) <= sys.version_info[:2] <= (3, 12):
        raise RuntimeError(
            "Use Python 3.10-3.12 (3.12 recommended) for these pinned packages."
        )
    if platform.system() not in (
        "Windows",
        "Linux",
    ) or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError(
            "This processor setup targets Windows/Linux x86-64. The Pi recorder is a separate role."
        )
    check_media_tools()
    python = environment_python()
    if not python.exists():
        print(
            "Creating .venv; existing recordings and model files are preserved.",
            flush=True,
        )
        venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)
    # The answer model stays on CPU even when Whisper uses CUDA. This avoids
    # installing a second GPU framework and consuming additional GPU memory.
    run([python, "-m", "pip", "install", "-r", ROOT / "requirements.txt"])
    run(
        [
            python,
            "-m",
            "pip",
            "install",
            "torch==2.8.0",
            "--index-url",
            "https://download.pytorch.org/whl/cpu",
        ]
    )
    run([python, "-m", "pip", "install", "-r", ROOT / "requirements-rag.txt"])
    if device == "cuda":
        run([python, "-m", "pip", "install", "-r", ROOT / "requirements-cuda.txt"])
    run([python, "-m", "pip", "check"])
    run([python, "securenote.py", "download-model", "--model", "base.en"])
    run([python, "ask.py", "download-model"])
    environment = runtime_environment(python)
    run([python, "securenote.py", "doctor"], environment)
    # Imports alone do not prove that weights can be loaded or inference works.
    run(
        [
            python,
            "-c",
            "from prototype.rag import load_answer_model,generate_answer; t,m=load_answer_model('models/flan-t5-small'); print('Answer model smoke test:',generate_answer('Context: Alice sends the budget Friday. Question: When does Alice send the budget? Answer:',t,m))",
        ],
        environment,
    )
    if device == "cuda":
        run(
            [
                python,
                "-c",
                "from prototype.gpu import check_cuda; check_cuda('models/base.en')",
            ],
            environment,
        )
    else:
        run(
            [
                python,
                "-c",
                "from faster_whisper import WhisperModel; import numpy as np; m=WhisperModel('models/base.en',device='cpu',compute_type='int8',local_files_only=True); s,_=m.transcribe(np.zeros(16000,dtype=np.float32),language='en',vad_filter=False); list(s); print('CPU Whisper inference passed')",
            ],
            environment,
        )
    # Save the selection only after installation and model checks succeed.
    from prototype.transfer import atomic_json

    atomic_json(SETTINGS, {"device": device})
    print(
        "Setup complete. Run this script again and choose Start workspace.", flush=True
    )


def menu():
    print(
        "\nSecureNote - local recording workspace\n"
        "  1. Set up and start (CPU; simplest option)\n"
        "  2. Set up and start (NVIDIA GPU transcription)\n"
        "  3. Start workspace (saved setting; no downloads)\n"
        "  4. Run the three-example assignment demo (CPU)\n"
        "  5. Run tests\n"
        "  6. Exit"
    )
    choices = {
        "1": ("setup", "cpu"),
        "2": ("setup", "cuda"),
        "3": ("run", None),
        "4": ("demo", None),
        "5": ("test", None),
        "6": ("exit", None),
    }
    while True:
        choice = input("Choose [3]: ").strip() or "3"
        if choice in choices:
            return choices[choice]
        print("Enter a number from 1 to 6.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=["setup", "run", "demo", "test"])
    parser.add_argument("--device", choices=["cpu", "cuda"])
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Setup only; do not start the workspace",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print private URL without opening a browser",
    )
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    action, device = args.action, args.device
    if action is None:
        if not sys.stdin.isatty():
            parser.error(
                "Specify setup, run, demo or test in a noninteractive terminal."
            )
        action, selected_device = menu()
        device = device or selected_device
    if action == "exit":
        return
    device = device or saved_device()
    if action == "setup":
        setup(device)
        if args.no_launch:
            return
        action = "run"
    python = environment_python()
    if not python.exists():
        raise RuntimeError(
            "Environment missing. Run: python start.py setup --device cpu"
        )
    if action != "test":
        check_media_tools()
    environment = runtime_environment(python)
    if action == "run":
        command = [python, "review.py", "--device", device, "--port", str(args.port)]
        if args.no_browser:
            command.append("--no-browser")
        run(command, environment)
    elif action == "demo":
        # Unique folders preserve earlier evidence. The demo deliberately uses
        # CPU so that measurements and behavior are comparable across machines.
        folder = "demo-assignment-" + str(time.time_ns())
        run([python, "tools/run_assignment_demo.py", "--output", folder], environment)
    elif action == "test":
        run([python, "-m", "unittest", "discover", "-s", "tests", "-v"], environment)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print("\nSecureNote could not finish:", error, file=sys.stderr)
        print(
            "See README.md for setup and troubleshooting. Existing recordings are preserved.",
            file=sys.stderr,
        )
        sys.exit(1)
