"""Cleaning text before it is counted."""
import re


def strip_punctuation(text):
    """The text without punctuation marks."""
    return re.sub(r"[^\w\s]", "", text)
