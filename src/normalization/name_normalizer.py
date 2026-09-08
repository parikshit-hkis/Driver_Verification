import unicodedata
import re
from typing import List, Set

HONORIFICS = {
    "MR", "MRS", "MS", "MISS", "SHRI", "SHREE", "SMT", "DR", "MD",
    "KUMAR", "KUMARI"
}

def clean_and_normalize_name(name: str) -> str:
    """
    Standardizes a personal name:
    1. Normalizes Unicode to NFKC
    2. Converts to uppercase
    3. Removes non-alphabetic punctuation (keeps letters and spaces)
    4. Strips known honorifics/titles (Mr, Smt, etc.)
    5. Normalizes whitespace
    """
    if not name:
        return ""

    # Unicode normalization
    normalized = unicodedata.normalize("NFKC", name)

    # Replace punctuation (periods, commas, dashes) with spaces
    cleaned = re.sub(r"[^A-Za-z\s]", " ", normalized)
    tokens = cleaned.upper().split()

    # Filter out known prefixes/honorifics if not the only token
    if len(tokens) > 1:
        tokens = [t for t in tokens if t not in HONORIFICS]

    return " ".join(tokens)

def get_name_tokens(name: str) -> List[str]:
    """Returns sorted list of alphanumeric tokens from a normalized name."""
    clean_name = clean_and_normalize_name(name)
    return sorted(clean_name.split())

def remove_single_letter_initials(name: str) -> str:
    """Removes single-character initials for fuzzy/token comparison."""
    clean_name = clean_and_normalize_name(name)
    tokens = clean_name.split()
    non_initials = [t for t in tokens if len(t) > 1]
    return " ".join(non_initials) if non_initials else clean_name
