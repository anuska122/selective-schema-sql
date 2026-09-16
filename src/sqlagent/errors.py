class AbortRun(RuntimeError):
    """Raised when a run cannot continue, such as an exhausted daily quota."""
