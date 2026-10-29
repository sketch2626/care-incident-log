"""Refused: its handler crashes."""


def spin(ctx):
    return {"turns": 1 // 0}
