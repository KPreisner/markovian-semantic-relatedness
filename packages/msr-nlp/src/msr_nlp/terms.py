"""Term sets: the unique terms of one chunk, as the model build consumes them (§3.1).

A term set is the chunk's unique token texts plus its named-entity spans. Terms are case-sensitive.
Tokens with no letter or digit (punctuation, symbols, whitespace) are dropped; numbers and dates
are kept, since they're meaningful terms ("September 19, 1979", "2005YU55"). Stop words are not
removed here: the model build drops them by chunk frequency.
"""

from dataclasses import dataclass

from spacy.tokens import Doc


@dataclass(frozen=True)
class TermSet:
    terms: frozenset[str]
    entities: frozenset[str]
    """The entity spans among `terms`, kept for inspection (`entity_df`). The model build treats
    them like any other term."""


def is_term(text: str) -> bool:
    return any(ch.isalnum() for ch in text)


def term_set(doc: Doc) -> TermSet:
    tokens = {t.text for t in doc if is_term(t.text)}
    entities = {" ".join(e.text.split()) for e in doc.ents}
    entities = {e for e in entities if is_term(e)}
    return TermSet(frozenset(tokens | entities), frozenset(entities))


def is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿" or "豈" <= ch <= "﫿"


def language_of(term: str) -> str:
    """`zh` if the term has any CJK character, otherwise `en`. Stop-word rules run per language."""
    return "zh" if any(is_cjk(ch) for ch in term) else "en"
