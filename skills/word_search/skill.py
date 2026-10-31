"""Word search: a big-print puzzle on a topic the resident likes, played by voice or by touch.

The puzzle itself is pure functions (make_puzzle). The live puzzle sits in ctx.state and is mirrored to ctx.store so it
survives a restart. Where an unfound word lies never goes in a response or in view(), only in the effects for a found
or shown word and in the hint the resident asked for. What Mary knows about a resident only ever picks the theme.
"""
import difflib
import functools
import random
import re
import threading

SMALLEST = 3
# level: (grid size, words, longest word, diagonal, backward). Change DEFAULT_LEVEL to 1 to open on the 8x8.
LEVELS = {1: (8, 6, 6, False, False), 2: (10, 10, 8, False, False), 3: (12, 14, 10, False, False),
          4: (12, 14, 12, True, False), 5: (12, 14, 12, True, True)}
DEFAULT_LEVEL = 2

# Placing words is a search that gives up and starts over; these bound it well inside the 2 second skill limit.
SEARCH_STEPS = 4000       # steps of one try
SEARCH_TRIES = 60         # tries before a word is given up on
FILLER_PASSES = 200       # filler re-rolls before the whole try starts again

ACROSS_DOWN = ((0, 1), (1, 0))
DIAGONALS = ((1, 1), (-1, 1))
REVERSED = ((0, -1), (-1, 0), (-1, -1), (1, -1))

# Never reads in the filler, in any direction. Theme and Gemini words can't be these, though a fair word may hold one
# (BASS, GRASS).
BLOCKLIST = frozenset("""
    ANAL ARSE ASS BITCH BOOB CHINK COCK COON CRAP CUNT DAGO DICK DYKE FAG FAGGOT FUCK GOOK HOMO JIZZ KIKE NAZI NIGGA
    NIGGER PAKI PENIS PISS PUSSY RAPE RETARD SHIT SLUT SPIC TIT TITS TWAT VAGINA WANK WHORE WOP
""".split())

THEMES = {
    "fishing": {"title": "Fishing",
                "keywords": ["fishing", "fish", "fisherman", "lake", "river", "pond", "bass"],
                "words": [
                    "BASS", "TROUT", "CATFISH", "BOBBER", "TACKLE", "CREEL", "WORM", "DOCK", "LURE", "ROD", "SINKER",
                    "HOOK", "PERCH", "CRAPPIE", "MINNOW", "BREAM", "BLUEGILL", "SALMON", "WALLEYE", "REEL", "LINE",
                    "SPINNER", "JIG", "CRICKET", "WADERS", "CANOE", "BOAT", "PADDLE", "LAKE", "RIVER", "STREAM",
                    "CREEK", "BAIT", "CAST", "SHORE", "FILLET", "STRINGER", "SWIVEL", "FLOAT", "PIER", "ANGLER"]},
    "gardening": {"title": "Gardening",
                "keywords": ["garden", "gardening", "flowers", "vegetables", "tomatoes", "roses", "planting", "yard"],
                "words": [
                    "TOMATO", "SQUASH", "BEANS", "CORN", "HOE", "SPADE", "SEED", "ROSES", "WEEDS", "MULCH", "SOIL",
                    "PEPPER", "TROWEL", "RAKE", "COMPOST", "FENCE", "CARROT", "LETTUCE", "CUCUMBER", "OKRA",
                    "RADISH", "ONION", "POTATO", "PEAS", "CABBAGE", "ZINNIA", "MARIGOLD", "TULIP", "DAISY", "SHOVEL",
                    "WATER", "SPROUT", "BLOOM", "HARVEST", "PLANT", "FLOWER", "BED", "GLOVES", "SUNSHINE"]},
    "church": {"title": "Church",
                "keywords": ["church", "faith", "prayer", "bible", "hymns", "pastor", "sunday", "god", "gospel"],
                "words": [
                    "HYMN", "PEW", "PASTOR", "CHOIR", "BIBLE", "PRAYER", "SERMON", "DEACON", "STEEPLE", "ALTAR",
                    "BAPTISM", "PSALM", "GRACE", "ORGAN", "SUNDAY", "AMEN", "FAITH", "BLESSING", "GOSPEL", "CROSS",
                    "PRAISE", "WORSHIP", "SPIRIT", "HOPE", "MERCY", "SINGING", "PIANO", "USHER", "OFFERING",
                    "COMMUNION", "CHAPEL", "BELL", "CHURCH", "GLORY", "TESTIMONY", "REVIVAL", "SCRIPTURE", "PRAYING",
                    "CANDLE", "SAVIOR"]},
    "cooking": {"title": "Cooking",
                "keywords": ["cooking", "cook", "baking", "recipes", "kitchen", "food", "biscuits"],
                "words": [
                    "BISCUIT", "GRAVY", "SKILLET", "BACON", "FLOUR", "BUTTER", "PIE", "STEW", "OVEN", "SALT",
                    "PEPPER", "ONION", "ROAST", "SUGAR", "LADLE", "CORNBREAD", "APRON", "WHISK", "SPATULA",
                    "CASSEROLE", "COBBLER", "MUFFIN", "PANCAKE", "SAUSAGE", "GRITS", "BEANS", "CHICKEN", "MEATLOAF",
                    "FRY", "BOIL", "SIMMER", "BAKE", "GRILL", "SPICE", "CINNAMON", "VANILLA", "RECIPE", "TEASPOON",
                    "POTATO"]},
    "trucks": {"title": "Trucks",
                "keywords": ["trucks", "truck", "pickup", "cars", "driving", "mechanic", "engine"],
                "words": [
                    "PICKUP", "DIESEL", "TAILGATE", "TIRE", "ENGINE", "HITCH", "TRAILER", "BUMPER", "HAUL", "CAB",
                    "RADIO", "WINCH", "GEARS", "MUFFLER", "HEADLIGHT", "BED", "MIRROR", "HORN", "BRAKES", "CLUTCH",
                    "WHEEL", "AXLE", "FENDER", "GRILLE", "DASHBOARD", "FUEL", "TANK", "TOWING", "CARGO", "LOAD",
                    "ROAD", "HIGHWAY", "DRIVER", "TRUCKER", "PEDAL", "WIPER", "WINDSHIELD", "TOOLBOX", "MILES"]},
    "birds": {"title": "Birds",
                "keywords": ["birds", "bird", "birdwatching", "feeder", "cardinals"],
                "words": [
                    "CARDINAL", "ROBIN", "BLUEJAY", "WREN", "CROW", "HAWK", "OWL", "DOVE", "SPARROW", "FINCH",
                    "HERON", "EAGLE", "QUAIL", "TURKEY", "GOOSE", "MOCKINGBIRD", "DUCK", "SWAN", "CRANE", "FALCON",
                    "PELICAN", "WOODPECKER", "HUMMINGBIRD", "BLACKBIRD", "STARLING", "SWALLOW", "BLUEBIRD",
                    "PHEASANT", "VULTURE", "OSPREY", "KILLDEER", "NEST", "FEATHER", "WING", "BEAK", "FEEDER", "SEED",
                    "FLOCK", "CHIRP", "SONG", "PERCH"]},
    "north_carolina": {"title": "North Carolina",
                "keywords": ["north carolina", "carolina", "raleigh", "asheville", "charlotte", "outer banks"],
                "words": [
                    "RALEIGH", "DURHAM", "BOONE", "COAST", "BEACH", "PINE", "PIEDMONT", "DOGWOOD", "TARHEEL",
                    "CARDINAL", "BARBECUE", "HATTERAS", "ASHEVILLE", "CHARLOTTE", "MOUNTAIN", "PEANUT", "WILMINGTON",
                    "GREENSBORO", "FAYETTEVILLE", "CHAPEL", "TOBACCO", "BLUEGRASS", "SWEETPOTATO", "LIGHTHOUSE",
                    "WRIGHT", "BROTHERS", "KITTYHAWK", "OCRACOKE", "NASCAR", "BLUERIDGE", "SMOKIES", "APPALACHIAN",
                    "CAROLINA", "PECAN", "HUSHPUPPY", "MOREHEAD", "CAPE", "FARMS", "MARSH"]},
    "holidays": {"title": "Holidays",
                "keywords": ["holidays", "holiday", "christmas", "thanksgiving", "easter", "fourth of july"],
                "words": [
                    "CHRISTMAS", "EASTER", "TURKEY", "THANKSGIVING", "FIREWORKS", "PARADE", "GIFTS", "STOCKING",
                    "CANDY", "WREATH", "CAROLS", "FEAST", "PUMPKIN", "HAM", "FLAG", "BELLS", "SANTA", "TINSEL",
                    "ORNAMENT", "MANGER", "SLEIGH", "SNOWMAN", "COOKIES", "STUFFING", "CRANBERRY", "HARVEST",
                    "PICNIC", "SPARKLER", "BASKET", "EGGS", "BUNNY", "LILY", "GARLAND", "MISTLETOE", "CANDLE",
                    "FAMILY", "GATHER", "GRATEFUL", "BLESSED"]},
    "farm": {"title": "Farm",
                "keywords": ["farm", "farming", "farmer", "cows", "cattle", "tractor", "barn", "chickens", "hay"],
                "words": [
                    "BARN", "TRACTOR", "COW", "HORSE", "PIG", "GOAT", "SHEEP", "CHICKEN", "ROOSTER", "HAYLOFT",
                    "PASTURE", "FIELD", "CROPS", "PLOW", "COTTON", "SOYBEANS", "WHEAT", "SILO", "FENCE", "GATE",
                    "TROUGH", "STABLE", "MEADOW", "HARVEST", "MILK", "EGGS", "CALF", "FOAL", "COOP", "DAIRY",
                    "CORNFIELD", "TOBACCO", "SEEDS", "COMBINE", "HARROW", "PITCHFORK", "BUCKET", "SADDLE", "ORCHARD",
                    "ACRES"]},
    "baseball": {"title": "Baseball",
                "keywords": ["baseball", "ball game", "softball", "pitcher", "braves", "umpire"],
                "words": [
                    "PITCHER", "CATCHER", "BATTER", "UMPIRE", "INNING", "STRIKE", "HOMERUN", "DUGOUT", "MOUND",
                    "GLOVE", "BASES", "DIAMOND", "OUTFIELD", "INFIELD", "SHORTSTOP", "FASTBALL", "CURVEBALL", "BUNT",
                    "STEAL", "SLIDE", "SINGLE", "DOUBLE", "TRIPLE", "WALK", "FOUL", "FLY", "GRANDSLAM", "BULLPEN",
                    "STADIUM", "PENNANT", "HOTDOG", "PEANUTS", "ROOKIE", "COACH", "SCORE", "TEAM", "LEAGUE",
                    "BATTING", "HELMET"]},
    "old_cars": {"title": "Old Cars",
                "keywords": ["old cars", "classic cars", "antique cars", "hot rod", "mustang", "chevy", "model t", "roadster"],
                "words": [
                    "MUSTANG", "CAMARO", "CORVETTE", "CHEVY", "FORD", "BUICK", "CADILLAC", "PONTIAC", "IMPALA",
                    "BELAIR", "COUPE", "SEDAN", "ROADSTER", "CONVERTIBLE", "HOTROD", "CHROME", "FENDER", "HUBCAP",
                    "GRILLE", "WHITEWALL", "RUNNING", "BOARD", "DRIVEIN", "CRUISE", "CRUISING", "GARAGE", "ENGINE",
                    "HORSEPOWER", "CARBURETOR", "POLISH", "WAX", "RESTORE", "ANTIQUE", "VINTAGE", "CLASSIC", "SHOW",
                    "TAILFIN", "RUMBLE", "DASHBOARD", "STEERING"]},
    "hunting": {"title": "Hunting",
                "keywords": ["hunting", "hunter", "deer", "turkey season", "duck", "rifle", "woods"],
                "words": [
                    "DEER", "RIFLE", "DECOY", "STAND", "BUCK", "DOE", "ANTLER", "SCOPE", "CAMO", "BLIND", "TRACK",
                    "TRAIL", "WOODS", "FOREST", "DOG", "BEAGLE", "HOUND", "SQUIRREL", "RABBIT", "QUAIL", "DUCK",
                    "TURKEY", "GOOSE", "SHOTGUN", "BOW", "ARROW", "CALL", "SEASON", "LICENSE", "ORANGE", "BOOTS",
                    "THERMOS", "LODGE", "CAMP", "DAWN", "FIELD", "HARVEST", "HUNTER", "PURSUIT"]},
}

RECENT_KEEP = 20          # words of a theme remembered, so the next puzzle starts with the others
TAP_SAY_EVERY = 3         # a find by touch gets a word from her about one time in three
WORDS_TAKEN = 30          # at most this many words read from Gemini

ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh",
            "twelfth")
FOUND_LINES = ("There it is.", "That's the one.", "Yes, that's it.", "You've got it.")
TAP_LINES = ("There's your {word}.", "That's {word}.", "Got {word}.")
FINISH_LINES = ("That's all of them.", "That's every word.", "That's the whole list.")
NOT_ON_LIST = "I don't see that one on the list."
ALREADY = "You've already got that one."
NO_PUZZLE = "We don't have a puzzle going."
NOT_WORDS = frozenset(("THE", "A", "AN", "WORD", "IT", "ONE"))

_RNG = random.Random()
_LOCK = threading.Lock()   # a tap and a spoken line may land together


# ---------- the puzzle ----------

def _directions(diagonal, backward):
    """(row step, column step) of every way a word may run."""
    across_down = ACROSS_DOWN + (DIAGONALS if diagonal else ())
    if not backward:
        return across_down
    return across_down + (REVERSED if diagonal else REVERSED[:2])


@functools.lru_cache(maxsize=8)
def _lines(size):
    """Every row, column and diagonal of a grid as a tuple of cells, read one way."""
    lines = [tuple((r, c) for c in range(size)) for r in range(size)]
    lines += [tuple((r, c) for r in range(size)) for c in range(size)]
    for start in range(-(size - 1), size):
        lines.append(tuple((r, r - start) for r in range(size) if 0 <= r - start < size))
    for total in range(2 * size - 1):
        lines.append(tuple((r, total - r) for r in range(size) if 0 <= total - r < size))
    return [line for line in lines if len(line) >= SMALLEST]


def _copies(grid, word, lines):
    """Every place word reads in the grid, either way along any line, one entry per set of cells."""
    seen = {}
    for line in lines:
        text = "".join(grid[r][c] for r, c in line)
        for shown, cells in ((text, line), (text[::-1], line[::-1])):
            at = shown.find(word)
            while at >= 0:
                piece = cells[at:at + len(word)]
                seen[frozenset(piece)] = piece
                at = shown.find(word, at + 1)
    return list(seen.values())


def _contained(word, other):
    """True when word can't be alone in a grid holding other, because other holds it (or the same letters backward)."""
    return word in other or word[::-1] in other


def _usable(words, size):
    """Upper-case, in-size, distinct words. A word inside a longer one goes, since it could never appear just once."""
    kept = []
    for word in words:
        word = str(word).upper()
        if SMALLEST <= len(word) <= size and word.isalpha() and word not in kept:
            kept.append(word)
    return [w for w in kept if not any(o != w and (len(o), o) > (len(w), w) and _contained(w, o) for o in kept)]


def _spots(word, size, directions):
    """Every way word fits inside the grid, as lists of cells."""
    spots = []
    for dr, dc in directions:
        for r in range(size):
            for c in range(size):
                end_r, end_c = r + dr * (len(word) - 1), c + dc * (len(word) - 1)
                if 0 <= end_r < size and 0 <= end_c < size:
                    spots.append([(r + dr * i, c + dc * i) for i in range(len(word))])
    return spots


def _place(words, spots, rng):
    """One try at a place for every word, longest first, stepping back on a dead end. {word: cells}, or None."""
    order = sorted(words, key=len, reverse=True)
    for word in order:
        rng.shuffle(spots[word])
    letters, chosen, steps = {}, {}, [SEARCH_STEPS]

    def fits(word, cells):
        return all(letters.get(cell, ch) == ch for cell, ch in zip(cells, word))

    def go(index):
        if index == len(order):
            return True
        word = order[index]
        for cells in spots[word]:
            steps[0] -= 1
            if steps[0] < 0:
                return False
            if not fits(word, cells):
                continue
            added = [cell for cell in cells if cell not in letters]
            letters.update(zip(cells, word))
            chosen[word] = cells
            if go(index + 1):
                return True
            for cell in added:
                del letters[cell]
        return False

    return chosen if go(0) else None


def _fill(chosen, size, rng):
    """The finished grid, or None when the words themselves form a second copy of a word or a word off the blocklist.
    Filler is re-rolled until no word appears twice and nothing crude reads anywhere."""
    letters = {cell: ch for word, cells in chosen.items() for cell, ch in zip(cells, word)}
    grid = [[letters.get((r, c)) or rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for c in range(size)] for r in range(size)]
    lines = _lines(size)
    homes = [set(cells) for cells in chosen.values()]
    for _ in range(FILLER_PASSES):
        bad = []
        for word, cells in chosen.items():
            home = set(cells)
            bad += [copy for copy in _copies(grid, word, lines) if set(copy) != home]
        for word in BLOCKLIST:
            # A blocked word wholly inside one fair word (ASS in BASS) stays: that's the word, not the filler.
            bad += [copy for copy in _copies(grid, word, lines) if not any(set(copy) <= home for home in homes)]
        if not bad:
            return ["".join(row) for row in grid]
        for copy in bad:
            filler = [cell for cell in copy if cell not in letters]
            if not filler:
                return None
            r, c = rng.choice(filler)
            grid[r][c] = rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return None


def make_puzzle(words, size, diagonal=False, backward=False, rng=None):
    """A grid of size rows and {word, cells} for every word placed. Every word reads along its cells, inside the grid,
    exactly once in any direction, and words may share letters where they cross. A word goes only if it's too long,
    sits inside a longer word, or still can't fit after every try: then the last one given is dropped, never the
    longest as such, and the rest are tried again."""
    rng = rng or random.Random()
    usable = _usable(words, size)
    directions = _directions(diagonal, backward)
    spots = {word: _spots(word, size, directions) for word in usable}
    while True:
        for _ in range(SEARCH_TRIES):
            chosen = _place(usable, spots, rng)
            grid = _fill(chosen, size, rng) if chosen is not None else None
            if grid is not None:
                placed = [{"word": w, "cells": [list(cell) for cell in chosen[w]]} for w in usable]
                return {"grid": grid, "placed": placed, "size": size, "diagonal": bool(diagonal),
                        "backward": bool(backward)}
        usable = usable[:-1]


# ---------- choosing the words ----------

def _clean_words(words, size):
    """Gemini's words, made safe: letters only, upper case, 3 to size long, not blocked, no repeats."""
    if not isinstance(words, list):
        return []
    clean = []
    for word in words[:WORDS_TAKEN]:
        word = str(word).strip().upper()
        if (word.isascii() and word.isalpha() and SMALLEST <= len(word) <= size and word not in BLOCKLIST
                and word[:-1] not in BLOCKLIST and word not in clean):
            clean.append(word)
    return clean


def _clean_title(topic):
    """A topic fit for the top of the page, or "" if there's nothing fit in it."""
    title = " ".join(re.findall(r"[A-Za-z]+", str(topic or "")))[:40].strip()
    if any(word.upper() in BLOCKLIST for word in title.split()):
        return ""
    return title.title() if title.islower() else title


def _find_theme(text):
    """The theme whose title or a keyword is in text, or None."""
    padded = " " + " ".join(re.findall(r"[a-z]+", str(text or "").lower())) + " "
    for key, theme in THEMES.items():
        if any(f" {word} " in padded or f" {word}s " in padded for word in (theme["title"].lower(), *theme["keywords"])):
            return key
    return None


def _interest_theme(ctx):
    """A theme from what she knows about them, starting after the last one used; else simply the next one."""
    keys = list(THEMES)
    last = ctx.store.get("last_theme")
    start = keys.index(last) + 1 if last in THEMES else 0
    order = [k for k in keys[start:] + keys[:start] if k != last]
    for key in order:
        if ctx.recall(" ".join(THEMES[key]["keywords"]), limit=1):
            return key
    return order[0]


def _pick_words(key, count, longest, size, have, recent):
    """have, topped up from the theme to count: fresh words first, then ones used lately, then longer ones."""
    words = list(THEMES[key]["words"])
    _RNG.shuffle(words)
    words.sort(key=lambda w: (len(w) > longest, w in recent))
    picked = list(have)
    for word in words:
        if len(picked) >= count:
            break
        if len(word) <= size and not any(_contained(word, o) or _contained(o, word) for o in picked):
            picked.append(word)
    return picked


# ---------- the saved puzzle ----------

def _sound(saved):
    """True when something read back from the store is a puzzle this code can use."""
    try:
        return (saved["size"] == len(saved["grid"]) and bool(saved["placed"]) and saved["level"] in LEVELS
                and isinstance(saved["found"], list) and isinstance(saved["shown"], list))
    except (KeyError, TypeError):
        return False


def _current(ctx, reopen=False):
    """The puzzle up now (even a finished one), back from the store if the app restarted. One put away with end() isn't
    up until the page opens it again (reopen)."""
    puzzle = ctx.state.get("puzzle")
    if puzzle:
        return puzzle
    saved = ctx.store.get("puzzle")
    if _sound(saved) and (reopen or not saved.get("closed")):
        ctx.state["puzzle"] = saved
        return saved
    return None


def _live(ctx):
    """The puzzle being played: up and not finished."""
    puzzle = _current(ctx)
    return None if puzzle is None or puzzle["finished"] else puzzle


def _save(ctx, puzzle):
    ctx.store.put("puzzle", puzzle)


def _none():
    """No puzzle up: not for this skill. Offline, her normal line runs; Gemini gets the plain answer."""
    return {"not_for_me": True, "say": NO_PUZZLE}


def _cells(puzzle, word):
    return next(p["cells"] for p in puzzle["placed"] if p["word"] == word)


def _left(puzzle):
    done = set(puzzle["found"]) | set(puzzle["shown"])
    return [p["word"] for p in puzzle["placed"] if p["word"] not in done]


def _hint_state(puzzle):
    """What the page draws for the hint: never more than the resident has asked for."""
    hint = puzzle["hint"]
    if not hint:
        return None
    state = {"word": hint["word"], "step": hint["step"], "line": _line(_cells(puzzle, hint["word"]))}
    if hint["step"] >= 2:
        state["cell"] = _cells(puzzle, hint["word"])[0]
    return state


def _page(puzzle):
    """The `puzzle` effect: all the page needs to redraw."""
    return {"grid": puzzle["grid"], "words": sorted(p["word"] for p in puzzle["placed"]), "theme": puzzle["title"],
            "size": puzzle["size"], "level": puzzle["level"], "diagonal": puzzle["diagonal"],
            "backward": puzzle["backward"], "found": [{"word": w, "cells": _cells(puzzle, w)} for w in puzzle["found"]],
            "shown": [{"word": w, "cells": _cells(puzzle, w)} for w in puzzle["shown"]],
            "hint": _hint_state(puzzle), "finished": puzzle["finished"]}


# ---------- doing things ----------

def _start(ctx, topic="", words=None, level=None, diagonal=None, backward=None, theme=None, show=True, say=None):
    """A new puzzle, saved and sent to the page. Returns the response."""
    if isinstance(level, int) and level in LEVELS:
        ctx.store.put("level", level)
    else:
        level = ctx.store.get("level", DEFAULT_LEVEL)
        level = level if level in LEVELS else DEFAULT_LEVEL
    size, count, longest, level_diagonal, level_backward = LEVELS[level]
    diagonal = level_diagonal if diagonal is None else diagonal
    backward = level_backward if backward is None else backward

    title = _clean_title(topic)
    key = theme or _find_theme(topic)
    custom = [] if key and not theme else _clean_words(words, size)[:count]
    if key is None and not topic:
        key = _find_theme(ctx.heard)  # offline: "a word search on birds"
    enough = len(custom) * 2 >= count
    if key is None:
        key = _interest_theme(ctx)
        if title and not enough:
            say = f"I don't have a list for {title.lower()}, so here's one on {THEMES[key]['title'].lower()}."
    if enough and not title:
        title = "Your words"
    title = title if enough else THEMES[key]["title"]

    recent = ctx.store.get("recent", {})
    recent = recent if isinstance(recent, dict) else {}
    used = recent.get(key, [])
    chosen = _pick_words(key, count, longest, size, custom, used if isinstance(used, list) else [])
    made = make_puzzle(chosen, size, diagonal, backward, _RNG)
    themed = [p["word"] for p in made["placed"] if p["word"] not in custom]
    recent[key] = (list(used) + themed)[-RECENT_KEEP:] if isinstance(used, list) else themed
    ctx.store.put("recent", recent)
    ctx.store.put("last_theme", key)

    puzzle = dict(made, theme=key, title=title, level=level, topic=str(topic or "")[:60], custom=custom,
                  found=[], shown=[], hint=None, finished=False, closed=False, tap_finds=0)
    ctx.state["puzzle"] = puzzle
    _save(ctx, puzzle)
    if show:
        ctx.effect("show_screen")
    ctx.effect("puzzle", _page(puzzle))
    return {"ok": True, "theme": title, "size": size, "level": level, "words_left": len(puzzle["placed"]),
            "say": say or f"Here's one on {title.lower()}."}


def _again(ctx, puzzle, level, show, say=None):
    """A new puzzle on the same theme or the same words."""
    return _start(ctx, topic=puzzle["topic"], words=puzzle["custom"], level=level, theme=puzzle["theme"], show=show,
                  say=say)


def _step(ctx, puzzle, change, show):
    """One level easier or harder; at the ends she says so and a puzzle in play stays as it is."""
    level = puzzle["level"] + change
    if level not in LEVELS:
        end = "This is the easiest one I have." if change < 0 else "This is as hard as they come."
        if puzzle["finished"]:
            return _again(ctx, puzzle, puzzle["level"], show, say=end + " Here's another.")
        return {"ok": True, "level": puzzle["level"], "at_end": True, "say": end}
    return _again(ctx, puzzle, level, show, say="Here's an easier one." if change < 0 else "Here's a harder one.")


def _finish(ctx, puzzle):
    """The last word is in. Returns her line."""
    puzzle["finished"] = True
    puzzle["hint"] = None
    ctx.store.delete("puzzle")
    ctx.effect("done", {"found": len(puzzle["found"]), "shown": len(puzzle["shown"])})
    return _RNG.choice(FINISH_LINES)


def _mark(ctx, puzzle, word, kind):
    """A word is in, as "found" or "shown". Her finish line when it was the last, else None."""
    puzzle[kind].append(word)
    if puzzle["hint"] and puzzle["hint"]["word"] == word:
        puzzle["hint"] = None
    ctx.effect(kind, {"word": word, "cells": _cells(puzzle, word)})
    if not _left(puzzle):
        return _finish(ctx, puzzle)
    _save(ctx, puzzle)
    return None


def _forms(text):
    """text and what it could be with a plural said or left off."""
    forms = [text, text + "S", text + "ES"]
    if text.endswith("S"):
        forms.append(text[:-1])
    if text.endswith("ES"):
        forms.append(text[:-2])
    return forms


def _resolve(puzzle, text):
    """Spoken text to ("left" | "done" | "no", word). Spoken text is messy: a plural is fine, and so is one small slip
    when only one word left is close."""
    tokens = [t for t in re.findall(r"[A-Z]+", str(text or "").upper()) if t not in NOT_WORDS]
    guesses = ["".join(tokens)] + tokens if len(tokens) > 1 else tokens
    left = _left(puzzle)
    done = puzzle["found"] + puzzle["shown"]
    for wanted, kind in ((left, "left"), (done, "done")):
        for guess in guesses:
            for form in _forms(guess):
                if form in wanted:
                    return kind, form
    close = {match for guess in guesses if len(guess) >= SMALLEST
             for match in difflib.get_close_matches(guess, left, n=3, cutoff=0.75)}
    if len(close) == 1:
        return "left", close.pop()
    return "no", None


def _spoken_word(heard):
    """The words after "found" in an offline line."""
    match = re.search(r"\bfound\b(.*)", str(heard or ""), re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else ""


def _line(cells):
    """The line a word lies on: a row, a column, or for a diagonal where it starts (index is its row)."""
    (r, c), (r2, c2) = cells[0], cells[-1]
    if r == r2:
        return {"kind": "row", "index": r}
    if c == c2:
        return {"kind": "column", "index": c}
    return {"kind": "diagonal", "index": r, "start": [r, c]}


def _line_words(line):
    if line["kind"] == "diagonal":
        r, c = line["start"]
        return f"on a slant, starting in the {ORDINALS[r]} row, {ORDINALS[c]} column"
    return f"in the {ORDINALS[line['index']]} {line['kind']}"


def _locked(fn):
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with _LOCK:
            return fn(*args, **kwargs)
    return run


# ---------- the actions ----------

@_locked
def start(ctx, topic="", words=None, level=None, diagonal=None, backward=None):
    if not topic and not words and level is None:
        puzzle = _current(ctx, reopen=True)
        if puzzle is not None and not puzzle["finished"]:  # M7a: a puzzle in progress is brought back, not thrown away
            puzzle["closed"] = False
            _save(ctx, puzzle)
            ctx.effect("show_screen")
            ctx.effect("puzzle", _page(puzzle))
            return {"ok": True, "resumed": True, "theme": puzzle["title"], "words_left": len(_left(puzzle)),
                    "say": "Here's where you left off."}
    return _start(ctx, topic, words, level, diagonal, backward)


@_locked
def new_puzzle(ctx):
    return _start(ctx)


def _hint(ctx, word=None):
    puzzle = _live(ctx)
    if puzzle is None:
        return _none()
    named = None
    if word:
        kind, named = _resolve(puzzle, word)
        if kind == "no":
            return {"ok": True, "say": NOT_ON_LIST}
        if kind == "done":
            return {"ok": True, "say": ALREADY}
    hint = puzzle["hint"]
    picked = None
    if named and (not hint or hint["word"] != named):
        hint = {"word": named, "step": 0}
    elif not hint:
        hint = {"word": min(_left(puzzle), key=len), "step": 0}
        picked = hint["word"]
    hint["step"] = min(hint["step"] + 1, 3)
    puzzle["hint"] = hint
    _save(ctx, puzzle)
    cells = _cells(puzzle, hint["word"])
    line = _line(cells)
    if hint["step"] == 1:
        ctx.effect("hint", {"step": 1, "word": hint["word"], "line": line})
        where = f"It's {_line_words(line)}."
        return {"ok": True, "step": 1, "say": f"Try {picked.lower()}. {where}" if picked else where}
    if hint["step"] == 2:
        ctx.effect("hint", {"step": 2, "word": hint["word"], "cell": cells[0], "line": line})
        return {"ok": True, "step": 2, "say": f"I lit up the first letter. It's {hint['word'][0]}."}
    return {"ok": True, "step": 3, "say": "That's about all the hints I've got. Say show me where and I'll show you."}


@_locked
def hint(ctx, word=None):
    return _hint(ctx, word)


@_locked
def check(ctx, word=None):
    puzzle = _live(ctx)
    if puzzle is None:
        return _none()
    text = word or _spoken_word(ctx.heard)
    if not [t for t in re.findall(r"[A-Z]+", str(text).upper()) if t not in NOT_WORDS]:
        return {"ok": True, "found": None, "say": "Which one did you find?"}
    kind, match = _resolve(puzzle, text)
    if kind == "no":
        return {"ok": True, "found": None, "say": NOT_ON_LIST}
    if kind == "done":
        return {"ok": True, "found": None, "say": ALREADY}
    last = _mark(ctx, puzzle, match, "found")
    return {"ok": True, "found": match, "say": last or _RNG.choice(FOUND_LINES)}


@_locked
def show(ctx, word=None):
    puzzle = _live(ctx)
    if puzzle is None:
        return _none()
    target = None
    if word:
        kind, target = _resolve(puzzle, word)
        if kind == "no":
            return {"ok": True, "say": NOT_ON_LIST}
        if kind == "done":
            return {"ok": True, "say": ALREADY}
    elif puzzle["hint"]:
        target = puzzle["hint"]["word"]
    target = target or min(_left(puzzle), key=len)
    last = _mark(ctx, puzzle, target, "shown")
    return {"ok": True, "shown": target, "say": last or f"There's {target.lower()}."}


@_locked
def easier(ctx):
    puzzle = _current(ctx)
    return _none() if puzzle is None else _step(ctx, puzzle, -1, True)


@_locked
def harder(ctx):
    puzzle = _current(ctx)
    return _none() if puzzle is None else _step(ctx, puzzle, 1, True)


def _put_away(ctx, puzzle):
    """Off the screen; an unfinished puzzle stays in the store for next time."""
    if puzzle is not None:
        if not puzzle["finished"]:
            puzzle["closed"] = True
            _save(ctx, puzzle)
        ctx.state.pop("puzzle", None)
    ctx.effect("leave_screen")


@_locked
def end(ctx):
    puzzle = _current(ctx)
    if puzzle is None:
        return _none()
    kept = not puzzle["finished"]
    _put_away(ctx, puzzle)
    return {"ok": True, "say": "All right. I'll keep this one for you." if kept else "All right."}


# ---------- the screen ----------

def _cell(value, size):
    """A valid [row, column] as a tuple, else None."""
    if not isinstance(value, list) or len(value) != 2 or not all(type(n) is int for n in value):
        return None
    return tuple(value) if all(0 <= n < size for n in value) else None


def _straight(start_cell, end_cell, diagonal):
    """The cells from one end to the other on an allowed line, else None."""
    dr, dc = end_cell[0] - start_cell[0], end_cell[1] - start_cell[1]
    if dr and dc and (abs(dr) != abs(dc) or not diagonal):
        return None
    span = max(abs(dr), abs(dc))
    step_r, step_c = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
    return [[start_cell[0] + step_r * i, start_cell[1] + step_c * i] for i in range(span + 1)]


def _tap_line(ctx, event):
    puzzle = _live(ctx)
    if puzzle is None:
        return {"ignored": True}
    begin, finish = _cell(event.get("from"), puzzle["size"]), _cell(event.get("to"), puzzle["size"])
    cells = _straight(begin, finish, puzzle["diagonal"]) if begin and finish else None
    if cells is None:
        return {"ignored": True}
    left = _left(puzzle)
    for word in left:
        home = _cells(puzzle, word)
        if cells == home or cells == home[::-1]:
            last = _mark(ctx, puzzle, word, "found")
            puzzle["tap_finds"] += 1
            answer = {"found": word, "partial": False}
            if last:
                answer["say"] = last
            elif puzzle["tap_finds"] % TAP_SAY_EVERY == 0:
                answer["say"] = _RNG.choice(TAP_LINES).format(word=word.lower())
            _save(ctx, puzzle)
            return answer
    # By the letters, not the place, so tapping around can't give away where a word is.
    text = "".join(puzzle["grid"][r][c] for r, c in cells)
    partial = any(w.startswith(text) or w[::-1].startswith(text) for w in left)
    return {"found": None, "partial": partial}


def _new(ctx, event):
    wanted = event.get("level", "same")
    if wanted not in ("easier", "same", "harder"):
        return {"ignored": True}
    puzzle = _current(ctx)
    if puzzle is None:
        return _start(ctx, show=False)
    if wanted == "same":
        return _again(ctx, puzzle, puzzle["level"], False)
    return _step(ctx, puzzle, -1 if wanted == "easier" else 1, False)


@_locked
def on_event(ctx, event):
    kind = event.get("type")
    if kind == "open":
        puzzle = _current(ctx, reopen=True)
        if puzzle is None or puzzle["finished"]:
            return _start(ctx, show=False)
        puzzle["closed"] = False
        _save(ctx, puzzle)
        ctx.effect("puzzle", _page(puzzle))
        return {"ok": True}
    if kind == "line":
        return _tap_line(ctx, event)
    if kind == "hint":
        return _hint(ctx)
    if kind == "new":
        return _new(ctx, event)
    if kind == "close":
        _put_away(ctx, _current(ctx))
        return {"ok": True}
    return {"ignored": True}


def view(state):
    """What Mary sees: never where anything is."""
    puzzle = state.get("puzzle")
    if not puzzle:
        return "No puzzle up."
    left = _left(puzzle)
    parts = [f"Word search on {puzzle['title']}, {puzzle['size']} by {puzzle['size']}.",
             f"{len(left)} words left: {', '.join(left) or 'none'}.",
             f"Found: {', '.join(puzzle['found']) or 'none'}."]
    if puzzle["shown"]:
        parts.append(f"Shown by you: {', '.join(puzzle['shown'])}.")
    if puzzle["hint"]:
        parts.append(f"Hint step {puzzle['hint']['step']} on {puzzle['hint']['word']}.")
    if puzzle["finished"]:
        parts.append("Finished.")
    return " ".join(parts)
