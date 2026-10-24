"""Optional Gemini "smart helper": tidy a spoken report and pull out the facts.

Off unless the resident turns it on and adds their own free Gemini API key.
server.py falls back to its offline guesser whenever this raises.
"""
import json
import urllib.request

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.5-flash-lite"

PROMPT = """You help a nursing-home resident write down a problem with their care.
You get what they said in their own words; it may be messy speech-to-text.
Never add facts they did not say. Return JSON with:
- description: their account in first person, tidied (punctuation, filler words and false starts removed), keeping their words and meaning.
- formal_summary: one or two sentences in neutral third person, as in an official complaint to a state agency, e.g. "Resident reports that the evening meal was not delivered and no staff member offered a meal before the kitchen closed."
- category: one of {categories}
- severity: "minor" (annoying, no harm), "serious" (caused hunger, pain, distress, or being left soiled or wet), or "dangerous" (could have caused injury or illness)
- wait_minutes: how long they waited, only if they said; otherwise null
- never_came: true only if no one ever came
- occurred_time: "HH:MM" 24-hour only if they said when it happened; otherwise ""
- staff_involved, reported_to, outcome: only if they said; otherwise ""
"""


def structure(text, api_key, categories, model=""):
    """Returns a dict with the fields described in PROMPT. Raises on any network/API/format problem."""
    string = {"type": "STRING"}
    schema = {
        "type": "OBJECT",
        "properties": {
            "description": string, "formal_summary": string,
            "category": {"type": "STRING", "enum": list(categories)},
            "severity": {"type": "STRING", "enum": ["minor", "serious", "dangerous"]},
            "wait_minutes": {"type": "INTEGER", "nullable": True},
            "never_came": {"type": "BOOLEAN"},
            "occurred_time": string, "staff_involved": string, "reported_to": string, "outcome": string,
        },
        "required": ["description", "formal_summary", "category", "severity", "never_came"],
    }
    body = {
        "systemInstruction": {"parts": [{"text": PROMPT.format(categories=", ".join(categories))}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "responseSchema": schema},
    }
    req = urllib.request.Request(
        ENDPOINT.format(model=model or DEFAULT_MODEL), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)
    return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
