"""A short report on the most frequent words."""
from collections import Counter

from tally.tokens import tokens


def top_words(text, n=3):
    """The n most frequent words with their counts."""
    return Counter(tokens(text)).most_common(n)
