"""Compositional Data Analysis: zero replacement + log-ratio transforms.

Defaults: CLR (note: rank-deficient, covariance singular) for interpretation;
ILR (full rank, default sequential-binary-partition basis) for ML consumers.
Zero/below-DL replacement: multiplicative (Martin-Fernandez et al. 2003).
"""
import numpy as np


def multiplicative_replacement(X, delta):
    """Replace zeros in each row with `delta` (fraction of closed total),
    scaling the non-zeros to preserve closure (Martin-Fernandez)."""
    X = np.asarray(X, dtype=float)
    Xc = X / X.sum(axis=1, keepdims=True)
    out = Xc.copy()
    for i in range(Xc.shape[0]):
        row = Xc[i]
        zeros = row <= 0
        if zeros.any():
            out[i, zeros] = delta
            out[i, ~zeros] = row[~zeros] * (1.0 - delta * zeros.sum())
    return out


def _close(X):
    X = np.asarray(X, dtype=float)
    return X / X.sum(axis=1, keepdims=True)


def clr(X):
    Xc = _close(X)
    L = np.log(Xc)
    return L - L.mean(axis=1, keepdims=True)


def clr_inv(Z):
    Z = np.asarray(Z, dtype=float)
    E = np.exp(Z)
    return E / E.sum(axis=1, keepdims=True)


def default_sbp_basis(D):
    """Orthonormal ILR basis from the standard sequential binary partition
    (Egozcue & Pawlowsky-Glahn). Returns V with shape (D, D-1)."""
    psi = np.zeros((D - 1, D))
    for i in range(D - 1):
        r = D - i - 1
        psi[i, i] = np.sqrt(r / (r + 1.0))
        psi[i, i + 1:] = -1.0 / np.sqrt(r * (r + 1.0))
    return psi.T            # (D, D-1)


def ilr(X, basis=None):
    Z = clr(X)
    V = default_sbp_basis(X.shape[1]) if basis is None else basis
    return Z @ V
