"""Splitting text into lowercase tokens."""
from re import compile as build

WORD = build(r"[A-Za-z']+")


def tokens(text):
    """All words of the text, lowercased, in order."""
    return [w.lower() for w in WORD.findall(text)]
