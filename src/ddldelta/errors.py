# Own module so sources/render can raise it without importing generator
# (import cycles).


class GenerationError(Exception):
    """Abort condition of the generator; callers decide how to abort."""
