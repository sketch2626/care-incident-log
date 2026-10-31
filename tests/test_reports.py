"""Report tests: the printable /report page, F-tag citations, the neglect pattern rule and the xlsx export.
Scratch data only (see helpers.py)."""
from tests import helpers  # noqa: F401  (must be first: points the data folder at a scratch dir)

import io
import re
import unittest
import zipfile

import reports

api, incident, reset_db = helpers.api, helpers.incident, helpers.reset_db

NOTE = "possible neglect"


def attest_section(html):
    m = re.search(r'<section class="attest">.*?</section>', html, re.S)
    assert m, "no attestation section in the report"
    return m.group(0)


class ReportBase(unittest.TestCase):
    def setUp(self):
        reset_db()

    def add(self, **overrides):
        status, body, _ = api("POST", "/api/incidents", incident(**overrides))
        self.assertEqual(status, 201, body)
        return body

    def report(self, query=""):
        status, body, headers = api("GET", "/report" + query)
        self.assertEqual(status, 200)
        self.assertIsInstance(body, bytes)
        return body.decode("utf-8"), headers


class ReportPageTests(ReportBase):
    def test_report_is_html_with_attestation_and_signature_lines(self):
        self.add()
        html, headers = self.report()
        self.assertIn("text/html", headers.get("Content-Type", ""))
        section = attest_section(html)
        self.assertIn("Resident&rsquo;s attestation", section)
        self.assertIn("declare that each entry in this record was written by me", section)
        self.assertIn("Signature of resident", section)
        self.assertIn("Witness signature (optional)", section)

    def test_resident_name_appears_in_attestation(self):
        self.add()
        status, _, _ = api("PUT", "/api/settings", {"resident_name": "Mabel Jones"})
        self.assertEqual(status, 200)
        html, _ = self.report()
        self.assertRegex(attest_section(html), r"I, <span class=\"fill\">Mabel Jones</span>, declare that")

    def test_blank_name_leaves_an_empty_signing_blank(self):
        # The page shows an empty underlined blank (class "fill"); the '______' placeholder is for the xlsx.
        self.add()
        html, _ = self.report()
        self.assertRegex(attest_section(html), r"I, <span class=\"fill\">(?:&nbsp;|\s*)</span>, declare that")

    def test_report_with_no_incidents_still_renders(self):
        html, headers = self.report()
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn("No incidents recorded in this period.", html)
        self.assertIn("Signature of resident", html)

    def test_period_with_no_incidents_still_renders(self):
        self.add(occurred_date="2026-10-20")
        html, _ = self.report("?from=2025-01-01&to=2025-01-31")
        self.assertIn("No incidents recorded in this period.", html)
        self.assertNotIn("Lunch tray never arrived.", html)
        self.assertIn("Witness signature (optional)", html)

    def test_period_filters_the_rows(self):
        self.add(occurred_date="2026-10-05", description="Inside the period marker.")
        self.add(occurred_date="2026-11-05", description="Outside the period marker.")
        html, _ = self.report("?from=2026-10-01&to=2026-10-31")
        self.assertIn("Inside the period marker.", html)
        self.assertNotIn("Outside the period marker.", html)


class FTagReportTests(ReportBase):
    def test_medication_cites_f760(self):
        self.add(category="medication", description="My evening pills came two hours late.")
        html, _ = self.report()
        self.assertIn("F760", html)

    def test_medication_f760_is_labelled_significant_only(self):
        self.add(category="medication", description="My evening pills came two hours late.")
        html, _ = self.report()
        self.assertIn("F760 (if the error was significant)", html)

    def test_non_medication_row_has_no_significant_note(self):
        self.add(category="call_light", description="I waited a long time for help.")
        html, _ = self.report()
        self.assertNotIn("if the error was significant", html)

    def test_f600_cite_covers_neglect_and_abuse_lines(self):
        for day in ("2026-10-17", "2026-10-18", "2026-10-19"):
            self.add(occurred_date=day)
        html, _ = self.report()
        self.assertIn("F600", html)
        self.assertEqual(reports.REGULATIONS["F600"]["cite"], "§483.12, §483.12(a)(1)")
        self.assertIn("§483.12, §483.12(a)(1)", html)

    def test_call_light_cites_f725(self):
        self.add(category="call_light", description="I waited a long time for help.")
        html, _ = self.report()
        self.assertIn("F725", html)
        self.assertNotIn("F919", html)

    def test_broken_call_light_also_cites_f919(self):
        self.add(category="call_light", description="My call light is broken and nobody came.")
        html, _ = self.report()
        self.assertIn("F725", html)
        self.assertIn("F919", html)

    def test_other_categories_cite_their_base_tags(self):
        self.add(category="meal")
        self.add(category="bathing", description="No bath this week.")
        self.add(category="repositioning", description="Not turned all night.")
        self.add(category="safety", description="The floor was wet by my bed.")
        html, _ = self.report()
        for tag in ("F809", "F677", "F686", "F689"):
            self.assertIn(tag, html)

    def test_unused_tags_are_not_listed(self):
        self.add(category="medication", description="Wrong pill.")
        html, _ = self.report()
        self.assertNotIn("F725", html)
        self.assertNotIn("F809", html)
        self.assertNotIn("F600", html)


class PatternRuleTests(ReportBase):
    """Three or more incidents of one category in the period add F600 (neglect)."""

    def test_two_meal_incidents_no_f600(self):
        self.add(occurred_date="2026-10-18")
        self.add(occurred_date="2026-10-19")
        html, _ = self.report()
        self.assertNotIn("F600", html)
        self.assertNotIn(NOTE, html)

    def test_three_meal_incidents_cite_f600_with_note(self):
        for day in ("2026-10-17", "2026-10-18", "2026-10-19"):
            self.add(occurred_date=day)
        html, _ = self.report()
        self.assertIn("F600", html)
        self.assertIn(NOTE, html)

    def test_three_incidents_but_only_two_in_period_no_f600(self):
        self.add(occurred_date="2026-10-18")
        self.add(occurred_date="2026-10-19")
        self.add(occurred_date="2026-10-25")
        html, _ = self.report("?from=2026-10-01&to=2026-10-20")
        self.assertNotIn("F600", html)
        # all three together do make the pattern
        html, _ = self.report()
        self.assertIn("F600", html)

    def test_three_other_incidents_no_f600(self):
        for day in ("2026-10-17", "2026-10-18", "2026-10-19"):
            self.add(category="other", occurred_date=day, description="Something else went wrong.")
        html, _ = self.report()
        self.assertNotIn("F600", html)

    def test_single_staff_incident_with_yelled_cites_f600_without_pattern(self):
        self.add(category="staff", description="The aide yelled at me in front of everyone.")
        html, _ = self.report()
        self.assertIn("F550", html)
        self.assertIn("F600", html)
        self.assertNotIn(NOTE, html)

    def test_regs_for_pattern_unit(self):
        meal = {"category": "meal", "description": "Lunch tray never arrived."}
        two = [meal, meal]
        three = [meal, meal, meal]
        self.assertNotIn("F600", reports.regs_for(meal, two))
        self.assertIn("F600", reports.regs_for(meal, three))
        self.assertIn("F809", reports.regs_for(meal, three))
        self.assertFalse(reports.is_pattern(meal, two))
        self.assertTrue(reports.is_pattern(meal, three))

    def test_regs_for_other_never_a_pattern(self):
        other = {"category": "other", "description": "Something else."}
        self.assertFalse(reports.is_pattern(other, [other] * 5))
        self.assertEqual(reports.regs_for(other, [other] * 5), [])

    def test_regs_for_text_rules_unit(self):
        self.assertEqual(reports.regs_for({"category": "call_light", "description": "light not working"}, []),
                         ["F725", "F919"])
        self.assertIn("F692", reports.regs_for({"category": "meal", "description": "I am not eating"}, []))
        self.assertIn("F600", reports.regs_for({"category": "staff", "description": "she pushed me"}, []))
        self.assertEqual(reports.regs_for({"category": "toileting", "description": "x"}, []), ["F690", "F677"])


@unittest.skipUnless(reports.Workbook, "openpyxl not installed")
class XlsxExportTests(ReportBase):
    def export(self, query=""):
        status, body, headers = api("GET", "/api/export.xlsx" + query)
        self.assertEqual(status, 200)
        self.assertIsInstance(body, bytes)
        return body, headers

    def test_export_headers(self):
        self.add()
        _, headers = self.export()
        self.assertIn("spreadsheetml.sheet", headers.get("Content-Type", ""))
        self.assertTrue(headers.get("Content-Disposition", "").startswith("attachment"))
        self.assertIn(".xlsx", headers.get("Content-Disposition", ""))

    def test_export_is_a_workbook_with_three_sheets(self):
        self.add()
        data, _ = self.export()
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        self.assertIn("xl/workbook.xml", names)
        sheets = [n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)]
        self.assertEqual(len(sheets), 3)
        wb = z.read("xl/workbook.xml").decode("utf-8")
        for name in ("Incident Record", "Summary", "Regulations"):
            self.assertIn(name, wb)

    def test_export_contains_the_incident_text_and_rows(self):
        self.add(description="Zebra marker lunch never came.")
        self.add(description="Second incident for the row count.", occurred_date="2026-10-21")
        data, _ = self.export()
        z = zipfile.ZipFile(io.BytesIO(data))
        text = ""
        if "xl/sharedStrings.xml" in z.namelist():
            text += z.read("xl/sharedStrings.xml").decode("utf-8")
        for n in z.namelist():
            if n.startswith("xl/worksheets/sheet"):
                text += z.read(n).decode("utf-8")
        self.assertIn("Zebra marker lunch never came.", text)
        sheet1 = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertGreaterEqual(len(re.findall(r"<row\b", sheet1)), 2 + 1)

    def test_export_period_filters_rows(self):
        self.add(description="Inside marker.", occurred_date="2026-10-05")
        self.add(description="Outside marker.", occurred_date="2026-11-05")
        data, _ = self.export("?from=2026-10-01&to=2026-10-31")
        z = zipfile.ZipFile(io.BytesIO(data))
        text = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xml"))
        self.assertIn("Inside marker.", text)
        self.assertNotIn("Outside marker.", text)

    def test_export_labels_f760_as_significant_only(self):
        self.add(category="medication", description="My evening pills came two hours late.")
        data, _ = self.export()
        z = zipfile.ZipFile(io.BytesIO(data))
        text = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xml"))
        self.assertIn("F760 (if the error was significant)", text)

    def test_export_with_no_incidents_still_works(self):
        data, _ = self.export()
        z = zipfile.ZipFile(io.BytesIO(data))
        self.assertIn("xl/workbook.xml", z.namelist())

    def test_export_cites_f600_only_for_a_pattern(self):
        def all_text(data):
            z = zipfile.ZipFile(io.BytesIO(data))
            return "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xml"))

        self.add(occurred_date="2026-10-18")
        self.add(occurred_date="2026-10-19")
        data, _ = self.export()
        self.assertNotIn("F600", all_text(data))
        self.add(occurred_date="2026-10-20")
        data, _ = self.export()
        self.assertIn("F600", all_text(data))

    def test_blank_resident_name_uses_underscore_placeholder(self):
        self.add()
        data, _ = self.export()
        z = zipfile.ZipFile(io.BytesIO(data))
        text = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xml"))
        self.assertIn("I, ______, declare that", text)


if __name__ == "__main__":
    unittest.main()
