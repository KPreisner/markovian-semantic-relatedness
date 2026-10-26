class NoConceptError(ValueError):
    """A root that has no concept: it's alone in its component, or its component is too small for
    the trimmed reference statistics to scale by (the toy's "Bill"). The input is fine; the answer
    is that there is none."""
