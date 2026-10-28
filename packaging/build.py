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

VERSION = "0.2.0"
NAME = "Care Incident Log"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORK, APP_DIST, OUT = HERE / "build", HERE / "dist", ROOT / "dist"
ICON = HERE / "icon.ico"
MODEL = "models/faster-whisper-base.en"  # speech.py finds it next to itself (_internal\ in the app)
# speech and reports are imported lazily inside routes; name them so they're never missed.
SPEECH_ARGS = ["--hidden-import", "speech", "--hidden-import", "reports",
               "--collect-data", "faster_whisper",  # silero VAD .onnx
               "--collect-binaries", "ctranslate2", "--collect-binaries", "onnxruntime"]
ISCC_PATHS = [Path(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
              Path(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
              Path(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe")]


def run(*cmd):
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)


def ensure_model():
    """models/ is not in git: fetch the voice model (about 140 MB) on a fresh copy."""
    if (ROOT / MODEL / "model.bin").exists():
        return
    print("Downloading the voice model (base.en) once...")
    from faster_whisper.utils import download_model
    download_model("base.en", output_dir=str(ROOT / MODEL))


def main():
    if not ICON.exists():
        run(sys.executable, HERE / "make_icon.py")
    ensure_model()
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
        "--windowed", "--name", NAME, "--icon", ICON,
        "--add-data", f"{ROOT / 'web'}{os.pathsep}web",
        "--add-data", f"{ROOT / 'mary' / 'instructions.md'}{os.pathsep}mary",  # Mary's instructions (mary.py reads ROOT/mary/)
        "--add-data", f"{ROOT / MODEL}{os.pathsep}{MODEL}", *SPEECH_ARGS,
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
