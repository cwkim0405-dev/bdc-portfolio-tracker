"""
normalizer.py
Deterministic entity-name normalization — a cheap first pass that catches
common legal-suffix and punctuation variants (e.g. "L.P." vs "LP") before
any AI-assisted matching is needed. Genuine rebranding/name changes (e.g.
a portfolio company renamed between filings) are NOT handled here and are
left for the AI normalization layer.
"""

import re

# Legal-entity form words. Matched ONLY when they immediately follow a
# comma (the standard filing convention: "Company Name, LLC",
# "(BP Alpha Holdings, L.P.)") — this deliberately avoids stripping short,
# common tokens like "co" or "as" when they're part of an unrelated word
# or phrase (e.g. "Box Co-Invest" — "Co" here follows a hyphen, not a
# comma, so it's correctly left untouched).
LEGAL_FORM_WORDS = [
    "llc", "lp", "inc", "incorporated", "corp", "corporation", "ltd",
    "co", "company", "plc", "nv", "sa", "ab", "as", "gmbh", "sarl", "srl", "bv",
]

# Matches ", <form>" optionally with periods/spaces between letters
# (so it catches "L.P.", "LLC", "L. L. C.", etc.) right after a comma.
_SUFFIX_AFTER_COMMA = re.compile(
    r",\s*(" + "|".join(
        r"\.?\s*".join(list(word)) + r"\.?" for word in LEGAL_FORM_WORDS
    ) + r")\b",
    flags=re.IGNORECASE,
)


def normalize_entity_name(name: str) -> str:
    """
    Normalize an investment/entity name for matching purposes:
    - Remove a legal-form suffix (LLC, L.P., Inc., Co., etc.) ONLY when
      it directly follows a comma, matching the standard filing
      convention. This avoids false positives on words like "Co" or "As"
      appearing elsewhere in a name (e.g. "Box Co-Invest Blocker").
    - Lowercase and collapse remaining punctuation/whitespace.

    This is for MATCHING only — always display the original `investment_name`
    to the user, since normalization intentionally discards information
    (the legal form) that may matter for other purposes.

    Example:
        normalize_entity_name("BP Alpha Holdings, L.P.") == "bp alpha holdings"
        normalize_entity_name("BP Alpha Holdings, LP")   == "bp alpha holdings"
        normalize_entity_name("Box Co-Invest Blocker, LLC") == "box co-invest blocker"
    """
    if not isinstance(name, str):
        return name

    text = _SUFFIX_AFTER_COMMA.sub("", name)

    text = text.lower()
    text = re.sub(r"[.,]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text