"""Connected components of C (§4.2). Walks and statistics stay inside the root's component."""

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray
from scipy.sparse.csgraph import connected_components


def component_labels(c: sp.csr_array) -> NDArray[np.int32]:
    """A component label per term. Labels are numbered in order of each component's first term."""
    _, labels = connected_components(c, directed=False)
    return labels.astype(np.int32)


def largest_component(labels: NDArray[np.int32]) -> int:
    """The label of the largest component; ties go to the lower label."""
    return int(np.argmax(np.bincount(labels)))
