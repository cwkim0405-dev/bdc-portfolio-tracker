"""
normalizer.py
Deterministic entity-name normalization — a cheap first pass that catches
common legal-suffix and punctuation variants (e.g. "L.P." vs "LP") before
any AI-assisted matching is needed. Genuine rebranding/name changes (e.g.
a portfolio company renamed between filings) are NOT handled here and are
left for the AI normalization layer.
"""

import re

# Legal-entity form words, matched in two ways:
# 1. Immediately after a comma, anywhere in the string (standard filing
#    convention: "Company Name, LLC", "(BP Alpha Holdings, L.P.)")
# 2. As the LAST whitespace-delimited word of the string, comma or not
#    (e.g. "Samsung Electronics Co", "Toyota Motor Corp")
#
# Both anchors deliberately require the suffix to be its own word (preceded
# by whitespace, a comma, or start-of-string) — this is what keeps common
# short tokens safe when they're fused into another word, e.g. "Co" inside
# "Box Co-Invest Blocker" is attached via a hyphen, not a space, so neither
# anchor matches it and it's correctly left untouched.
LEGAL_FORM_WORDS = [
    "llc", "lp", "inc", "incorporated", "corp", "corporation", "ltd",
    "co", "company", "plc", "nv", "sa", "ab", "as", "gmbh", "sarl", "srl", "bv",
]

_SUFFIX_UNION = "|".join(
    r"\.?\s*".join(list(word)) + r"\.?" for word in LEGAL_FORM_WORDS
)

# Anchor 1: ", <suffix>" anywhere in the string
_SUFFIX_AFTER_COMMA = re.compile(r",\s*(" + _SUFFIX_UNION + r")\b", flags=re.IGNORECASE)

# Anchor 2: "<suffix>" as the very last word, whether or not preceded by a comma
_SUFFIX_AT_END = re.compile(r"[\s,]+(" + _SUFFIX_UNION + r")\.?\s*$", flags=re.IGNORECASE)


def normalize_entity_name(name: str) -> str:
    """
    Normalize an investment/entity name for matching purposes:
    - Strip a legal-form suffix (LLC, L.P., Inc., Co., etc.) when it
      either (a) directly follows a comma anywhere in the string, or
      (b) is the trailing word of the string — covers both
      "Company Name, LLC" and "Samsung Electronics Co" conventions.
    - Both anchors require the suffix to be its own whitespace-delimited
      word, so words fused into another via a hyphen (e.g. "Co" in
      "Box Co-Invest Blocker") are never touched.
    - Lowercase and collapse remaining punctuation/whitespace.

    This is for MATCHING only — always display the original `investment_name`
    to the user, since normalization intentionally discards information
    (the legal form) that may matter for other purposes.

    Examples:
        normalize_entity_name("BP Alpha Holdings, L.P.") == "bp alpha holdings"
        normalize_entity_name("BP Alpha Holdings, LP")   == "bp alpha holdings"
        normalize_entity_name("Samsung Electronics Co")  == "samsung electronics"
        normalize_entity_name("Box Co-Invest Blocker, LLC") == "box co-invest blocker"
    """
    if not isinstance(name, str):
        return name

    text = _SUFFIX_AFTER_COMMA.sub("", name)
    text = _SUFFIX_AT_END.sub("", text)

    text = text.lower()
    text = re.sub(r"[.,]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text