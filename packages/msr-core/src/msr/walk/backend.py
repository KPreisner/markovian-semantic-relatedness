"""The walk backend interface. CPU is the reference; GPU backends must agree with it."""

from collections.abc import Callable
from typing import Protocol

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray

type Progress = Callable[[int, int], None]
"""Called as `progress(step, total)` after each walk step."""


class WalkBackend(Protocol):
    def hitting_times(
        self,
        t: sp.csr_array,
        alpha1: NDArray[np.float64],
        steps: int,
        progress: Progress | None = None,
    ) -> NDArray[np.float64]:
        """v for each root: an N × roots array (Eqs. 11–18, with the tail of Eq. 17).

        `alpha1` holds the first step S·Γᵣ per root (see `msr.model.transition.first_step`); steps
        2..`steps` use `t`.
        """
        ...
