import unittest

from ledger import balance, statement

ENTRIES = [("rent", -1200), ("salary", 3000), ("coffee", -4)]


class LedgerTest(unittest.TestCase):
    def test_balance(self):
        self.assertEqual(balance(ENTRIES), 1796)

    def test_statement_covers_every_entry(self):
        lines = statement(ENTRIES, opening=100)
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[-1].split()[-1], "1896")


if __name__ == "__main__":
    unittest.main()
