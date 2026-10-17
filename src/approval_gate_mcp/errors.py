class GateError(ValueError):
    """Caller-visible refusal: bad params, unknown op, bad/expired token, scope violation, budget exceeded."""
