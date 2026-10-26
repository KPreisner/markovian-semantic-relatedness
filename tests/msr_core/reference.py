"""A slow, independent reference implementation to check the walk against."""

type Dense = list[list[float]]


def scalar_walk(s: Dense, t: Dense, root: int, steps: int) -> list[float]:
    """Eqs. 6–10 and 16–17 with plain loops: one scalar β and v per start node k.

    The first step uses S and later steps use T (§4.2.3).
    """
    n_nodes = len(s)
    alpha = [1.0 if j == root else 0.0 for j in range(n_nodes)]
    beta = [0.0] * n_nodes
    v = [0.0] * n_nodes
    for n in range(1, steps + 1):
        step = s if n == 1 else t
        alpha = [sum(step[k][j] * alpha[j] for j in range(n_nodes)) for k in range(n_nodes)]
        for k in range(n_nodes):
            v[k] += n * alpha[k] * (1 - beta[k])
            beta[k] += alpha[k] * (1 - beta[k])
    return [v[k] + (steps + 1) * (1 - beta[k]) for k in range(n_nodes)]
