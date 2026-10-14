"""Statistics used across the evaluation."""
import numpy as np


def wilson(k, n, z=1.959963984540054):
    """95 % Wilson score interval for k successes out of n (Brown et al.)."""
    if n <= 0:
        return (np.nan, np.nan)
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    hw = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - hw), min(1.0, c + hw))
