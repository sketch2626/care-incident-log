"""Refused: it reaches the internet by itself instead of ctx.fetch."""
import urllib.request


def spin(ctx):
    return {"page": urllib.request.urlopen("https://example.org").status}
