"""Turkish-aware folding for search and enum aliases.

Postgres locales do not implement Turkish casing: ``I`` and ``İ`` do not
round-trip through ``lower()`` the way they do in Turkish. The snowball
``turkish`` stemmer is also a light stemmer, so agglutinative forms often
miss. Callers store a second, folded tsvector (see ``app.retrieval``) built
from this function. Folding maps both dotted and dotless I onto ``i``, which
means the search cannot tell ``ı`` and ``i`` apart.
"""

import re

_FOLD = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)


def fold_turkish(value: str) -> str:
    """Return a lowercase ASCII-ish form of ``value`` for matching."""
    prepared = value.replace("İ", "i").replace("I", "ı")
    return prepared.casefold().translate(_FOLD)


def area_key(value: str | None) -> str | None:
    if value is None:
        return None
    folded = re.sub(r"\s+", " ", fold_turkish(value)).strip()
    return folded or None
