"""Deterministic scoring rules for live quiz responses."""


FAST_ANSWER_THRESHOLD_MS = 500


def calculate_points(
    *,
    is_correct: bool,
    response_time_ms: int,
    time_limit_seconds: int,
    max_points: int,
) -> int:
    """Return points for one response using the standard Kahoot speed formula.

    Correct responses submitted in less than 0.5 seconds receive the maximum.
    Otherwise the formula is:

        max_points * (1 - response_time / (2 * time_limit))

    The result is rounded to the nearest whole point, with exact halves rounded
    upward. A response beyond the question limit is invalid and must be rejected
    rather than scored.
    """
    if response_time_ms < 0:
        raise ValueError("Response time must not be negative.")
    if time_limit_seconds <= 0:
        raise ValueError("Time limit must be positive.")
    if max_points <= 0:
        raise ValueError("Maximum points must be positive.")

    time_limit_ms = time_limit_seconds * 1_000
    if response_time_ms > time_limit_ms:
        raise ValueError("A late response cannot be scored.")

    if not is_correct:
        return 0
    if response_time_ms < FAST_ANSWER_THRESHOLD_MS:
        return max_points

    # Integer arithmetic avoids floating-point drift. For non-negative values,
    # (2 * numerator + denominator) // (2 * denominator) is round-half-up.
    numerator = max_points * (2 * time_limit_ms - response_time_ms)
    denominator = 2 * time_limit_ms
    return (2 * numerator + denominator) // (2 * denominator)
