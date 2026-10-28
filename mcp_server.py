"""MCP server for the Care Incident Log, so Claude can read and update the log directly.

Stdlib only; speaks MCP (JSON-RPC 2.0, one message per line) over stdin/stdout.
Uses server.py's data path and rules, so it always sees the same log as the app.
Registered for Claude Code in .mcp.json.
"""
import contextlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server as tracker  # noqa: E402

INCIDENT_PROPS = {
    "occurred_date": {"type": "string", "description": "YYYY-MM-DD"},
    "occurred_time": {"type": "string", "description": "HH:MM 24-hour, or empty if unknown"},
    "category": {"type": "string", "enum": list(tracker.CATEGORIES)},
    "description": {"type": "string", "description": "What happened, in the resident's own words"},
    "severity": {"type": "string", "enum": ["minor", "serious", "dangerous"]},
    "wait_minutes": {"type": "integer"},
    "never_came": {"type": "boolean", "description": "No one ever came"},
    "staff_involved": {"type": "string"},
    "reported_to": {"type": "string"},
    "outcome": {"type": "string", "description": "What happened after"},
    "witnesses": {"type": "string"},
    "formal_summary": {"type": "string", "description": "1-2 neutral third-person sentences for the state report"},
}

TOOLS = [
    ("tracker_summary", "Totals for the incident log: all time, last 7 and 30 days, by category, "
     "times no one came, longest wait, and how many Andy Flow items are waiting.", {}, []),
    ("list_incidents", "List logged incidents, newest first.",
     {"date_from": {"type": "string"}, "date_to": {"type": "string"},
      "category": {"type": "string", "enum": list(tracker.CATEGORIES)},
      "limit": {"type": "integer", "default": 50}}, []),
    ("add_incident", "Log a new incident.", INCIDENT_PROPS, ["occurred_date", "category", "description"]),
    ("update_incident", "Change fields on an existing incident. Only the fields given are changed.",
     {"id": {"type": "integer"}, **INCIDENT_PROPS}, ["id"]),
    ("remove_incident", "Hide an incident from the log (kept in the file, recoverable).",
     {"id": {"type": "integer"}}, ["id"]),
    ("andy_flow_inbox", "Andy Flow dictations/notes starting with 'Incident' not yet added or dismissed, "
     "each with a best-guess structured incident.", {}, []),
    ("update_from_andy_flow", "Same as the app's 'Update from Andy Flow' button: log every new "
     "'Incident' dictation/note from Andy Flow in one go.", {}, []),
    ("dismiss_andy_flow_item", "Mark an Andy Flow inbox item as not an incident.",
     {"kind": {"type": "string", "enum": ["dictation", "note"]}, "source_id": {"type": "integer"}},
     ["kind", "source_id"]),
    ("search_andy_flow", "Search ALL of Andy's Andy Flow dictations and notes (not just 'Incident' ones), "
     "to find care problems he mentioned in passing. Read-only.",
     {"query": {"type": "string", "description": "Text to look for; empty returns the most recent"},
      "since": {"type": "string", "description": "YYYY-MM-DD; default 30 days ago"},
      "limit": {"type": "integer", "default": 30}}, []),
]


def summary(conn):
    rows = tracker.list_incidents(conn)
    today = datetime.now().date()
    within = lambda n: [r for r in rows if r["occurred_date"] >= str(today - timedelta(days=n - 1))]
    by_cat = {}
    for r in rows:
        by_cat[tracker.CATEGORIES[r["category"]]] = by_cat.get(tracker.CATEGORIES[r["category"]], 0) + 1
    return {
        "total": len(rows), "last_7_days": len(within(7)), "last_30_days": len(within(30)),
        "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
        "times_no_one_came": sum(r["never_came"] for r in rows),
        "longest_wait_minutes": max((r["wait_minutes"] or 0 for r in rows), default=0),
        "andy_flow_waiting": len(tracker.scan_andyflow(conn)["items"]),
    }


def search_andy_flow(query="", since="", limit=30):
    if not tracker.ANDYFLOW_DB.exists():
        return {"available": False, "items": []}
    since = since or str(datetime.now().date() - timedelta(days=30))
    like = f"%{query}%"
    af = sqlite3.connect(tracker.ANDYFLOW_DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        items = [{"kind": "dictation", "id": i, "at": at, "app": app, "text": t[:1500]} for i, at, app, t in af.execute(
            "SELECT id, timestamp, COALESCE(app_name, ''), COALESCE(text, '') FROM dictations "
            "WHERE timestamp >= ? AND text LIKE ? ORDER BY timestamp DESC LIMIT ?", (since, like, limit))]
        items += [{"kind": "note", "id": i, "at": at, "folder": f, "text": f"{ti}\n{b}".strip()[:1500]}
                  for i, at, ti, b, f in af.execute(
            "SELECT id, updated_at, COALESCE(title, ''), COALESCE(body, ''), folder FROM notes "
            "WHERE updated_at >= ? AND (title LIKE ? OR body LIKE ?) ORDER BY updated_at DESC LIMIT ?",
            (since, like, like, limit))]
    finally:
        af.close()
    items.sort(key=lambda i: i["at"], reverse=True)
    return {"available": True, "items": items[:limit]}


def _limit(value, default):
    # Clamp a requested row count to 1..500; anything unusable gets the default.
    try:
        return max(1, min(500, int(value)))
    except (TypeError, ValueError):
        return default


def call_tool(name, args):
    if not isinstance(args, dict):
        args = {}
    with tracker.connect() as conn:
        if name == "tracker_summary":
            return summary(conn)
        if name == "list_incidents":
            rows = tracker.list_incidents(conn, args.get("date_from", ""), args.get("date_to", ""))
            if args.get("category"):
                rows = [r for r in rows if r["category"] == args["category"]]
            return rows[:_limit(args.get("limit", 50), 50)]
        if name == "add_incident":
            row = tracker.clean_incident({**args, "source": "claude"})
            return {"id": tracker.insert_incident(conn, row)}
        if name == "update_incident":
            current = conn.execute("SELECT * FROM incidents WHERE id = ? AND deleted_at IS NULL",
                                   (args["id"],)).fetchone()
            if not current:
                raise ValueError(f"No incident with id {args['id']}.")
            row = tracker.clean_incident({**dict(current), **args})
            row.pop("source"), row.pop("source_id")
            row["updated_at"] = tracker.now()
            conn.execute(f"UPDATE incidents SET {', '.join(k + ' = ?' for k in row)} WHERE id = ?",
                         [*row.values(), args["id"]])
            return {"ok": True}
        if name == "remove_incident":
            cur = conn.execute("UPDATE incidents SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                               (tracker.now(), args["id"]))
            if cur.rowcount == 0:
                raise ValueError(f"No incident with id {args['id']}.")
            return {"ok": True}
        if name == "andy_flow_inbox":
            return tracker.scan_andyflow(conn)
        if name == "update_from_andy_flow":
            return tracker.import_andyflow(conn)
        if name == "dismiss_andy_flow_item":
            tracker.mark_seen(conn, args["kind"], args["source_id"], "dismissed")
            return {"ok": True}
    if name == "search_andy_flow":
        return search_andy_flow(args.get("query", ""), args.get("since", ""), _limit(args.get("limit", 30), 30))
    raise ValueError(f"Unknown tool: {name}")


def handle(msg):
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "care-incident-log", "version": "0.1.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d,
                           "inputSchema": {"type": "object", "properties": p, "required": r}}
                          for n, d, p, r in TOOLS]}
    if method == "tools/call":
        try:
            result = call_tool(params["name"], params.get("arguments") or {})
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
    raise LookupError(method)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    with contextlib.redirect_stdout(sys.stderr):  # stdout is reserved for protocol messages
        tracker.init_db()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue  # not JSON: skip the bad line rather than stop the server
        if not isinstance(msg, dict) or "id" not in msg:
            continue  # notifications (e.g. notifications/initialized) need no reply
        try:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
        except LookupError:
            reply = {"jsonrpc": "2.0", "id": msg["id"],
                     "error": {"code": -32601, "message": f"Method not found: {msg.get('method')}"}}
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
