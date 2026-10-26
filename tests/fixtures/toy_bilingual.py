"""A bilingual toy: the paper's toy corpus, a Chinese mirror of it, and a dictionary between them.

Every English chunk except "Bill G" has a Chinese twin with the same structure (的 stands in for
"the"), so with no dictionary the two languages are separate components and the dictionary is the
only bridge.
"""

from tests.fixtures import toy

EN_TO_ZH = {
    "cat": "猫",
    "child": "孩子",
    "dog": "狗",
    "fat": "胖",
    "hat": "帽子",
    "in": "里",
    "lost": "迷路",
    "the": "的",
    "wild": "野",
}

ZH_CHUNKS = [{EN_TO_ZH[t] for t in chunk} for chunk in toy.CHUNKS[1:]]
CHUNKS = toy.CHUNKS + ZH_CHUNKS

# Every toy word's translation, plus pairs that must be skipped.
DICTIONARY = [
    *EN_TO_ZH.items(),
    ("猫", "cat"),  # the same pair reversed: counted once
    ("cat", "cat"),  # a term with itself
    ("fish", "鱼"),  # neither side in the vocab
    ("cat", "鱼"),  # zh side not in the vocab
    ("bird", "狗"),  # en side not in the vocab
]

# Raw, untokenized Chinese paragraphs for cross-language search.
PARAGRAPHS = {
    "weather": "今天天气很好，我们去公园散步。",
    "dog": "迷路的狗在公园里找到了孩子。",
    "cat": "我家的胖猫喜欢睡在帽子里。",
}
