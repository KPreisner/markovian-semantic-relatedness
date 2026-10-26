# ruff: noqa: E501  (verbatim paragraphs)
"""The paper's multi-concept search example (§5.4.3): Table 4 concepts and Table 5 chunks.

Transcribed from the page images (`tmp/extraction/paper_llm.md`). Table 5 omits ranks 1 and 4.
"""

# Table 4: each concept cropped to its top 10, as (term, scaled weight). Root = 100.
CONCEPTS: dict[str, list[tuple[str, float]]] = {
    "asteroid": [
        ("asteroid", 100.0),
        ("小行星", 0.42178),
        ("地球", 0.41357),
        ("陨石", 0.89455),
        ("近地", 1.80493),
        ("comet", 2.69132),
        ("火星", 0.56316),
        ("spacecraft", 1.54553),
        ("sample", 0.62392),
        ("surface", 1.70026),
    ],
    "danger": [
        ("danger", 100.0),
        ("危险", 20.28861),
        ("substantial", 2.16429),
        ("believing", 6.9801),
        ("imminent", 2.61293),
        ("危险性", 2.61619),
        ("place", 3.63564),
        ("poses", 5.20434),
        ("驱回", 3.62021),
        ("refouler", 48.82741),
    ],
    "Earth": [
        ("Earth", 100.0),
        ("地球", 49.32796),
        ("观测", 23.71159),
        ("satellite", 23.831),
        ("observation", 56.2268),
        ("orbit", 31.09241),
        ("planet", 29.9733),
        ("global", 14.7013),
        ("atmosphere", 11.59373),
        ("遥感", 10.95425),
    ],
}

# Table 5: rank → (printed score, chunk text with the bold markup removed).
CHUNKS: dict[int, tuple[float, str]] = {
    2: (
        13.046,
        '科技日报北京 12 月 30 日电据美国太空新闻网近日报道，美国国家航空航天局（NASA）近地天体（NEO）新任务近日获得 3560 万美元的研发启动资金。这一任务名为"近地天体监视任务"（NEO Surveillance Mission），将利用一台带有红外热像仪的小型太空望远镜发现和监视直径大约 140 米的近地天体，以"揪出"其中对地球构成危险的天体。',
    ),
    3: (
        12.008,
        '- 小行星防御系统预警陨石来袭可计算是否处于危险中（记者张梦然）美国国家公共广播电台官网 1 日消息称，一个"大块头"陨石近距离飞掠地球，天文学家借助美国国家航空航天局 (NASA) 研发的新系统，成功标记并算出其危险系数。2016-11-02 15:51:24',
    ),
    5: (
        9.42,
        '按照美国航天局的定义，与地球距离在 7 4 8 万公里之内、直径超过 1 4 0 米的小行星，才被认为对地球构成"潜在危险"。',
    ),
    6: (
        9.42,
        "对于地球来说，近地小行星是一种危险的存在。它们在太空中风驰电掣，不时与地球擦肩而过，让人心惊肉跳。不过这些鲁莽的家伙并非一无是处，它们身上也藏有科学家们梦寐以求的东西，比如太阳系最古老的遗迹。",
    ),
}

# Table 5 "Terms Found" (by the original tokenizer), per rank.
TERMS_FOUND: dict[int, set[str]] = {
    2: {"危险", "地球", "近地"},
    3: {"危险", "地球", "小行星", "陨石"},
    5: {"危险", "地球", "小行星"},
    6: {"危险", "地球", "小行星"},
}
