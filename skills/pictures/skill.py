"""Pictures: shows a Wikipedia picture of what the resident asks to see, so Mary can talk about it.

Only the few search words go out (nothing else the resident said), only to Wikipedia, and only free
pictures come back. A short blocklist turns away adult or gory asks before any search. Every network
problem becomes a kind line, never a crash. The page loads the picture from IMAGE_ROUTE.
"""
import html
import json
import re
import time

API = "https://en.wikipedia.org/w/api.php"
IMAGE_HOST = "https://upload.wikimedia.org/"
IMAGE_ROUTE = "/api/mary/skills/pictures/image/"
CREDIT_FIELDS = "Artist|LicenseShortName|Credit|UsageTerms"
QUERY_MAX, TITLE_MAX, SUMMARY_MAX, ARTIST_MAX, LICENSE_MAX, VIEW_MAX = 100, 100, 400, 80, 30, 600
IMAGE_BYTES_MAX, JSON_BYTES_MAX, IMAGE_WIDTH = 4_000_000, 1_000_000, 1600
TIME_BUDGET_S = 7.0   # the core stops a slow skill at 8 s
FETCH_TIMEOUT_S = 4.0
MIN_FETCH_S = 0.8     # with less time than this left, don't start another fetch
TRIES = 3             # pictures to try before giving up (one may be too big)
SHOWN_MAX = 50

SAY_ASK = "What would you like to see?"
SAY_BLOCKED = ("That's not something I'll show, but I'd love to find you something else. "
               "How about a bird or a pretty place?")
SAY_NOT_FOUND = "I couldn't find a picture of that. Want to try something else?"
SAY_OFFLINE = "I need the internet to find pictures."
SAY_FAILED = "I couldn't get a picture just now. Want to try again?"
SAY_SLOW = "That's taking too long. Want me to try again?"
SAY_NO_PICTURE = "There's no picture up yet. What would you like to see?"
SAY_CLOSED = "Okay, I put the picture away."
CREDIT_FALLBACK = "Photo from Wikipedia"

# Clearly adult or gory asks. Whole words only: guns, hunting, deer, fishing, church and Bible
# topics are welcome, and "dead", "kill", "hunt" or "breast" alone are never blocked.
_BLOCKED = re.compile(r"\b(?:" + "|".join([
    r"porn\w*", r"nude[sd]?", r"nudity", r"naked(?![\s-]*mole)", r"sex", r"sexy", r"sexual\w*", r"xxx",
    r"erotic\w*", r"fetish\w*", r"genital\w*", r"penis\w*", r"vagina\w*", r"vulva", r"nipples?", r"topless",
    r"hentai", r"orgy", r"orgies", r"bdsm", r"masturbat\w*", r"intercourse", r"boobs", r"stripper\w*",
    r"strip[\s-]*clubs?", r"onlyfans", r"gore", r"gory", r"corpses?", r"cadavers?", r"dead[\s-]+bod(?:y|ies)",
    r"behead\w*", r"decapitat\w*", r"dismember\w*", r"mutilat\w*", r"autops(?:y|ies)", r"tortur\w*",
    r"suicid\w*", r"self[\s-]*harm\w*", r"lynching", r"lynchings", r"lynched", r"massacres?",
]) + r")\b", re.IGNORECASE)
# File names that are rarely photos: icons, logos, maps, flags, symbols, diagrams, signatures, arms.
_JUNK = re.compile(r"(?<![a-z])(?:icons?|logos?|maps?|flags?|symbols?|diagrams?|signatures?|"
                   r"coat[\s-]*of[\s-]*arms|locator|emblems?|seal[\s-]+of|charts?|graphs?)(?![a-z])", re.IGNORECASE)
_TAG = re.compile(r"<[^>]*>")
_PIC = re.compile(r"pic-\d+\.(?:jpg|png|gif|webp)")


class _NetError(Exception):
    """A fetch that failed; reason is ctx.fetch's short code (offline, too_big, http_error, ...) or "slow"."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ---------- pure helpers (tests call these) ----------

def clean_query(what):
    """The search words only: single spaces, at most 100 characters."""
    return " ".join(str(what or "").split())[:QUERY_MAX].strip()


def blocked(text):
    """True when the words ask for something adult or gory."""
    return bool(_BLOCKED.search(str(text or "").replace("_", " ")))


def plain_text(value, limit):
    """Wikipedia HTML as short plain text: no tags, no entities, single spaces."""
    text = _TAG.sub(" ", html.unescape(_TAG.sub(" ", str(value or ""))))
    return _cap(" ".join(text.split()), limit)


def credit_text(meta, repository="shared"):
    """'Photo: <artist> · <license> · Wikimedia Commons' from imageinfo extmetadata."""
    meta = meta if isinstance(meta, dict) else {}

    def field(key, limit):
        item = meta.get(key)
        return plain_text(item.get("value") if isinstance(item, dict) else "", limit)

    artist = field("Artist", ARTIST_MAX)
    license_ = field("LicenseShortName", LICENSE_MAX) or field("UsageTerms", LICENSE_MAX)
    where = "Wikimedia Commons" if repository == "shared" else "Wikipedia"
    parts = [f"Photo: {artist}" if artist else f"Photo from {where}"] + ([license_] if license_ else [])
    return " · ".join(parts + ([where] if artist else []))


def sniff_image(data):
    """jpg, png, gif or webp from the file's first bytes; None for anything else."""
    head = bytes(data[:12]) if isinstance(data, (bytes, bytearray)) else b""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def pick_pages(data):
    """Search results in rank order with a free lead picture: no disambiguation pages, nothing blocked."""
    out = []
    for page in sorted(_pages(data), key=lambda p: p["index"] if isinstance(p.get("index"), int) else 99):
        thumb = page.get("thumbnail") if isinstance(page.get("thumbnail"), dict) else {}
        title, image = str(page.get("title") or ""), _norm(page.get("pageimage"))
        props = page.get("pageprops") if isinstance(page.get("pageprops"), dict) else {}
        if not title or not image or not thumb.get("source") or "disambiguation" in props:
            continue
        if blocked(title) or blocked(image):
            continue
        out.append({"page": title, "title": _cap(title, TITLE_MAX), "image": image, "src": str(thumb["source"]),
                    "summary": plain_text(page.get("extract"), SUMMARY_MAX)})
    return out


def pick_files(names, shown=()):
    """Photo file names (no 'File:') worth showing next: jpg or png, not an icon, map or logo, not shown yet."""
    seen = {_norm(n) for n in shown}
    out = []
    for raw in names:
        name = _norm(raw)
        if (name.lower().endswith((".jpg", ".jpeg", ".png")) and name not in seen
                and not _JUNK.search(name) and not blocked(name)):
            seen.add(name)
            out.append(name)
    return out


def _norm(name):
    """A file name as the API writes it in titles: spaces, no 'File:' in front."""
    name = str(name or "").replace("_", " ").strip()
    return name[5:].strip() if name.lower().startswith("file:") else name


def _cap(text, limit):
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _list(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _pages(data):
    query = data.get("query") if isinstance(data, dict) else None
    return _list(query.get("pages") if isinstance(query, dict) else None)


def _info(page):
    """A file page's first imageinfo entry, or {}."""
    items = _list(page.get("imageinfo"))
    return items[0] if items else {}


# ---------- network (only through ctx.fetch, always against the deadline) ----------

def _fetch(ctx, url, deadline, params, max_bytes):
    left = deadline - time.monotonic()
    if left < MIN_FETCH_S:
        raise _NetError("slow")
    try:
        got = ctx.fetch(url, params=params, max_bytes=max_bytes, timeout=min(FETCH_TIMEOUT_S, left))
    except Exception as err:  # noqa: BLE001 (every fetch problem is a kind line, never a crash)
        raise _NetError(str(getattr(err, "reason", "failed"))) from None
    if not isinstance(got, dict) or got.get("status") != 200 or not isinstance(got.get("body"), (bytes, bytearray)):
        raise _NetError("http_error")
    return got


def _api(ctx, params, deadline):
    """One Wikipedia API call, as parsed JSON."""
    got = _fetch(ctx, API, deadline, dict({"format": "json", "formatversion": 2}, **params), JSON_BYTES_MAX)
    try:
        return json.loads(bytes(got["body"]).decode("utf-8"))
    except ValueError:
        raise _NetError("failed") from None


def _search_params(query):
    return {"action": "query", "generator": "search", "gsrsearch": query, "gsrnamespace": 0, "gsrlimit": 5,
            "prop": "pageimages|extracts|pageprops", "piprop": "thumbnail|name", "pithumbsize": IMAGE_WIDTH,
            "pilicense": "free", "exintro": 1, "explaintext": 1, "exsentences": 2, "redirects": 1}


def _info_params(names, width=None):
    params = {"action": "query", "titles": "|".join("File:" + n for n in names), "prop": "imageinfo",
              "iiprop": "extmetadata|url", "iiextmetadatafilter": CREDIT_FIELDS}
    if width:
        params["iiurlwidth"] = width
    return params


def _image(ctx, src, deadline):
    """The picture's (bytes, type), or None when it's too big, gone, not on Wikimedia or not a real picture."""
    src = str(src or "")
    src = "https:" + src if src.startswith("//") else src
    if not src.startswith(IMAGE_HOST):
        return None
    try:
        body = _fetch(ctx, src, deadline, None, IMAGE_BYTES_MAX)["body"]
    except _NetError as err:
        if err.reason in ("too_big", "http_error"):
            return None
        raise
    ext = sniff_image(body)
    return (bytes(body), ext) if ext else None


def _credit(ctx, name, deadline):
    pages = _pages(_api(ctx, _info_params([name]), deadline))
    page = pages[0] if pages else {}
    return credit_text(_info(page).get("extmetadata"), page.get("imagerepository", "shared"))


def _say_for(reason):
    return {"offline": SAY_OFFLINE, "slow": SAY_SLOW}.get(reason, SAY_FAILED)


# ---------- the picture on screen ----------

def _store(ctx, data, ext):
    """Saves the picture as pic-<n>.<ext> and deletes the older ones."""
    count = int(ctx.state.get("count") or 0) + 1
    name = f"pic-{count}.{ext}"
    ctx.files.write_bytes(name, data)
    ctx.state["count"] = count
    _clear_files(ctx, keep=name)
    return name


def _clear_files(ctx, keep=None):
    for name in ctx.files.list():
        if _PIC.fullmatch(name) and name != keep:
            ctx.files.delete(name)


def _show(ctx):
    s = ctx.state
    ctx.effect("show_screen", {})
    ctx.effect("picture", {"src": IMAGE_ROUTE + s["file"], "title": s["title"], "credit": s["credit"]})
    return {"title": s["title"], "summary": s["summary"], "credit": s["credit"], "say": f"Here's {s['title']}."}


# ---------- actions ----------

def show_picture(ctx, what=""):
    """Finds the Wikipedia article for their words and shows its lead picture, with a credit line."""
    query = clean_query(what)
    if not query:
        return {"say": SAY_ASK}
    if blocked(query):
        return {"blocked": True, "say": SAY_BLOCKED}
    deadline = time.monotonic() + TIME_BUDGET_S
    try:
        for page in pick_pages(_api(ctx, _search_params(query), deadline))[:TRIES]:
            got = _image(ctx, page["src"], deadline)
            if got:
                break
        else:
            return {"found": False, "say": SAY_NOT_FOUND}
    except _NetError as err:
        return {"say": _say_for(err.reason)}
    try:
        credit = _credit(ctx, page["image"], deadline)
    except _NetError:
        credit = CREDIT_FALLBACK
    file = _store(ctx, *got)
    ctx.state.update(title=page["title"], summary=page["summary"], credit=credit, file=file, query=query,
                     page=page["page"], shown=[page["image"]])
    return _show(ctx)


def next_picture(ctx):
    """Another free photo (from Wikimedia Commons) from the same article, one not shown yet."""
    page, title = ctx.state.get("page"), ctx.state.get("title")
    if not page:
        return {"say": SAY_NO_PICTURE}
    shown = ctx.state.setdefault("shown", [])
    deadline = time.monotonic() + TIME_BUDGET_S
    try:
        listed = _api(ctx, {"action": "query", "titles": page, "prop": "images", "imlimit": 50, "redirects": 1},
                      deadline)
        fresh = pick_files([i.get("title") for p in _pages(listed) for i in _list(p.get("images"))], shown)[:TRIES]
        if not fresh:
            line = "the only picture" if len(shown) <= 1 else "all the pictures"
            return {"title": title, "say": f"That's {line} I have of {title}."}
        infos = {_norm(p.get("title")): p for p in _pages(_api(ctx, _info_params(fresh, IMAGE_WIDTH), deadline))}
        for name in fresh:
            p = infos.get(name, {})
            info = _info(p)
            got = (_image(ctx, info.get("thumburl") or info.get("url"), deadline)
                   if p.get("imagerepository") == "shared" else None)  # Commons only: every file there is free
            shown.append(name)
            del shown[:-SHOWN_MAX]
            if got:
                ctx.state.update(file=_store(ctx, *got), credit=credit_text(info.get("extmetadata"), "shared"))
                return _show(ctx)
    except _NetError as err:
        return {"say": _say_for(err.reason)}
    return {"title": title, "say": SAY_FAILED}


def close_picture(ctx):
    """Puts the picture away and goes back to Mary's face."""
    _clear_files(ctx)
    count = ctx.state.get("count", 0)
    ctx.state.clear()
    ctx.state["count"] = count  # file names keep counting up, so the page never shows an old picture
    ctx.effect("leave_screen", {})
    return {"closed": True, "say": SAY_CLOSED}


def on_event(ctx, event):
    """Taps on the screen: "next" for another picture, "close" to put it away."""
    kind = event.get("type") if isinstance(event, dict) else None
    if kind == "next":
        return next_picture(ctx)
    if kind == "close":
        return close_picture(ctx)
    return {"ignored": True}


def view(state):
    """What Mary sees: the picture's title, its two-sentence summary and the credit."""
    if not state.get("title"):
        return "No picture is up."
    parts = [f"A picture of {state['title']} is on the screen.", state.get("summary") or "",
             f"({state['credit']})" if state.get("credit") else ""]
    return _cap(" ".join(" ".join(parts).split()), VIEW_MAX - 1)
