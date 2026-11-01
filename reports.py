"""Formal "Resident Care Incident Record" for the state survey agency or the ombudsman.

The same record is produced two ways from the incident log:
  build_xlsx(...)         -> bytes of a spreadsheet (openpyxl)
  build_report_html(...)  -> a standalone, printable page

Both take `rows` (dicts as returned by server.list_incidents), `settings` (dict from
server.get_settings; only the resident/facility keys are ever read) and the reporting
period. This module does not import server.py (server imports it lazily).
"""
import html
import io
import re
from datetime import datetime
from types import SimpleNamespace

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.page import PageMargins
    from openpyxl.worksheet.properties import PageSetupProperties
except ImportError:  # the printable page still works without openpyxl
    Workbook = None

TITLE = "Resident Care Incident Record"
SUBTITLE = "Care deficiencies reported by the resident"
FOOTNOTE = ("Regulatory references (42 CFR Part 483; CMS State Operations Manual Appendix PP) "
            "are provided for reference. Determinations are made by the state survey agency.")
ATTESTATION = ("declare that each entry in this record was written by me at the time shown under "
               "'Logged at', and that it is true and accurate to the best of my knowledge.")
PATTERN_NOTE = "repeated failure — possible neglect"
SIGNIFICANT_NOTE = "if the error was significant"
PATTERN_MIN = 3

# Same keys as server.CATEGORIES (not imported: running `python server.py` makes it __main__).
CATEGORY_LABELS = {
    "call_light": "Call light not answered",
    "meal": "Meal missed or late",
    "bathing": "Bath or shower missed",
    "toileting": "Toileting / brief change",
    "medication": "Medication problem",
    "repositioning": "Not turned or repositioned",
    "staff": "Staff conduct",
    "safety": "Fall, injury or safety",
    "other": "Something else",
}

# CMS F-tags (42 CFR Part 483, State Operations Manual Appendix PP).
REGULATIONS = {
    "F725": {"title": "Sufficient Nursing Staff", "cite": "§483.35(a)(1)-(2)"},
    "F919": {"title": "Resident Call System", "cite": "§483.90(g)(1)-(2)"},
    "F809": {"title": "Frequency of Meals/Snacks at Bedtime", "cite": "§483.60(f)(1)-(3)"},
    "F692": {"title": "Nutrition/Hydration Status Maintenance", "cite": "§483.25(g)(1)-(3)"},
    "F677": {"title": "ADL Care Provided for Dependent Residents", "cite": "§483.24(a)(2)"},
    "F561": {"title": "Self Determination", "cite": "§483.10(f)(1)-(3),(8)"},
    "F690": {"title": "Bowel/Bladder Incontinence, Catheter, UTI", "cite": "§483.25(e)(1)-(3)"},
    "F760": {"title": "Residents Are Free of Significant Med Errors", "cite": "§483.45(f)(2)"},
    "F686": {"title": "Treatment/Svcs to Prevent/Heal Pressure Ulcers", "cite": "§483.25(b)(1)(i)-(ii)"},
    "F600": {"title": "Free from Abuse and Neglect", "cite": "§483.12, §483.12(a)(1)"},
    "F550": {"title": "Resident Rights/Exercise of Rights", "cite": "§483.10(a)(1)-(2),(b)(1)-(2)"},
    "F689": {"title": "Free of Accident Hazards/Supervision/Devices", "cite": "§483.25(d)(1)-(2)"},
}


def _rx(pattern):
    return re.compile(pattern, re.I)


# category -> (tags always implicated, [(tag, regex on description + formal_summary), ...])
_RULES = {
    "call_light": (("F725",), [
        ("F919", _rx(r"broken|not working|can['’]t reach|out of reach|unplugged|no call light"))]),
    "meal": (("F809",), [
        ("F677", _rx(r"\bhelp(?:ed|ing)?\s+(?:me\s+)?eat|\bfeed")),
        ("F692", _rx(r"weight|dehydrat|not eating|starv|thirst"))]),
    "bathing": (("F677",), [
        ("F561", _rx(r"schedule|my choice|when I (?:want|asked)"))]),
    "toileting": (("F690", "F677"), []),
    "medication": (("F760",), []),
    "repositioning": (("F686",), []),
    "staff": (("F550",), [
        ("F600", _rx(r"\b(?:rough|hit|grab|shov|push|slap|pinch|abus|threat|scream|yell|curs|cuss)"))]),
    "safety": (("F689",), []),
    "other": ((), []),
}


# ---------------------------------------------------------------- regulations

def is_pattern(incident, period_rows):
    """This app's own rule, not CMS's: 3 or more incidents of one category in the period count as a pattern.
    ("Something else" is a catch-all, not one kind of failure, so it never counts as a pattern.)"""
    cat = incident.get("category")
    if cat == "other":
        return False
    return sum(1 for r in period_rows if r.get("category") == cat) >= PATTERN_MIN


def _pattern_categories(rows):
    counts = {}
    for r in rows:
        counts[r.get("category")] = counts.get(r.get("category"), 0) + 1
    return {c for c, n in counts.items() if n >= PATTERN_MIN and c != "other"}


def _tags(incident, pattern):
    text = f"{incident.get('description') or ''} {incident.get('formal_summary') or ''}"
    base, extra = _RULES.get(incident.get("category") or "", ((), []))
    tags = list(base)
    for tag, rx in extra:
        if tag not in tags and rx.search(text):
            tags.append(tag)
    if pattern and "F600" not in tags:
        tags.append("F600")
    return tags


def regs_for(incident, period_rows):
    """F-tag codes implicated by one incident, given every incident in the reporting period."""
    return _tags(incident, is_pattern(incident, period_rows))


def _describe(tags, pattern=False):
    """'F809, F600 (repeated failure -- possible neglect), F760 (if the error was significant)'."""
    notes = {"F760": SIGNIFICANT_NOTE}
    if pattern:
        notes["F600"] = PATTERN_NOTE
    return ", ".join(f"{t} ({notes[t]})" if t in notes else t for t in tags)


# ---------------------------------------------------------------- shared content

def record_no(incident):
    year = str(incident.get("logged_at") or "")[:4]
    if not year.isdigit():
        year = str(incident.get("occurred_date") or "")[:4]
    if not year.isdigit():
        year = "0000"
    return f"INC-{year}-{int(incident.get('id') or 0):04d}"


def _minutes(n):
    return f"{n} minute" + ("" if n == 1 else "s")


_SUMMARY_BASE = {
    "call_light": "Resident reports the call light was not answered",
    "meal": "Resident reports a missed or late meal",
    "bathing": "Resident reports a missed bath or shower",
    "toileting": "Resident reports a delay or failure in toileting assistance or a brief change",
    "medication": "Resident reports a medication problem",
    "repositioning": "Resident reports not being turned or repositioned",
    "staff": "Resident reports a concern about staff conduct",
    "safety": "Resident reports a fall, injury or safety incident",
    "other": "Resident reports a care concern",
}


def helped_note(incident):
    """M18 piece 5: the one wording of the line that says the companion helped fill in the form. Empty when she didn't.
    It stands apart from the statement, which stays the resident's exact words."""
    who = {"mary": "Mary", "sam": "Sam"}.get(incident.get("helped_by") or "")
    return f"Filled in with {who}'s help" if who else ""


def summary_for(incident):
    """The formal summary if one was saved, otherwise a neutral third-person sentence."""
    saved = (incident.get("formal_summary") or "").strip()
    if saved:
        return saved
    cat = incident.get("category")
    base = _SUMMARY_BASE.get(cat, "Resident reports a care concern")
    wait = incident.get("wait_minutes")
    parts = []
    if cat == "call_light":
        parts.append(base + (f" for {_minutes(wait)}." if wait else "."))
    else:
        parts.append(base + ".")
        if wait:
            parts.append(f"Resident waited {_minutes(wait)}.")
    if incident.get("never_came"):
        parts.append("No staff member came.")
    return " ".join(parts)


def _logged_display(value):
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)", str(value or ""))
    return f"{m.group(1)} {m.group(2)}" if m else str(value or "")


def _period(date_from, date_to, rows):
    f, t = (date_from or "").strip(), (date_to or "").strip()
    if f and t:
        return f"{f} to {t}"
    if f:
        return f"From {f}"
    if t:
        return f"Up to {t}"
    dates = sorted(r.get("occurred_date") for r in rows if r.get("occurred_date"))
    return f"All recorded dates ({dates[0]} to {dates[-1]})" if dates else "All recorded dates"


def _prepare(rows, settings, date_from, date_to):
    settings = settings or {}
    rows = sorted(rows, key=lambda r: (r.get("occurred_date") or "", r.get("occurred_time") or "",
                                       r.get("id") or 0))
    pcats = _pattern_categories(rows)

    def setting(key):
        return str(settings.get(key) or "").strip()

    out, by_cat, tag_counts = [], {}, {}
    for r in rows:
        cat = r.get("category") or ""
        pattern = cat in pcats
        tags = _tags(r, pattern)
        sev = (r.get("severity") or "minor").lower()
        wait = r.get("wait_minutes")
        out.append({
            "record_no": record_no(r),
            "date": r.get("occurred_date") or "",
            "time": r.get("occurred_time") or "",
            "category": CATEGORY_LABELS.get(cat, cat),
            "summary": summary_for(r),
            "statement": "“" + (r.get("description") or "").strip() + "”",
            "wait": wait if isinstance(wait, int) and wait > 0 else None,
            "never": bool(r.get("never_came")),
            "sev_key": sev,
            "severity": sev.capitalize(),
            "staff": r.get("staff_involved") or "",
            "reported": r.get("reported_to") or "",
            "outcome": r.get("outcome") or "",
            "tags": tags,
            "regs": _describe(tags, pattern),
            "logged": _logged_display(r.get("logged_at")),
            "helped": helped_note(r),
        })
        entry = by_cat.setdefault(cat, {"count": 0, "tags": [], "pattern": pattern})
        entry["count"] += 1
        for t in tags:
            if t not in entry["tags"]:
                entry["tags"].append(t)
            tag_counts[t] = tag_counts.get(t, 0) + 1

    order = [c for c in CATEGORY_LABELS if c in by_cat] + [c for c in by_cat if c not in CATEGORY_LABELS]
    summary = []
    for c in order:
        e = by_cat[c]
        tags = sorted(e["tags"], key=lambda t: list(REGULATIONS).index(t) if t in REGULATIONS else 99)
        summary.append((CATEGORY_LABELS.get(c, c), e["count"], _describe(tags, e["pattern"]) or "None"))

    never = sum(1 for r in rows if r.get("never_came"))
    name = setting("resident_name")
    header = [
        ("Resident", name or "Not provided"),
        ("Room", setting("room") or "Not provided"),
        ("Facility", setting("facility") or "Not provided"),
        ("Facility address", setting("facility_address") or "Not provided"),
        ("State", setting("state") or "Not provided"),
        ("Reporting period", _period(date_from, date_to, rows)),
        ("Date prepared", datetime.now().strftime("%Y-%m-%d")),
        ("Total incidents", str(len(rows))),
        ("Times no staff came", str(never)),
    ]
    used = [(t, REGULATIONS[t]["title"], REGULATIONS[t]["cite"], tag_counts[t])
            for t in REGULATIONS if t in tag_counts]
    return {"resident": name, "header": header, "rows": out, "summary": summary,
            "total": len(rows), "tags": used,
            "attest": f"I, {name or '______'}, {ATTESTATION}"}


# ---------------------------------------------------------------- XLSX

NAVY = "1F2A44"
COLUMNS = [("Record No.", 14), ("Date", 11), ("Time", 7), ("Category", 18), ("Summary", 36),
           ("Resident's statement", 42), ("Wait", 9), ("No staff came", 9), ("Severity", 10),
           ("Staff involved", 16), ("Reported to", 16), ("Outcome", 22), ("Regulations", 24),
           ("Logged at", 17), ("Help filling it in", 18)]
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _styles():
    side = Side(style="thin", color="595959")
    return SimpleNamespace(
        line=Side(style="thin", color="000000"),
        border=Border(left=side, right=side, top=side, bottom=side),
        title=Font(name="Calibri", size=16, bold=True, color=NAVY),
        sub=Font(name="Calibri", size=11, italic=True, color="404040"),
        head=Font(name="Calibri", size=10, bold=True, color="FFFFFF"),
        body=Font(name="Calibri", size=10),
        bold=Font(name="Calibri", size=10, bold=True),
        h2=Font(name="Calibri", size=11, bold=True, color=NAVY),
        note=Font(name="Calibri", size=9, italic=True, color="404040"),
        navy=PatternFill("solid", start_color=NAVY, end_color=NAVY),
        label=PatternFill("solid", start_color="E7E9EE", end_color="E7E9EE"),
        sev={"dangerous": PatternFill("solid", start_color="F8CBCB", end_color="F8CBCB"),
             "serious": PatternFill("solid", start_color="FCE0B8", end_color="FCE0B8")},
        top=Alignment(wrap_text=True, vertical="top", horizontal="left"),
        top_c=Alignment(wrap_text=True, vertical="top", horizontal="center"),
        mid=Alignment(wrap_text=True, vertical="center", horizontal="left"),
        mid_r=Alignment(wrap_text=True, vertical="center", horizontal="right"),
        mid_c=Alignment(wrap_text=True, vertical="center", horizontal="center"),
    )


def _put(ws, row, col, value, font=None, fill=None, align=None, border=None, fmt=None):
    c = ws.cell(row=row, column=col)
    if isinstance(value, str):
        value = _ILLEGAL.sub("", value)
        c.value = value
        if value.startswith("="):  # the resident's words are text, never a formula
            c.data_type = "s"
    else:
        c.value = value
    if font:
        c.font = font
    if fill:
        c.fill = fill
    if align:
        c.alignment = align
    if border:
        c.border = border
    if fmt:
        c.number_format = fmt
    return c


def _merge(ws, row, c1, c2, value, **style):
    for col in range(c1, c2 + 1):
        _put(ws, row, col, value if col == c1 else None, **style)
    if c2 > c1:
        ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)


def _lines(text, width):
    cap = max(1, int(width))
    return sum(max(1, -(-len(p) // cap)) for p in str(text or "").split("\n"))


def _setup_print(ws, title_rows=None):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.6)
    ws.print_options.horizontalCentered = True
    ws.oddFooter.center.text = "Page &P of &N"
    ws.oddFooter.center.size = 9
    if title_rows:
        ws.print_title_rows = title_rows


def _title_rows(ws, s, ncols, sub=SUBTITLE):
    _merge(ws, 1, 1, ncols, TITLE, font=s.title, align=s.mid_c)
    ws.row_dimensions[1].height = 28
    _merge(ws, 2, 1, ncols, sub, font=s.sub, align=s.mid_c)
    ws.row_dimensions[2].height = 18


def _table_head(ws, s, row, names, start=1):
    for i, name in enumerate(names):
        _put(ws, row, start + i, name, font=s.head, fill=s.navy, align=s.mid_c, border=s.border)
    ws.row_dimensions[row].height = 30


def _sheet_record(ws, d, s):
    ws.title = "Incident Record"
    n = len(COLUMNS)
    widths = [w for _, w in COLUMNS]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    _title_rows(ws, s, n)

    # Header block: three label/value pairs per row, merged across the table's columns.
    spans = [((1, 2), (3, 5)), ((6, 6), (7, 10)), ((11, 12), (13, 14))]
    for i, (label, value) in enumerate(d["header"]):
        r = 3 + i // 3
        (l1, l2), (v1, v2) = spans[i % 3]
        _merge(ws, r, l1, l2, label, font=s.bold, fill=s.label, align=s.mid, border=s.border)
        _merge(ws, r, v1, v2, value, font=s.body, align=s.mid, border=s.border)
        need = _lines(value, sum(widths[v1 - 1:v2])) * 13 + 7
        ws.row_dimensions[r].height = max(ws.row_dimensions[r].height or 20, need)
    ws.row_dimensions[6].height = 8

    hdr = 7
    _table_head(ws, s, hdr, [name for name, _ in COLUMNS])
    last = hdr
    for i, r in enumerate(d["rows"]):
        row = last = hdr + 1 + i
        values = [r["record_no"], r["date"], r["time"], r["category"], r["summary"], r["statement"],
                  r["wait"], "Yes" if r["never"] else "No", r["severity"], r["staff"], r["reported"],
                  r["outcome"], r["regs"], r["logged"], r["helped"]]
        centered = {1, 2, 6, 7, 8}  # Date, Time, Wait, No staff came, Severity
        height = 1
        for j, v in enumerate(values):
            _put(ws, row, j + 1, v, font=s.bold if j == 8 and r["sev_key"] != "minor" else s.body,
                 fill=s.sev.get(r["sev_key"]) if j == 8 else None,
                 align=s.top_c if j in centered else s.top,
                 border=s.border, fmt='0" min"' if j == 6 else None)
            if isinstance(v, str):
                height = max(height, _lines(v, widths[j]))
        ws.row_dimensions[row].height = min(409, height * 13 + 5)
    ws.freeze_panes = f"A{hdr + 1}"
    ws.auto_filter.ref = f"A{hdr}:{get_column_letter(n)}{last}"

    row = last + 2
    _merge(ws, row, 1, n, "Resident's attestation", font=s.h2, align=s.mid)
    _merge(ws, row + 1, 1, n, d["attest"], font=s.body, align=s.top)
    ws.row_dimensions[row + 1].height = 32
    row += 3
    for label in ("Signature of resident", "Witness signature (optional)"):
        _merge(ws, row, 1, 3, label, font=s.bold, align=s.mid)
        _merge(ws, row, 4, 5, None, border=Border(bottom=s.line))
        _put(ws, row, 6, "Date", font=s.bold, align=s.mid_r)
        _merge(ws, row, 7, 9, None, border=Border(bottom=s.line))
        ws.row_dimensions[row].height = 34
        row += 1
    _merge(ws, row + 1, 1, n, FOOTNOTE, font=s.note, align=s.top)
    ws.row_dimensions[row + 1].height = 28
    _setup_print(ws, f"{hdr}:{hdr}")


def _header_block(ws, s, d, row, vspan):
    for label, value in d["header"]:
        _put(ws, row, 1, label, font=s.bold, fill=s.label, align=s.mid, border=s.border)
        _merge(ws, row, 2, 3, value, font=s.body, align=s.mid, border=s.border)
        ws.row_dimensions[row].height = max(20, _lines(value, vspan) * 13 + 7)
        row += 1
    return row


def _sheet_summary(ws, d, s):
    ws.title = "Summary"
    widths = [34, 18, 74]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    _title_rows(ws, s, 3)
    row = _header_block(ws, s, d, 4, widths[1] + widths[2]) + 1
    _merge(ws, row, 1, 3, "Summary by category", font=s.h2, align=s.mid)
    row += 1
    _table_head(ws, s, row, ["Category", "Number of incidents", "Regulations implicated"])
    for label, count, regs in d["summary"]:
        row += 1
        _put(ws, row, 1, label, font=s.body, align=s.top, border=s.border)
        _put(ws, row, 2, count, font=s.body, align=s.top_c, border=s.border)
        _put(ws, row, 3, regs, font=s.body, align=s.top, border=s.border)
        ws.row_dimensions[row].height = max(18, _lines(regs, widths[2]) * 13 + 5)
    row += 1
    _put(ws, row, 1, "Total", font=s.bold, fill=s.label, align=s.top, border=s.border)
    _put(ws, row, 2, d["total"], font=s.bold, fill=s.label, align=s.top_c, border=s.border)
    _put(ws, row, 3, None, fill=s.label, border=s.border)
    _merge(ws, row + 2, 1, 3, FOOTNOTE, font=s.note, align=s.top)
    ws.row_dimensions[row + 2].height = 28
    _setup_print(ws)


def _sheet_regs(ws, d, s):
    ws.title = "Regulations"
    widths = [10, 56, 30, 12]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    _title_rows(ws, s, 4, "Regulations referenced in this record")
    _table_head(ws, s, 4, ["Tag", "Title", "Citation (42 CFR)", "Incidents"])
    row = 4
    for tag, title, cite, count in d["tags"]:
        row += 1
        for col, v in enumerate((tag, title, cite, count), 1):
            _put(ws, row, col, v, font=s.bold if col == 1 else s.body,
                 align=s.top_c if col in (1, 4) else s.top, border=s.border)
        ws.row_dimensions[row].height = max(18, _lines(title, widths[1]) * 13 + 5)
    if not d["tags"]:
        _merge(ws, 5, 1, 4, "No regulations are implicated by the incidents in this period.",
               font=s.body, align=s.mid, border=s.border)
        row = 5
    _merge(ws, row + 2, 1, 4, FOOTNOTE, font=s.note, align=s.top)
    ws.row_dimensions[row + 2].height = 28
    _setup_print(ws, "4:4")


def build_xlsx(rows, settings, date_from="", date_to=""):
    """The record as an .xlsx workbook (bytes): Incident Record, Summary, Regulations."""
    if Workbook is None:
        raise RuntimeError("The openpyxl package is not installed.")
    d = _prepare(rows, settings, date_from, date_to)
    s = _styles()
    wb = Workbook()
    wb.properties.title = TITLE
    wb.properties.subject = SUBTITLE
    wb.properties.creator = _ILLEGAL.sub("", d["resident"]) or "Resident"
    wb.properties.lastModifiedBy = wb.properties.creator
    _sheet_record(wb.active, d, s)
    _sheet_summary(wb.create_sheet(), d, s)
    _sheet_regs(wb.create_sheet(), d, s)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- printable page

def _esc(value):
    return html.escape(str(value if value is not None else ""), quote=False)


def _attr(value):
    return html.escape(str(value if value is not None else ""), quote=True)


_CSS = r"""
@page { size: landscape; margin: 0.6in 0.5in 0.75in 0.5in;
  @bottom-center { content: "Resident Care Incident Record \2014  Page " counter(page) " of " counter(pages);
                   font: 9pt Georgia, "Times New Roman", serif; color: #000; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 32px; background: #fff; color: #000;
       font: 11pt/1.35 Georgia, "Times New Roman", Times, serif; }
h1, h2 { font-family: Georgia, "Times New Roman", Times, serif; margin: 0; }
h1 { font-size: 22pt; text-align: center; letter-spacing: .02em; }
.sub { text-align: center; font-style: italic; font-size: 12pt; margin: 2px 0 8px; }
.rule { border: 0; border-top: 3px double #000; margin: 6px 0 14px; }
h2 { font-size: 13pt; margin: 20px 0 6px; padding-bottom: 2px; border-bottom: 1px solid #000; break-after: avoid; }
.toolbar { display: flex; gap: 14px; align-items: center; margin: 0 0 16px; font: 10pt Arial, Helvetica, sans-serif; }
.toolbar button { font: bold 10pt Arial, Helvetica, sans-serif; padding: 7px 14px; background: #fff;
                  color: #000; border: 1px solid #000; cursor: pointer; }
.toolbar button:hover { background: #eee; }
dl.meta { display: grid; grid-template-columns: repeat(3, 1fr); margin: 0;
          border-top: 1px solid #000; border-left: 1px solid #000; }
dl.meta > div { padding: 4px 8px; border-right: 1px solid #000; border-bottom: 1px solid #000; }
dl.meta dt { font-size: 8pt; text-transform: uppercase; letter-spacing: .06em; }
dl.meta dd { margin: 1px 0 0; font-size: 11pt; font-weight: bold; overflow-wrap: anywhere; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #000; padding: 3px 6px; vertical-align: top; text-align: left; overflow-wrap: anywhere; }
th { border-bottom: 2px solid #000; font-weight: bold; background: #fff; }
thead { display: table-header-group; }
tr { break-inside: avoid; page-break-inside: avoid; }
td.num { text-align: center; }
.nw { white-space: nowrap; }
.rec { table-layout: fixed; font-size: 8.5pt; }
.rec th { font-size: 8pt; }
.stmt { white-space: pre-line; font-style: italic; }
.sev-serious { font-weight: bold; }
.sev-dangerous { font-weight: bold; text-transform: uppercase; }
.empty { text-align: center; font-style: italic; padding: 10px; }
.attest { break-inside: avoid; page-break-inside: avoid; }
.attest p { margin: 8px 0; font-size: 11pt; }
.fill { display: inline-block; min-width: 14em; border-bottom: 1px solid #000; padding: 0 6px; text-align: center; }
.sig { display: flex; gap: 40px; margin-top: 36px; }
.sig .line { border-top: 1px solid #000; padding-top: 3px; font-size: 9.5pt; }
.sig .long { flex: 3; }
.sig .short { flex: 1; }
.foot { margin-top: 18px; font-size: 9pt; font-style: italic; }
@media screen { .backbar button { font: bold 22px Arial, Helvetica, sans-serif; min-height: 64px; padding: 8px 30px; margin: 0 0 14px;
  background: #fff; border: 3px solid #000; border-radius: 12px; cursor: pointer; } }
@media screen { .scroll { overflow-x: auto; } .rec { min-width: 1300px; } }
@media print {
  .noprint { display: none !important; }
  body { padding: 0; font-size: 10pt; }
  .rec { font-size: 7.5pt; } .rec th { font-size: 7pt; }
  h1 { font-size: 20pt; }
}
"""

_REC_WIDTHS = [7, 6, 3.5, 6, 11, 15, 3.5, 4, 4.5, 6, 6, 7, 9, 6.5, 5]


def build_report_html(rows, settings, date_from="", date_to=""):
    """A standalone printable page (no external resources) carrying the same record."""
    d = _prepare(rows, settings, date_from, date_to)

    meta = "".join(f"<div><dt>{_esc(k)}</dt><dd>{_esc(v)}</dd></div>" for k, v in d["header"])

    if d["summary"]:
        summary_rows = "".join(
            f'<tr><td>{_esc(c)}</td><td class="num">{n}</td><td>{_esc(regs)}</td></tr>'
            for c, n, regs in d["summary"])
        summary_rows += f'<tr><th>Total</th><th class="num">{d["total"]}</th><th></th></tr>'
    else:
        summary_rows = '<tr><td colspan="3" class="empty">No incidents recorded in this period.</td></tr>'

    colgroup = "".join(f'<col style="width:{w}%">' for w in _REC_WIDTHS)
    heads = "".join(f"<th>{_esc(name)}</th>" for name, _ in COLUMNS)
    body = []
    for r in d["rows"]:
        regs = _esc(r["regs"]) if r["regs"] else "None"
        body.append(
            "<tr>"
            f'<td class="nw">{_esc(r["record_no"])}</td>'
            f'<td class="nw">{_esc(r["date"])}</td>'
            f'<td>{_esc(r["time"])}</td>'
            f'<td>{_esc(r["category"])}</td>'
            f'<td>{_esc(r["summary"])}</td>'
            f'<td class="stmt">{_esc(r["statement"])}</td>'
            f'<td class="num">{_esc(str(r["wait"]) + " min") if r["wait"] else "&mdash;"}</td>'
            f'<td class="num">{"Yes" if r["never"] else "No"}</td>'
            f'<td class="sev-{_attr(r["sev_key"])}">{_esc(r["severity"])}</td>'
            f'<td>{_esc(r["staff"])}</td>'
            f'<td>{_esc(r["reported"])}</td>'
            f'<td>{_esc(r["outcome"])}</td>'
            f'<td>{regs}</td>'
            f'<td>{_esc(r["logged"])}</td>'
            f'<td>{_esc(r["helped"])}</td>'
            "</tr>")
    if not body:
        body.append(f'<tr><td colspan="{len(COLUMNS)}" class="empty">No incidents recorded in this period.</td></tr>')

    if d["tags"]:
        reg_rows = "".join(
            f'<tr><td class="nw"><b>{_esc(t)}</b></td><td>{_esc(title)}</td><td>42 CFR {_esc(cite)}</td></tr>'
            for t, title, cite, _ in d["tags"])
    else:
        reg_rows = '<tr><td colspan="3" class="empty">No regulations are implicated by the incidents in this period.</td></tr>'

    name_html = f'<span class="fill">{_esc(d["resident"])}</span>' if d["resident"] else '<span class="fill">&nbsp;</span>'
    attest = f"I, {name_html}, {_esc(ATTESTATION)}"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(TITLE)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="backbar noprint"><button type="button" id="reportBack" onclick="if(history.length>1){{history.back()}}else{{location.href='/'}}">Back</button></div>
<div class="toolbar noprint">
  <button type="button" onclick="window.print()">Print or save as PDF</button>
  <span>Choose &ldquo;Save as PDF&rdquo; as the destination to keep a copy. Landscape paper is set for you.</span>
</div>
<h1>{_esc(TITLE)}</h1>
<p class="sub">{_esc(SUBTITLE)}</p>
<hr class="rule">
<dl class="meta">{meta}</dl>

<h2>Summary by category</h2>
<table>
<thead><tr><th>Category</th><th class="num">Number of incidents</th><th>Regulations implicated</th></tr></thead>
<tbody>{summary_rows}</tbody>
</table>

<h2>Incident record</h2>
<div class="scroll">
<table class="rec">
<colgroup>{colgroup}</colgroup>
<thead><tr>{heads}</tr></thead>
<tbody>
{chr(10).join(body)}
</tbody>
</table>
</div>

<section class="attest">
<h2>Resident&rsquo;s attestation</h2>
<p>{attest}</p>
<div class="sig"><div class="line long">Signature of resident</div><div class="line short">Date</div></div>
<div class="sig"><div class="line long">Witness signature (optional)</div><div class="line short">Date</div></div>
</section>

<h2>Regulations referenced</h2>
<table>
<thead><tr><th>Tag</th><th>Title</th><th>Citation</th></tr></thead>
<tbody>{reg_rows}</tbody>
</table>
<p class="foot">{_esc(FOOTNOTE)}</p>
</body>
</html>
"""
