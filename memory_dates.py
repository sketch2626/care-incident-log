"""Mary's family dates (M15a): birthdays and anniversaries read from a resident's plain words, on the laptop.

Says nothing unless the words are plain: a date she never saved costs little, and a wrong one, or a dead husband's
birthday, hurts. Standard library only; imports neither memory_core, server nor mary.
"""
import re
from calendar import monthrange
from datetime import date

MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")
_MONTH_DAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_OF = {name[:3].lower(): number for number, name in enumerate(MONTH_NAMES, 1)}
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
          r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_ONES = "one two three four five six seven eight nine".split()
_ORDS = "first second third fourth fifth sixth seventh eighth ninth".split()
_TEENS = "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TEEN_ORDS = ("tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth "
              "nineteenth").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety hundred thousand".split()
_WORD_VALUE = {**{w: n for n, w in enumerate(_ONES, 1)}, **{w: n for n, w in enumerate(_ORDS, 1)},
               **{w: n for n, w in enumerate(_TEENS, 10)}, **{w: n for n, w in enumerate(_TEEN_ORDS, 10)},
               "twenty": 20, "twentieth": 20, "thirty": 30, "thirtieth": 30}
_NUMBERS = frozenset([*_WORD_VALUE, *_TENS, *(w[:-1] + "ieth" for w in _TENS[:8]), "hundredth"])
_ORD_ALT, _ONE_ALT = "|".join(_ORDS), "|".join(_ONES)
_NUM_ALT = "|".join(_ONES + _TEENS + _TENS)
# Which alternative wins doesn't matter: a date must end at a word's end, so "seven" can't take "seventh".
_DAY_NTH = (rf"\d{{1,2}}(?:st|nd|rd|th)?|(?:twenty|thirty)[\s-]+(?:{_ORD_ALT})|twentieth|thirtieth|"
            rf"{'|'.join(_TEEN_ORDS)}|{_ORD_ALT}")
# A spoken plain number is a day only when no number follows it: "november nineteen fifty two" is a year.
_DAY_ANY = (rf"{_DAY_NTH}|(?:(?:twenty|thirty)[\s-]+(?:{_ONE_ALT})|twenty|thirty|{'|'.join(_TEENS)}|{_ONE_ALT})"
            rf"(?![\s-]+(?:{_NUM_ALT})\b)")
_DATE = re.compile(
    rf"(?:\b(?P<m1>{_MONTH})\.?(?:\s+the)?\s+(?P<d1>{_DAY_ANY})(?!\s+(?:years?|days?|weeks?|months?)\b)"  # November 7th
    rf"|\b(?:the\s+)?(?P<d2>{_DAY_NTH})\s+of\s+(?P<m2>{_MONTH})\b"  # the seventh of November
    rf"|\b(?:the\s+)?(?P<d3>\d{{1,2}}(?:st|nd|rd|th)?)\s+(?P<m3>{_MONTH})\b"  # 7 November
    rf"|(?<![\d/.:-])\b(?P<nm>\d{{1,2}})[/-](?P<nd>\d{{1,2}})(?:[/-](?:\d{{4}}|\d{{2}}))?)(?![\w/-])", re.I)
_YEAR_AFTER = re.compile(r"^,?\s*(?:1[89]|20)\d\d\b")
_WHATS = {"birthday": "birthday", "bday": "birthday", "b-day": "birthday", "birthdate": "birthday",
          "anniversary": "anniversary"}
_WORD = re.compile(rf"\b(?:{'|'.join(_WHATS)}|born|turn(?:s|ed|ing)?)\b", re.I)
_END = re.compile(r"(?<![.!?;])[.!?;]+(?=\s|$)|\n+")
_UNSURE = re.compile(
    r"\b(?:is\s+it|was\s+it|is\s+that|(?:is|was|are|does|did)n'?t|not\s+(?:sure|certain)|unsure|maybe|perhaps|possibly|"
    r"probably|might|i\s+(?:guess|wonder|forget)|forgot(?:ten)?|or|if|whether|"
    r"(?:don'?t|do\s+not|can'?t|cannot|can\s+not|couldn'?t|could\s+not)\s+(?:\w+\s+)?"
    r"(?:remember|recall|know|think|say))\b", re.I)
_TOKEN = re.compile(r"\d+(?:st|nd|rd|th)?|[^\W\d_][\w'-]*|[,:;]")
_POSS = re.compile(r"'s?$", re.I)
_GREAT = re.compile(r"\bgreat\s+(?=grand)", re.I)
_IN_LAW = re.compile(r"\b\s+in\s+law\b", re.I)
_REL = re.compile(
    r"(?:great-)?(?:step-?)?(?:son|daughter|child|kid|boy|girl|wife|husband|spouse|brother|sister|twin|mother|father|"
    r"mom|momma|mama|mommy|dad|daddy|papa|nephew|niece|aunt|auntie|uncle|cousin|grandson|granddaughter|grandchild|"
    r"grandkid|grandbaby|grandmother|grandfather|grandma|grandpa|granny|friend|neighbor|roommate|pastor|preacher)"
    r"(?:-in-law)?", re.I)
# All that may stand between "birthday" and its date.
_FILLER = frozenset("""is was are were will would be it's that's always actually also really just on in at falls fall
                       fell comes came coming up back , :""".split())
_LINKS = frozenset("is was were will would it's that's".split())  # "November 7 is Mark's birthday"
_NOT_THE_DAY = frozenset("of party dinner cake card present gift celebration lunch".split())  # "birthday party"
_MODIFIERS = frozenset("wedding marriage golden silver diamond ruby pearl next big upcoming".split())
_TURN = frozenset("turn turns turned turning be".split())
_TO_BE = frozenset("was were is got be being will going to gonna ,".split())
_OWNERS = frozenset("my our his her their your the a".split())
_FONDLY = frozenset("late oldest youngest eldest older younger middle baby little dear only sweet".split())
_NOT_WHO = frozenset("""
    i i'm me we we're us you he she it they them him hers theirs ours mine yours that this these those there here what
    who whose which when where how why let one someone somebody anyone anybody everyone everybody nobody today tomorrow
    yesterday tonight year years week weeks month months day days time last next each every all both and or but is was
    since after before until because so then now well yes oh ok okay also remember note tell please hey used had has
    would could did always never my our his her their your the a an
    church company store school town city county state country nation business shop restaurant facility hospital home
    club team war university college bank firm lodge parish department center village community society union
""".split())
_GONE_IS = r"(?:\b(?:is|are|was|were|been)\s+|(?<=')s\s+)"
_GONE = re.compile(
    r"\bpassed(?!\s+(?:his|her|their|your|my|our|the|a|an|me|him|them|us|it|that|this|out|by|through|over|up|down|"
    r"along|around|on\s+(?:the|a|my|to|it|that))\b)|\bdied\b|\bin\s+heaven\b|"
    r"\b(?:went|gone)\s+(?:home\s+)?to\s+(?:be\s+with\s+)?(?:the\s+lord|jesus|god|heaven|glory)\b|"
    rf"{_GONE_IS}(?:dead|with\s+the\s+lord)\b", re.I)
_LOST = re.compile(r"(?<!almost\s)(?<!nearly\s)\b(?:lost|buried)\s+|\b(?:my|our|his|her|their|the)\s+late\s+", re.I)
_WIDOW = re.compile(r"\bwidow(er|ed)?\b", re.I)
_SPOUSE_GONE = {"": ("husband",), "er": ("wife",), "ed": ("husband", "wife")}
_BEFORE_GONE = frozenset("has had have is was were are been just already recently both sadly finally who ,".split())
_NEARLY = frozenset("almost nearly never not could would should might may could've would've should've might've".split())
_STOP = re.compile(r"\b(?:(?:don'?t|do\s+not|never|stop|quit)\s+(?:you\s+)?(?:remind(?:ing)?\s+me\s+(?:about|of)|"
                   r"bring(?:ing)?\s+up)|no\s+more\s+reminders?\s+(?:about|of|for))\s+(.{1,40})", re.I)
_REMIND = re.compile(r"\b(?:go\s+ahead\s+and|you\s+can|you\s+may|it's\s+(?:ok|okay|fine|all\s+right)\s+to)\s+"
                     r"(?:remind\s+me\s+(?:about|of)|bring\s+up)\s+(.{1,40})", re.I)
_AFTER_WHO = frozenset("again anymore any please either ever up now today , : ;".split())
_PRONOUNS = frozenset("him her his them their it that those".split())
_CORRECTION = re.compile(
    r"\W*(?:no|nope|actually|wait|sorry|i\s+mean|it's|it\s+is|that's\s+wrong|that's\s+not\s+right)\b", re.I)
_LOOSE_DAY = re.compile(
    rf"(?<![\w/:.-])(?<!not\s)(?:the\s+(?P<word>{_DAY_NTH})|(?<!the\s)(?P<num>\d{{1,2}}(?:st|nd|rd|th)?))"
    r"(?=\s*(?:$|[.,!;]|not\b))", re.I)


def _plain(text):
    return str(text or "").replace("’", "'").replace("‘", "'")  # one letter for one, so spans still fit the text


def _tokens(text):
    """The words, with "son in law" and "great grandson" as one word. A comma is a token, since it breaks a name."""
    return _TOKEN.findall(_IN_LAW.sub("-in-law", _GREAT.sub("great-", text)))


def _base(token):
    return _POSS.sub("", token).lower()


def _is_num(token):
    token = token.lower()
    return token.rstrip("stndrh").isdigit() or all(part in _NUMBERS for part in token.split("-"))


def _show(name):
    """How a person is written: "mark" is "Mark", and a relation stays "son"."""
    if _REL.fullmatch(name):
        return name.lower()
    return re.sub(r"(?:^|(?<=[\s-]))[^\W\d_]", lambda letter: letter[0].upper(), name)


def _day_value(words):
    digits = re.match(r"\d+", words)
    return int(digits[0]) if digits else sum(_WORD_VALUE[w] for w in re.split(r"[\s-]+", words.lower()))


def _dates(text):
    """Every month and day in text, in order: (start, end, month, day, numeric). A day that can't be stays in, so it
    still cuts the sentence where it stands; parse skips it. A year after a spoken date stays out of the span, so a
    corrected day keeps the year."""
    out = []
    for hit in _DATE.finditer(text):
        if hit["nm"]:
            month, day = int(hit["nm"]), int(hit["nd"])
        else:
            month = _MONTH_OF[(hit["m1"] or hit["m2"] or hit["m3"])[:3].lower()]
            day = _day_value(hit["d1"] or hit["d2"] or hit["d3"])
        out.append((*hit.span(), month, day, bool(hit["nm"])))
    return out


def valid(month, day):
    """True for a day that can be: Feb 29 is, Nov 31 isn't."""
    return 1 <= month <= 12 and 1 <= day <= _MONTH_DAYS[month - 1]


def _sentences(text, dates):
    ends = [m.end() for m in _END.finditer(text) if not any(d[0] <= m.start() < d[1] for d in dates)]  # "Nov. 7"
    edges = [0, *ends]
    if edges[-1] < len(text):
        edges.append(len(text))
    return list(zip(edges, edges[1:]))


def _who(toks, what, subject=False, whole=False):
    """Whom the words ending at the last token name: (who, relation). who is "" for my/our anniversary and None for
    nobody to keep. subject: "Lily" counts as well as "Lily's". whole: every token must be part of the name."""
    toks = list(toks)
    while toks and (toks[-1].lower() in _MODIFIERS or _is_num(toks[-1])):
        toks.pop()
    if not toks:
        return None, ""
    word = toks.pop()
    if word.lower() in ("my", "our"):
        return ("" if what == "anniversary" and not (whole and toks) else None), ""
    name, low = _POSS.sub("", word), _base(word)
    if low in _NOT_WHO or not name[0].isalpha() or not (subject or _POSS.search(word)):
        return None, ""
    relation = low if _REL.fullmatch(low) else ""
    name = _show(name)
    if toks and not relation and name[0].isupper() and toks[-1][0].isupper() and not _POSS.search(toks[-1]) \
            and toks[-1].lower() not in _NOT_WHO and not _REL.fullmatch(toks[-1]):
        name = f"{toks.pop()} {name}"  # Mary Ann, Mark Smith
    if toks and not relation and _REL.fullmatch(toks[-1]):
        relation = toks.pop().lower()
    if toks and _POSS.search(toks[-1]) and _base(toks[-1]) not in _NOT_WHO:  # "Mark's wife" is his, not the resident's
        owner = _show(_POSS.sub("", toks.pop()))
        name, relation = (f"{owner}'s {name}", "") if relation == name else (name, "")
    while toks and toks[-1].lower() in _FONDLY:
        toks.pop()
    if toks and toks[-1].lower() == "the" and not relation:
        return None, ""  # "the church's": a person isn't "the" anything
    if toks and toks[-1].lower() in _OWNERS:
        toks.pop()
    if len(toks) > 1 and toks[-1].lower() == "and":
        first = _POSS.sub("", toks[-2])
        if first[0].isalpha() and first.lower() not in _NOT_WHO \
                and (what != "birthday" or first[0].isupper() or _REL.fullmatch(first)):
            del toks[-2:]
            name, relation = f"{_show(first)} and {name}", first.lower() if _REL.fullmatch(first) else ""
            if toks and _REL.fullmatch(toks[-1]):
                relation = toks.pop().lower()
    while toks and (toks[-1].lower() in _OWNERS or toks[-1].lower() in _FONDLY):
        toks.pop()
    return (None, "") if whole and toks else (name, relation)


def _before(left, carried):
    """For "Mark's birthday is": (what, who, relation) from the words before a date, or None."""
    toks = _tokens(left)
    while toks and toks[-1].lower() in _FILLER:
        toks.pop()
    if not toks:
        return None
    last = toks.pop()
    what = _WHATS.get(_base(last))
    if what:
        return (what, *_who(toks, what))
    if _is_num(last):  # "turns ten on": the same words come before "turns" as before "was born"
        while toks and _is_num(toks[-1]):
            toks.pop()
        if not toks or toks.pop().lower() not in _TURN:
            return None
        last = "born"
    if last.lower() == "born":
        while toks and toks[-1].lower() in _TO_BE:
            toks.pop()
        return ("birthday", *_who(toks, "birthday", subject=True))
    return (carried, *_who([*toks, last], carried)) if carried and _POSS.search(last) else None


def _after(right, carried):
    """For "November 7 is Mark's birthday": (what, who, relation) from the words after a date, or None."""
    toks = _tokens(_YEAR_AFTER.sub("", right, count=1))
    if toks and toks[0] == ",":  # "November 7, that's Mark's birthday"
        toks.pop(0)
    if not toks or toks[0].lower() not in _LINKS:
        return None
    while toks and toks[0].lower() in _FILLER:
        toks.pop(0)
    toks = toks[:8]
    for n, tok in enumerate(toks):
        what = _WHATS.get(_base(tok))
        if what:
            if n + 1 < len(toks) and toks[n + 1].lower() in _NOT_THE_DAY:
                return None
            return (what, *_who(toks[:n], what, whole=True))
    n = next((n for n, tok in enumerate(toks) if _POSS.search(tok)), None)
    return (carried, *_who(toks[:n + 1], carried, whole=True)) if carried and n is not None else None


def parse(text, self_name=""):
    """Every family date said plainly in text, as dicts: month, day, who (shown, "" only for their own anniversary),
    relation ("son" or ""), what ("birthday" or "anniversary"), span (of the date words in text). Nothing at all for a
    question, a doubt or a day that can't be. Never the resident's own birthday."""
    text = _plain(text)
    dates = _dates(text)
    spots = _sentences(text, dates) if dates else []
    self_words = set(str(self_name or "").casefold().split())
    found, what = [], ""  # what carries on, for "and Lily's is March 12"
    for i, (a, b) in enumerate(spots):
        tag = text[spots[i + 1][0]:spots[i + 1][1]] if i + 1 < len(spots) else ""  # "Right?" just after is doubt
        if "?" in text[a:b] or _UNSURE.search(text[a:b]) or ("?" in tag and len(tag.split()) <= 3):
            continue
        here = [d for d in dates if a <= d[0] < b]
        floor = a
        for n, (start, end, month, day, _) in enumerate(here):
            stop = here[n + 1][0] if n + 1 < len(here) else b
            hit = _before(text[floor:start], what)
            floor = end
            if not hit:
                hit = _after(text[end:stop], what)
                if hit:  # those words are used up, so the next date can't take them too
                    word = _WORD.search(text, end, stop)
                    floor = word.end() if word else stop
            if not hit:
                continue
            what, who, relation = hit
            mine = not relation and who and set(who.casefold().split()) <= self_words
            if who is not None and not mine and valid(month, day):
                found.append({"month": month, "day": day, "who": who, "relation": relation, "what": what,
                              "span": (start, end)})
    return found


def loose_dates(text):
    """Every month and day in text, in any spoken form, with no who needed. 3/4 counts only beside a birthday word."""
    text = _plain(text)
    plain_numbers = bool(_WORD.search(text))
    return {(m, d) for _, _, m, d, numeric in _dates(text) if valid(m, d) and (plain_numbers or not numeric)}


def loose_day(text):
    """The day in "no, it's the 9th" or "actually the ninth", or None. "No one came" and "9 o'clock" aren't days."""
    text = _plain(text)
    if "?" in text or _UNSURE.search(text):
        return None
    hit = _LOOSE_DAY.search(text)
    day = _day_value(hit["word"] or hit["num"]) if hit else 0
    return day if 1 <= day <= 31 else None


def is_correction(text):
    """True when these few words start like a correction."""
    text = _plain(text)
    return bool(_CORRECTION.match(text)) and len(text.split()) <= 10


def _named_after(toks, lower):
    """The people after "lost" or "my late": the relation, then the name. "lost Mark's wife" names the wife."""
    toks = toks[1:] if toks and toks[0].lower() in _OWNERS else toks
    names = []
    while toks:
        tok, toks = toks[0], toks[1:]
        base = _base(tok)
        if _POSS.search(tok) and toks and _REL.fullmatch(_POSS.sub("", toks[0])):
            continue
        if _REL.fullmatch(base):
            names.append(base)
            continue
        if tok[0].isalpha() and not _POSS.search(tok) and base not in _NOT_WHO and (tok[0].isupper() or lower):
            names.append(base)
        break
    return names


def passed(text):
    """The lower-case people these words say have died: names and relations, as ["husband", "bob"]. Leans toward naming,
    since wrongly staying quiet costs little."""
    text = _plain(text)
    names = []
    for hit in _GONE.finditer(text):
        toks = _tokens(text[max(0, hit.start() - 80):hit.start()])
        while toks and toks[-1].lower() in _BEFORE_GONE:
            toks.pop()
        if toks and toks[-1].lower() in _NEARLY:
            continue
        who, relation = _who(toks, "", subject=True)
        if who:
            names.append(relation)
            names += [one.split("'s ")[-1].lower() for one in who.split(" and ")]  # "Mark's wife": the wife
    lower = text.islower()  # speech with no capitals: any word might be a name
    for hit in _LOST.finditer(text):
        names += _named_after(_tokens(text[hit.end():hit.end() + 60]), lower)
    for hit in _WIDOW.finditer(text):
        names += _SPOUSE_GONE[(hit[1] or "").lower()]
    return list(dict.fromkeys(name for name in names if name))


def stop_request(text):
    """("stop", who) for "don't remind me about Mark", ("remind", who) for "you can remind me about Mark", or None.
    who is "" for a pronoun, and "anniversary" for their own."""
    text = _plain(text)
    for kind, pattern in (("stop", _STOP), ("remind", _REMIND)):
        hit = pattern.search(text)
        if hit:
            toks, what = _tokens(hit[1]), ""
            for n, tok in enumerate(toks):
                what = _WHATS.get(_base(tok), "")
                if what or tok.lower() in _AFTER_WHO:
                    toks = toks[:n]
                    break
            who = _who(toks, what, subject=True)[0]
            if who is None and not (len(toks) == 1 and toks[0].lower() in _PRONOUNS):
                return None  # "don't bring up the rent" is no one
            return kind, "anniversary" if who == "" else who or ""
    return None


def when(month, day):
    return f"{MONTH_NAMES[month - 1]} {day}"


def label(found):
    """A date in plain words: "Mark's birthday, November 7", "Your anniversary, June 3"."""
    found = dict(found)
    who, date_words = found["who"], when(found["month"], found["day"])
    if not who:
        return f"Your {found['what']}, {date_words}"
    yours = "Your " if _REL.fullmatch(_POSS.sub("", who.split()[0])) else ""
    return f"{yours}{who}'s {found['what']}, {date_words}"


def next_date(month, day, today):
    """The next time this date comes, on or after today. Feb 29 falls on Feb 28 in a year without one."""
    for year in (today.year, today.year + 1):
        on = date(year, month, min(day, monthrange(year, month)[1]))
        if on >= today:
            return on
    return on
