"""The paper's toy example (§3, Figures 2–3, matrices (1), (3), (5)).

Values lifted as-is from `tmp/extraction/verify_toy.py`, which checked these transcriptions
against the page images: the chunks reproduce C exactly and M and S within the paper's 2-dp
rounding.
"""

# Figure 2: one line per chunk.
CORPUS = [
    "Bill G",
    "the cat in the hat",
    "the cat",
    "the dog",
    "the hat",
    "the wild dog",
    "the lost dog",
    "the fat cat",
    "the lost child",
]

# Figure 3: unique terms per chunk. NER keeps "Bill G" and its tokens.
CHUNKS = [
    {"Bill", "G", "Bill G"},
    {"the", "cat", "in", "hat"},
    {"the", "cat"},
    {"the", "dog"},
    {"the", "hat"},
    {"the", "wild", "dog"},
    {"the", "lost", "dog"},
    {"the", "fat", "cat"},
    {"the", "lost", "child"},
]

# Row and column order of every toy matrix: code-point order.
VOCAB = ["Bill", "Bill G", "G", "cat", "child", "dog", "fat", "hat", "in", "lost", "the", "wild"]

# fmt: off
# Matrix (1), exact.
C: list[list[int]] = [
    [  1,   1,   1,   0,   0,   0,   0,   0,   0,   0,   0,   0],
    [  1,   1,   1,   0,   0,   0,   0,   0,   0,   0,   0,   0],
    [  1,   1,   1,   0,   0,   0,   0,   0,   0,   0,   0,   0],
    [  0,   0,   0,   3,   0,   0,   1,   1,   1,   0,   3,   0],
    [  0,   0,   0,   0,   1,   0,   0,   0,   0,   1,   1,   0],
    [  0,   0,   0,   0,   0,   3,   0,   0,   0,   1,   3,   1],
    [  0,   0,   0,   1,   0,   0,   1,   0,   0,   0,   1,   0],
    [  0,   0,   0,   1,   0,   0,   0,   2,   1,   0,   2,   0],
    [  0,   0,   0,   1,   0,   0,   0,   1,   1,   0,   1,   0],
    [  0,   0,   0,   0,   1,   1,   0,   0,   0,   2,   2,   0],
    [  0,   0,   0,   3,   1,   3,   1,   2,   1,   2,   8,   1],
    [  0,   0,   0,   0,   0,   1,   0,   0,   0,   0,   1,   1],
]

# Matrix (3), printed to 2 dp (half-to-even: 0.125 prints as 0.12).
M: list[list[float]] = [
    [  0,   1,   1,   0,   0,   0,   0,   0,   0,   0,   0,   0],
    [  1,   0,   1,   0,   0,   0,   0,   0,   0,   0,   0,   0],
    [  1,   1,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0],
    [  0,   0,   0,   0,   0,   0,   1,  .5,   1,   0, .38,   0],
    [  0,   0,   0,   0,   0,   0,   0,   0,   0,  .5, .12,   0],
    [  0,   0,   0,   0,   0,   0,   0,   0,   0,  .5, .38,   1],
    [  0,   0,   0, .33,   0,   0,   0,   0,   0,   0, .12,   0],
    [  0,   0,   0, .33,   0,   0,   0,   0,   1,   0, .25,   0],
    [  0,   0,   0, .33,   0,   0,   0,  .5,   0,   0, .12,   0],
    [  0,   0,   0,   0,   1, .33,   0,   0,   0,   0, .25,   0],
    [  0,   0,   0,   1,   1,   1,   1,   1,   1,   1,   0,   1],
    [  0,   0,   0,   0,   0, .33,   0,   0,   0,   0, .12,   0],
]

# Matrix (5), printed to 2 dp.
S: list[list[float]] = [
    [  0,  .5,  .5,   0,   0,   0,   0,   0,   0,   0,   0,   0],
    [ .5,   0,  .5,   0,   0,   0,   0,   0,   0,   0,   0,   0],
    [ .5,  .5,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0],
    [  0,   0,   0,   0,   0,   0, .35, .17, .35,   0, .13,   0],
    [  0,   0,   0,   0,   0,   0,   0,   0,   0,  .8,  .2,   0],
    [  0,   0,   0,   0,   0,   0,   0,   0,   0, .27,  .2, .53],
    [  0,   0,   0, .73,   0,   0,   0,   0,   0,   0, .27,   0],
    [  0,   0,   0, .21,   0,   0,   0,   0, .63,   0, .16,   0],
    [  0,   0,   0, .35,   0,   0,   0, .52,   0,   0, .13,   0],
    [  0,   0,   0,   0, .63, .21,   0,   0,   0,   0, .16,   0],
    [  0,   0,   0, .12, .12, .12, .12, .12, .12, .12,   0, .12],
    [  0,   0,   0,   0,   0, .73,   0,   0,   0,   0, .27,   0],
]
# fmt: on

# Tolerance for M and S: half a unit in the last printed place.
PRINT_TOL = 0.005
