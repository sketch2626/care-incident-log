"""M19's nine required proofs. Each is already tested end to end elsewhere; this file names where,
and checks those tests are still there so a rename can't quietly drop a proof."""
from tests import helpers  # noqa: F401  (first: scratch data folder)

import unittest
from pathlib import Path

TESTS = Path(__file__).parent

# proof -> (file, test name)
PROOFS = {
    1: ("test_address_book.py", "test_nothing_readable_in_either_file"),
    2: ("test_address_book.py", "test_missing_key_locks_and_no_new_key_is_made"),
    3: ("test_book_move.py", "test_they_leave_the_file_for_good"),
    4: ("test_people_door.py", "test_a_card_without_it_gets_nothing_not_even_a_count"),
    5: ("test_book_forget.py", "test_every_place_she_was"),
    6: ("test_book_forget.py", "test_forget_everything_leaves_the_book_and_its_reminders"),
    7: ("test_book_copy.py", "test_round_trip_into_a_fresh_folder_with_its_own_key"),
    8: ("test_book_voice.py", "test_only_their_plain_save_counts"),
    9: ("test_book_tools.py", "test_words_that_dont_ask_get_nothing"),
}
# Also: 3 Backups.test_every_dated_backup_is_cleaned; 7 test_every_bad_try_gets_the_same_words;
# 9 ListAndAdd.test_who_gives_names_and_relationships.


class ProofsAreStillTested(unittest.TestCase):
    def test_each_proof_has_its_test(self):
        for number, (name, test) in PROOFS.items():
            text = (TESTS / name).read_text(encoding="utf-8")
            self.assertIn("def %s(" % test, text, "proof %d: %s in %s" % (number, test, name))


if __name__ == "__main__":
    unittest.main()
