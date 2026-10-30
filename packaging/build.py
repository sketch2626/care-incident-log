"""Builds the Care Incident Log Windows app. Use build.bat (it sets up the tools first).

Output in dist\\ at the project root:
  CareIncidentLog-Setup-<version>.exe     installer with Start-menu + desktop shortcuts
  CareIncidentLog-<version>-portable.zip  same app, unzip and double-click
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "0.3.0"
NAME = "Care Incident Log"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORK, APP_DIST, OUT = HERE / "build", HERE / "dist", ROOT / "dist"
ICON = HERE / "icon.ico"
WAKE_MODEL = "models/vosk-model-small-en-us-0.15"  # M6: offline "Hey Mary" listener (wakeword.py looks next to itself)
MODEL = "models/faster-whisper-base.en"  # speech.py finds it next to itself (_internal\ in the app)
KOKORO_MODEL = "models/kokoro"  # Mary's offline voice (voices.py finds it next to itself)
MODELS = [MODEL, KOKORO_MODEL, WAKE_MODEL]
MODEL_TOOLS = ["get_whisper_model.py", "get_voice_model.py", "get_wake_model.py"]  # each checks SHA-256 and skips what's there
# speech and reports are imported lazily inside routes; name them so they're never missed.
SPEECH_ARGS = ["--hidden-import", "speech", "--hidden-import", "reports",
               "--collect-data", "faster_whisper",  # silero VAD .onnx
               "--collect-binaries", "ctranslate2", "--collect-binaries", "onnxruntime",
               "--hidden-import", "wakeword", "--collect-binaries", "vosk", "--collect-data", "vosk"]  # M6
# Mary's own modules, named for the same reason, and what the Kokoro voice reads at run time.
MARY_ARGS = ["--hidden-import", "mary", "--hidden-import", "voices", "--hidden-import", "skills_core",
             "--hidden-import", "power", "--hidden-import", "kokoro_onnx", "--collect-data", "kokoro_onnx",
             "--collect-all", "espeakng_loader", "--collect-data", "phonemizer"]
ISCC_PATHS = [Path(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
              Path(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
              Path(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe")]


def run(*cmd):
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)


def ensure_models():
    """models/ is not in git: fetch what's missing on a fresh copy (about 260 MB). A failed check stops the build."""
    for tool in MODEL_TOOLS:
        run(sys.executable, "-I", ROOT / "tools" / tool)


def main():
    if not ICON.exists():
        run(sys.executable, HERE / "make_icon.py")
    ensure_models()
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
        "--windowed", "--name", NAME, "--icon", ICON,
        "--add-data", f"{ROOT / 'web'}{os.pathsep}web",
        "--add-data", f"{ROOT / 'mary' / 'instructions.md'}{os.pathsep}mary",  # Mary's instructions (mary.py reads ROOT/mary/)
        "--add-data", f"{ROOT / 'skills'}{os.pathsep}skills",  # Mary's skills (M13; server.py reads ROOT/skills/)
        *(arg for m in MODELS for arg in ("--add-data", f"{ROOT / m}{os.pathsep}{m}")),
        *SPEECH_ARGS, *MARY_ARGS,
        "--distpath", APP_DIST, "--workpath", WORK, "--specpath", WORK,
        ROOT / "desktop.py")
    OUT.mkdir(exist_ok=True)
    zip_base = OUT / f"CareIncidentLog-{VERSION}-portable"
    shutil.make_archive(str(zip_base), "zip", APP_DIST, NAME)
    print(f"Built {zip_base}.zip")

    iscc = next((p for p in ISCC_PATHS if p.exists()), None)
    if not iscc:
        print("Inno Setup 6 not found - skipped the installer (the zip still works).")
        return
    run(iscc, "/Q", f"/DAppVersion={VERSION}", f"/DSourceDir={APP_DIST / NAME}",
        f"/DOutputDir={OUT}", HERE / "installer.iss")
    print(f"Built {OUT / f'CareIncidentLog-Setup-{VERSION}.exe'}")


if __name__ == "__main__":
    main()
