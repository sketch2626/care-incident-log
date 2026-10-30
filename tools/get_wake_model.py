"""Download the offline wake-word model (Vosk small English 0.15) into models/ (gitignored).

Official file only: alphacephei.com, the Vosk project's own model page. The zip goes to a .part file
first, is checked against the size and SHA-256 below, then unpacked. A model that is already unpacked
(am/final.mdl present) is left alone.  Run: python -I tools/get_wake_model.py  [target folder]
Stdlib only.
"""
import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

NAME = "vosk-model-small-en-us-0.15"
URL = f"https://alphacephei.com/vosk/models/{NAME}.zip"
SIZE = 41205931
SHA256 = "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"
CHUNK = 1 << 20


def fetch(dest):
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    with urllib.request.urlopen(URL, timeout=60) as resp, open(part, "wb") as out:
        while True:
            block = resp.read(CHUNK)
            if not block:
                break
            out.write(block)
            h.update(block)
    return part, h.hexdigest()


def unpack(zip_path, folder):
    """Unpack into a temporary folder beside the target, then move the model folder into place."""
    target = (folder / NAME).resolve()
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        tmp = Path(tmp).resolve()
        with zipfile.ZipFile(zip_path) as z:
            for member in z.namelist():  # refuse paths that would land outside the temp folder
                if not (tmp / member).resolve().is_relative_to(tmp):
                    raise ValueError(f"unsafe path in zip: {member}")
            z.extractall(tmp)
        src = tmp / NAME
        if not (src / "am" / "final.mdl").is_file():
            raise ValueError("the zip does not hold the expected model folder")
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(src), str(target))


def main(argv):
    folder = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "models"
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / NAME / "am" / "final.mdl"
    if marker.is_file():
        print(f"{NAME}: already here ({folder / NAME})")
        return 0
    zip_path = folder / f"{NAME}.zip"
    part, got = fetch(zip_path)
    have = part.stat().st_size
    if have != SIZE or got != SHA256:
        part.unlink(missing_ok=True)
        print(f"{NAME}: FAILED check (size {have}, sha256 {got})")
        return 1
    part.replace(zip_path)
    try:
        unpack(zip_path, folder)
    except Exception as e:
        print(f"{NAME}: FAILED to unpack ({e})")
        return 1
    finally:
        zip_path.unlink(missing_ok=True)
    print(f"{NAME}: downloaded, {have / 1e6:.1f} MB, sha256 {got}, unpacked into {folder / NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
