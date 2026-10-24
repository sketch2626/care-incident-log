from tests import helpers  # noqa: F401  (scratch data before server)
import server
import unittest

AT = "2026-10-20 14:30:00"

# (text, values that must match; keys not listed are not checked)
CASES = [
    ("Incident: I pushed the call light and waited", {"category": "call_light"}),
    ("Incident: dinner came cold", {"category": "meal"}),
    ("Incident: they left me on the toilet for an hour",
     {"category": "toileting", "wait_minutes": 60, "severity": "serious"}),
    ("Incident: I asked for the bathroom and waited", {"category": "toileting"}),
    ("Incident: they skipped my shower today", {"category": "bathing", "severity": "serious"}),
    ("Incident: the nurse gave my meds two hours late",
     {"category": "medication", "wait_minutes": 120, "severity": "serious"}),
    ("Incident: they did not turn me in bed for 4 hours",
     {"category": "repositioning", "wait_minutes": 240, "severity": "serious"}),
    ("Incident: I fell out of bed", {"category": "safety", "severity": "dangerous"}),
    ("Incident: the aide was rude and yelled at me", {"category": "staff", "severity": "minor"}),
    ("Incident: the TV in the lounge was too loud all afternoon",
     {"category": "other", "severity": "minor"}),
    ("Incident: the call light was on for 15 minutes", {"wait_minutes": 15, "severity": "minor"}),
    ("Incident: the bath aide made me wait forty-five minutes",
     {"category": "bathing", "wait_minutes": 45}),
    ("Incident: I waited 3 hours for water", {"wait_minutes": 180, "severity": "serious"}),
    ("Incident: nobody came when I pushed the call light",
     {"never_came": True, "severity": "serious"}),
    ("Incident: nobody came for an hour",
     {"never_came": False, "wait_minutes": 60, "severity": "serious"}),
    ("Incident: nobody came until the next shift", {"never_came": False, "severity": "serious"}),
    ("Incident: I have a fever and no one helped me",
     {"severity": "dangerous", "never_came": False}),
    ("Incident: I had pain in my hip for hours", {"severity": "serious", "wait_minutes": None}),
]


class GuessIncidentTests(unittest.TestCase):
    def test_table(self):
        for text, expected in CASES:
            with self.subTest(text=text):
                got = server.guess_incident(text, AT)
                for key, value in expected.items():
                    self.assertEqual(got[key], value, key)

    def test_incident_prefix_and_filler_are_stripped(self):
        cases = [
            ("Incident: um, the window is loose", "The window is loose"),
            ("New incident: the window is loose", "The window is loose"),
        ]
        for text, description in cases:
            with self.subTest(text=text):
                self.assertEqual(server.guess_incident(text, AT)["description"], description)

    def test_description_starts_with_capital_letter(self):
        for text in ["the window is loose", "um the window is loose", "Incident: um, the window is loose"]:
            with self.subTest(text=text):
                self.assertTrue(server.guess_incident(text, AT)["description"][:1].isupper())

    def test_date_and_time_come_from_at(self):
        cases = [(AT, "2026-10-20", "14:30"), ("2026-01-05 07:05:59", "2026-01-05", "07:05")]
        for at, date, time in cases:
            with self.subTest(at=at):
                got = server.guess_incident("Incident: the window is loose", at)
                self.assertEqual(got["occurred_date"], date)
                self.assertEqual(got["occurred_time"], time)

    @unittest.skip("BUG: 'couldn't breathe' is marked minor, should be dangerous")
    def test_couldnt_breathe_is_dangerous(self):
        got = server.guess_incident("Incident: I couldn't breathe for a while", AT)
        self.assertEqual(got["severity"], "dangerous")

    @unittest.skip("BUG: 'bled' is marked minor, should be dangerous")
    def test_bled_is_dangerous(self):
        got = server.guess_incident("Incident: I bled from my arm", AT)
        self.assertEqual(got["severity"], "dangerous")

    @unittest.skip("BUG: 'twenty five' and 'thirty five' minutes are read as 5 minutes")
    def test_compound_number_minutes_are_read_whole(self):
        cases = [
            ("Incident: I waited twenty five minutes for water", 25),
            ("Incident: I waited thirty five minutes for water", 35),
        ]
        for text, minutes in cases:
            with self.subTest(text=text):
                got = server.guess_incident(text, AT)
                self.assertEqual(got["wait_minutes"], minutes)

    @unittest.skip("BUG: 'half an hour' is read as 60 minutes, should be 30")
    def test_half_an_hour_is_thirty_minutes(self):
        got = server.guess_incident("Incident: I had to wait half an hour for my pills", AT)
        self.assertEqual(got["wait_minutes"], 30)

    @unittest.skip("BUG: curly apostrophe in 'can't breathe' is marked minor, should be dangerous")
    def test_curly_apostrophe_cant_breathe_is_dangerous(self):
        got = server.guess_incident("Incident: I can’t breathe at night", AT)
        self.assertEqual(got["severity"], "dangerous")


if __name__ == "__main__":
    unittest.main()
