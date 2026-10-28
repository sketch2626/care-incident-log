"""Download Mary's offline voice (Kokoro-82M, int8) into models/kokoro/ (gitignored).

Official files only: the kokoro-onnx project's own release page. Each file goes to a .part file first,
is checked against the size and SHA-256 below, then renamed. A file that is already there and checks out
is left alone.  Run: python -I tools/get_voice_model.py  [target folder]
Stdlib only.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
# name -> (size in bytes, SHA-256)
FILES = {
    "kokoro-v1.0.int8.onnx": (92361271, "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb"),
    "voices-v1.0.bin": (28214398, "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
}
CHUNK = 1 << 20


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def fetch(name, dest):
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    with urllib.request.urlopen(BASE + name, timeout=60) as resp, open(part, "wb") as out:
        while True:
            block = resp.read(CHUNK)
            if not block:
                break
            out.write(block)
            h.update(block)
    return part, h.hexdigest()


def main(argv):
    folder = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "models" / "kokoro"
    folder.mkdir(parents=True, exist_ok=True)
    bad = False
    for name, (size, want) in FILES.items():
        dest = folder / name
        if dest.is_file():
            got = sha256_of(dest)
            if dest.stat().st_size == size and got == want:
                print(f"{name}: already here, {size / 1e6:.1f} MB, sha256 {got}")
                continue
            print(f"{name}: present but does not match; downloading again")
        part, got = fetch(name, dest)
        have = part.stat().st_size
        if have != size or got != want:
            part.unlink(missing_ok=True)
            print(f"{name}: FAILED check (size {have}, sha256 {got})")
            bad = True
            continue
        part.replace(dest)
        print(f"{name}: downloaded, {have / 1e6:.1f} MB, sha256 {got}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
