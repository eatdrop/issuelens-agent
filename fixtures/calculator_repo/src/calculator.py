"""Small fixture repository used by IssueLens evaluations."""


def add(left: float, right: float) -> float:
    return left + right


def divide(left: float, right: float) -> float:
    """Divide two numbers.

    The public API is expected to expose domain validation errors as ValueError.
    """
    return left / right
