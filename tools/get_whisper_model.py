"""Download the speech-to-text model (faster-whisper base.en) into models/ (gitignored).

Official files only: Systran's own Hugging Face page, pinned to one revision. Each file goes to a .part
file first, is checked against the size and SHA-256 below, then renamed. A file that is already there and
checks out is left alone.  Run: python -I tools/get_whisper_model.py  [target folder]
Stdlib only.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

NAME = "faster-whisper-base.en"
BASE = "https://huggingface.co/Systran/faster-whisper-base.en/resolve/3d3d5dee26484f91867d81cb899cfcf72b96be6c/"
# name -> (size in bytes, SHA-256)
FILES = {
    "config.json": (2227, "f3bc3821e9fc76a27bae538e11ae5b677dcdd352b4600429ce7951d398569aeb"),
    "model.bin": (145216508, "2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef"),
    "tokenizer.json": (2128466, "929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df"),
    "vocabulary.txt": (422309, "ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf"),
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
    folder = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "models" / NAME
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
