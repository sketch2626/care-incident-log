"""How full each second-account worker's conversation is (hub tool, not part of the app).

Reads the newest Claude Code transcript for each `.worktrees/<item>` folder and
prints the context size of its last real answer. The hub compacts or replaces a
worker before it passes about 250,000 tokens, because every answer re-reads it.
Usage: python tools/worker_context.py
"""
import glob
import json
import os
import time

BASE = os.path.expanduser("~/.claude/projects")


def last_context(path):
    size = 0
    for line in open(path, encoding="utf-8", errors="ignore"):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        msg = entry.get("message")
        if entry.get("type") != "assistant" or not isinstance(msg, dict):
            continue
        usage = msg.get("usage")
        if usage and msg.get("model") != "<synthetic>":  # skip usage-limit notices
            size = (usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0))
    return size


for folder in sorted(glob.glob(os.path.join(BASE, "*-worktrees-*"))):
    files = glob.glob(os.path.join(folder, "*.jsonl"))
    if not files:
        continue
    newest = max(files, key=os.path.getmtime)
    hours = (time.time() - os.path.getmtime(newest)) / 3600
    item = folder.split("-worktrees-", 1)[1]
    print(f"{item:10} {last_context(newest):>9,} tokens   last active {hours:.1f} h ago")
