"""Robust (MCD) and classic Mahalanobis distances.

MUST be applied to log-ratio (CLR/ILR) coordinates, never raw ppm (G11 closure).
Classic covariance is inflated by the very outliers we seek; MCD (Minimum
Covariance Determinant, Rousseeuw) estimates covariance from the most concentrated
subset, so anomalies do not mask themselves.
"""
import numpy as np
from sklearn.covariance import MinCovDet, EmpiricalCovariance


def robust_mahalanobis(X, support_fraction=None, random_state=0):
    X = np.asarray(X, dtype=float)
    mcd = MinCovDet(support_fraction=support_fraction, random_state=random_state).fit(X)
    return np.sqrt(mcd.mahalanobis(X))


def classic_mahalanobis(X):
    X = np.asarray(X, dtype=float)
    cov = EmpiricalCovariance().fit(X)
    return np.sqrt(cov.mahalanobis(X))
