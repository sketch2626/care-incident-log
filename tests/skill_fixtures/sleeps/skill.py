"""Refused: its handler takes longer than the time limit."""
import time


def spin(ctx):
    time.sleep(0.6)
    return {"ok": True}
