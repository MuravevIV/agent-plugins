"""Counting words."""


def count_words(text):
    """Number of words in text. Words are separated by spaces."""
    text = text.strip()
    if not text:
        return 0
    return len(text.split(" "))
