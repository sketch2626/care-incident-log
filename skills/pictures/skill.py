"""Pictures: shows a Wikipedia picture of what the resident asks to see, so Mary can talk about it.

Only the few search words go out (nothing else the resident said), only to Wikipedia, and only free
pictures come back. A short blocklist turns away adult or gory asks before any search. Every network
problem becomes a kind line, never a crash. The page loads the picture from IMAGE_ROUTE.
M4a: the picture and the search words also go to Gemini, through the host (ctx.look), so she knows what is really shown.
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
TIME_BUDGET_S = 12.0  # M4a: the core stops a slow skill at 18 s; a look begun inside this budget takes up to 8 s
FETCH_TIMEOUT_S = 4.0
MIN_FETCH_S = 0.8     # with less time than this left, don't start another fetch
TRIES = 3             # pictures to try before giving up (one may be too big)
SHOWN_MAX = 50
LOOKS_MAX = 2         # M4a: looks per picture shown: the one that's shown, and one turned down
LOOK_MIN_S = 4.0      # M4a: with less time than this left, don't start a look
SEEN_MAX = 200
RANK_LAST = 4         # M4a: a drawing, a mascot, a logo: only when nothing else exists
MIMES = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
ASK_SEEN = ("Does this show a real {subject}, as a photo or painting of the actual thing, not a mascot, logo, costume, "
            "cartoon or diagram? Answer YES or NO on the first line, then describe what it shows in one plain sentence.")

SAY_ASK = "What would you like to see?"
SAY_BLOCKED = ("That's not something I'll show, but I'd love to find you something else. "
               "What else would you like to see?")  # M4a: she never picks a subject herself
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
                   r"coat[\s-]*of[\s-]*arms|locator|emblems?|seal[\s-]+of|charts?|graphs?|"
                   r"mascots?|costumes?|jerseys?|uniforms?|helmets?|stadiums?|teams?|cheerleaders?)(?![a-z])",  # M4a
                   re.IGNORECASE)
# M4a: pages and files about a namesake, not the thing itself: a ball club, a film or a mascot named for it
_NAMESAKE = re.compile(r"(?<![a-z])(?:mascots?|costumes?|teams?|franchises?|athletics?|baseball|football|basketball|"
                       r"hockey|soccer|nfl|mlb|nba|nhl|ncaa|sports?|logos?|season|film|album|song|band|novel|"
                       r"video[\s-]*game|television|tv[\s-]+series|fictional|character|comic)(?![a-z])", re.IGNORECASE)
_NATURAL = re.compile(r"(?<![a-z])(?:species|genus|birds?|mammals?|animals?|breeds?|plants?|trees?|flowers?|fish|"
                      r"insects?|reptiles?|amphibians?)(?![a-z])", re.IGNORECASE)
# M4a: narrow on purpose: even a page named exactly what they asked for loses if it's one of these
_MASCOT = re.compile(r"(?<![a-z])(?:mascots?|costumes?|logos?)(?![a-z])", re.IGNORECASE)
_FILLER = {"a", "an", "the", "some"}  # M4a: "the canyon" asks for the same thing as "canyon"
_TAG = re.compile(r"<[^>]*>")
_TAG_CUT = re.compile(r"<[a-zA-Z/!][^>]*$")  # M4a: a tag cut off by a limit, with no closing >
_ENTITY = re.compile(r"&#?[a-zA-Z0-9]+;|&(?:#\w*|[a-z]{2,8})$")  # M4a: unknown, or cut off at the end (not "AT&T")
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
    """Wikipedia HTML as short plain text: no tags, whole or cut off, no entities, even encoded twice, single spaces."""
    text = _no_tags(str(value or ""))
    for _ in range(3):  # M4a
        text = _no_tags(html.unescape(text))
    return _cap(" ".join(_ENTITY.sub(" ", " ".join(text.split())).split()), limit)


def _no_tags(text):  # M4a
    return _TAG_CUT.sub(" ", _TAG.sub(" ", text))


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


def _words(text):
    return [w[:-1] if w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", str(text or "").lower())]


def _spread(name):  # M4a: "BigMascot.jpg" reads as two words, so whole-word patterns can see it
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(name or ""))


def _rank(page, query):  # M4a: 0 is best; Wikipedia's own order decides within a rank
    """The article named exactly what they asked for, then a living thing named for it, then the rest, then namesakes.
    Last of all, only when nothing else exists: a drawing (.svg), or a mascot, costume or logo even under the exact name."""
    title, image = str(page.get("title") or ""), _spread(page.get("pageimage"))
    asked = [w for w in _words(query) if w not in _FILLER]
    if image.lower().endswith(".svg"):
        return RANK_LAST
    text = f"{title} {page.get('extract') or ''}"
    if asked and _words(title) == asked:
        return RANK_LAST if _MASCOT.search(f"{_spread(text)} {image}") and not _MASCOT.search(query) else 0
    if _NAMESAKE.search(f"{text} {image}") and not _NAMESAKE.search(query):
        return 3
    return 1 if set(asked) & set(_words(title)) and _NATURAL.search(text) else 2


def pick_pages(data, query=""):
    """Search results, best first, with a free lead picture: no disambiguation pages, nothing blocked. M4a: query
    puts the real thing ahead of teams, mascots and other namesakes."""
    out = []
    order = lambda p: (_rank(p, query) if query else 0, p["index"] if isinstance(p.get("index"), int) else 99)
    for page in sorted(_pages(data), key=order):
        thumb = page.get("thumbnail") if isinstance(page.get("thumbnail"), dict) else {}
        title, image = str(page.get("title") or ""), _norm(page.get("pageimage"))
        props = page.get("pageprops") if isinstance(page.get("pageprops"), dict) else {}
        if not title or not image or not thumb.get("source") or "disambiguation" in props:
            continue
        if blocked(title) or blocked(image):
            continue
        shown = plain_text(title, TITLE_MAX)  # M4a: the title reaches her caption and her "say" too
        if not shown:
            continue
        out.append({"page": title, "title": shown, "image": image, "src": str(thumb["source"]),
                    "summary": plain_text(page.get("extract"), SUMMARY_MAX), "rank": order(page)[0]})
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
    return {"action": "query", "generator": "search", "gsrsearch": query, "gsrnamespace": 0, "gsrlimit": 10,
            "prop": "pageimages|extracts|pageprops", "piprop": "thumbnail|name", "pithumbsize": IMAGE_WIDTH,
            "pilicense": "free", "exintro": 1, "explaintext": 1, "exsentences": 2, "redirects": 1}


def _find_pages(ctx, query, deadline):  # M4a
    """Search results with a free lead picture, best first. When none is the thing itself or a living thing named for
    it, one more search with "species" added; never more than that."""
    pages = pick_pages(_api(ctx, _search_params(query), deadline), query)
    if any(p["rank"] <= 1 for p in pages):
        return pages
    try:
        more = pick_pages(_api(ctx, _search_params(query + " species"), deadline), query)
    except _NetError:
        if pages:
            return pages
        raise
    known = {p["page"] for p in pages}
    return sorted(pages + [p for p in more if p["page"] not in known], key=lambda p: p["rank"])


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


def verdict(answer):  # M4a
    """The first word's YES or NO (None when it's neither) and what follows as plain text."""
    match = re.match(r"\W*(yes|no)\b\W*(.*)", str(answer or "").strip(), re.IGNORECASE | re.DOTALL)
    if not match:
        return None, ""
    return match.group(1).lower() == "yes", plain_text(match.group(2), SEEN_MAX)


def _look(ctx, got, query, title, deadline):  # M4a
    """Has Mary look at the picture: (True, sentence), (False, sentence), or (None, "") when there's no answer."""
    if deadline - time.monotonic() < LOOK_MIN_S:
        return None, ""
    subject = query if _words(query) == _words(title) else f'{query} (the article "{title}")'
    return verdict(ctx.look(got[0], MIMES.get(got[1], "image/jpeg"), ASK_SEEN.format(subject=subject)))


def _pick_picture(ctx, pages, query, deadline):  # M4a
    """The first candidate that loads and isn't turned down: (page, (bytes, type), seen), or None. Only a real NO turns
    one down: with no answer the picture stands, with no seen line. Two NOs and she stops looking."""
    looks = 0
    for page in pages[:TRIES]:
        got = _image(ctx, page["src"], deadline)
        if not got:
            continue
        looks += 1
        yes, seen = _look(ctx, got, query, page["title"], deadline)
        if yes is not False:
            return page, got, seen
        if looks >= LOOKS_MAX:
            return None
    return None


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
    out = {"title": s["title"], "summary": s["summary"], "credit": s["credit"], "say": f"Here's {s['title']}."}
    if s.get("seen"):  # M4a: what the picture really shows, so she talks about that
        out["seen"] = s["seen"]
    return out


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
        picked = _pick_picture(ctx, _find_pages(ctx, query, deadline), query, deadline)  # M4a
    except _NetError as err:
        return {"say": _say_for(err.reason)}
    if not picked:
        return {"found": False, "say": SAY_NOT_FOUND}
    page, got, seen = picked
    try:
        credit = _credit(ctx, page["image"], deadline)
    except _NetError:
        credit = CREDIT_FALLBACK
    file = _store(ctx, *got)
    ctx.state.update(title=page["title"], summary=page["summary"], credit=credit, file=file, query=query,
                     page=page["page"], shown=[page["image"]], seen=seen)  # M4a: seen
    return _show(ctx)


def next_picture(ctx):
    """Another free photo (from Wikimedia Commons) from the same article, one not shown yet."""
    page, title = ctx.state.get("page"), ctx.state.get("title")
    if not page:
        return {"say": SAY_NO_PICTURE}
    shown = ctx.state.setdefault("shown", [])
    line = "the only picture" if len(shown) <= 1 else "all the pictures"
    nothing = {"title": title, "say": f"That's {line} I have of {title}."}
    deadline = time.monotonic() + TIME_BUDGET_S
    looks = 0  # M4a
    try:
        listed = _api(ctx, {"action": "query", "titles": page, "prop": "images", "imlimit": 50, "redirects": 1},
                      deadline)
        fresh = pick_files([i.get("title") for p in _pages(listed) for i in _list(p.get("images"))], shown)[:TRIES]
        if not fresh:
            return nothing
        infos = {_norm(p.get("title")): p for p in _pages(_api(ctx, _info_params(fresh, IMAGE_WIDTH), deadline))}
        for name in fresh:
            p = infos.get(name, {})
            info = _info(p)
            got = (_image(ctx, info.get("thumburl") or info.get("url"), deadline)
                   if p.get("imagerepository") == "shared" else None)  # Commons only: every file there is free
            yes, seen = None, ""
            if got:  # M4a: a file from the article can be anything: shown only when she sees it's the real thing
                looks += 1
                yes, seen = _look(ctx, got, ctx.state.get("query") or title, title, deadline)
                if yes is None:  # no answer: not shown, and not counted as tried
                    return nothing
            shown.append(name)
            del shown[:-SHOWN_MAX]
            if yes:
                ctx.state.update(file=_store(ctx, *got), credit=credit_text(info.get("extmetadata"), "shared"), seen=seen)
                return _show(ctx)
            if looks >= LOOKS_MAX:
                return nothing
    except _NetError as err:
        return {"say": _say_for(err.reason)}
    return nothing if looks else {"title": title, "say": SAY_FAILED}


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
    """What Mary sees: the picture's title, what it really shows (M4a), its two-sentence summary and the credit."""
    if not state.get("title"):
        return "No picture is up."
    parts = [f"A picture of {state['title']} is on the screen.",
             f"Seen: {state['seen']}" if state.get("seen") else "", state.get("summary") or "",  # M4a: seen
             f"({state['credit']})" if state.get("credit") else ""]
    return _cap(" ".join(" ".join(parts).split()), VIEW_MAX - 1)
