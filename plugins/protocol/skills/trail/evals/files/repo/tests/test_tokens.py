import re
import unittest

from tally.tokens import tokens


class TokensTest(unittest.TestCase):
    def test_lowercases_and_keeps_order(self):
        self.assertEqual(tokens("Hello, hello World"), ["hello", "hello", "world"])

    def test_every_token_is_a_word(self):
        for token in tokens("It's 9 o'clock"):
            self.assertTrue(re.fullmatch(r"[a-z']+", token))


if __name__ == "__main__":
    unittest.main()
