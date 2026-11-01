from tests import helpers  # noqa: F401  (must be first: points the data folders at a scratch folder)
"""M17: Mary offers printing only when this computer has a real printer."""
import unittest
from unittest import mock

import mary
import printers
from tests.test_m15b_cards import Base

OFFERS = ("Want it printed", "Would you like it printed")


class IsRealTests(unittest.TestCase):
    def test_names(self):
        for name in ("Microsoft Print to PDF", "Microsoft XPS Document Writer", "OneNote (Desktop)",
                     "Send To OneNote 2016", "Fax", "Microsoft Fax", "", None):
            self.assertFalse(printers.is_real(name), name)
        for name in ("HP LaserJet", "Fairfax Office", "Brother HL-L2350DW"):
            self.assertTrue(printers.is_real(name), name)

    def test_offline_is_not_real(self):
        self.assertFalse(printers.is_real("HP LaserJet", 0x400))
        self.assertTrue(printers.is_real("HP LaserJet", 0x2))


class HasPrinterTests(unittest.TestCase):
    def setUp(self):
        old = (printers._override, printers._cached, printers._cached_at)
        self.addCleanup(lambda: (setattr(printers, "_override", old[0]), setattr(printers, "_cached", old[1]),
                                 setattr(printers, "_cached_at", old[2])))
        printers._override, printers._cached, printers._cached_at = None, None, 0.0

    def test_cached_for_thirty_seconds(self):
        with mock.patch.object(printers, "sys", mock.Mock(platform="win32")), \
                mock.patch.object(printers, "_listed", return_value=[("HP LaserJet", 0)]) as listed, \
                mock.patch.object(printers.time, "monotonic") as clock:
            clock.return_value = 1000.0
            self.assertTrue(printers.has_printer())
            clock.return_value = 1029.0
            self.assertTrue(printers.has_printer())
            self.assertEqual(listed.call_count, 1)
            clock.return_value = 1031.0
            printers.has_printer()
            self.assertEqual(listed.call_count, 2)

    def test_an_error_means_no_printer(self):
        with mock.patch.object(printers, "sys", mock.Mock(platform="win32")), \
                mock.patch.object(printers, "_listed", side_effect=OSError("no spooler")):
            self.assertIs(printers.has_printer(), False)

    def test_only_fake_printers(self):
        with mock.patch.object(printers, "sys", mock.Mock(platform="win32")), \
                mock.patch.object(printers, "_listed", return_value=[("Microsoft Print to PDF", 0), ("Fax", 0)]):
            self.assertIs(printers.has_printer(), False)


class NoPrinterTests(Base):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, printers, "_override", printers._override)

    def set_printer(self, value):
        printers._override = value

    def test_ctx_matches_the_core(self):
        for value in (True, False):
            self.set_printer(value)
            self.assertIs(self.ctx.has_printer(), value)

    def test_skills_may_not_import_printers(self):
        import skills_core
        self.assertIn("printers", skills_core.FORBIDDEN_IMPORTS)

    def test_print_card_without_a_printer(self):
        self.set_printer(False)
        self.card()
        self.act("save_card_now")
        r = self.act("print_card")
        self.assertIs(r["printing"], False)
        self.assertIs(r["saved"], True)
        self.assertNotIn("print", self.kinds())
        self.assertIn("helper", self.last["say"])

    def test_print_card_with_a_printer(self):
        self.set_printer(True)
        self.card()
        self.act("save_card_now")
        r = self.act("print_card")
        self.assertIs(r["printing"], True)
        self.assertIn("print", self.kinds())

    def test_send_with_no_email_offers_nothing(self):
        self.set_printer(False)
        self.card()
        r = self.act("send_it")
        self.assertEqual((r["sent"], r["saved"], r["can_print"]), (False, True, False))
        for offer in OFFERS:
            self.assertNotIn(offer, self.last["say"])
        self.assertIn("helper", self.last["say"])

    def test_send_with_no_email_offers_with_a_printer(self):
        self.set_printer(True)
        self.card()
        r = self.act("send_it")
        self.assertIs(r["can_print"], True)
        self.assertIn("Want it printed", self.last["say"])

    def test_the_other_lines_offer_nothing(self):
        self.set_printer(False)
        self.card()
        self.act("save_card_now")
        ctx = self.ctx
        lines = [self.mod._then_print(ctx, "Sent to Ann."), self.mod._then_print(ctx, "Kept."),
                 self.mod._then_print(ctx, "That didn't go."), self.mod._no_picture(ctx),
                 self.mod._cant_go(ctx, self.mod.SAY_CANT_SEND, self.mod.SAY_CANT_SEND_LATER)["say"]
                 if "say" in self.mod._cant_go(ctx, "x", "y %s") else
                 self.mod.SAY_CANT_SEND_LATER % self.mod._what(ctx)]
        for line in lines:
            for offer in OFFERS:
                self.assertNotIn(offer, line)
        self.assertIn("helper", lines[0])
        self.set_printer(True)
        self.assertIn("Would you like it printed", self.mod._then_print(self.ctx, "Sent to Ann."))
        self.assertIn("Want it printed", self.mod.SAY_CANT_SEND)


class PromptTests(unittest.TestCase):
    def facts(self, printer):
        facts = {"printer": printer}
        with mock.patch.object(mary, "app_facts", lambda companion: facts):
            return mary._app_facts_text("mary")

    def test_no_printer_line(self):
        self.assertIn("no printer on this computer", self.facts(False))
        self.assertNotIn("no printer on this computer", self.facts(True))


if __name__ == "__main__":
    unittest.main()
