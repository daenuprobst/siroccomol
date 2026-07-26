import numpy as np
from scipy.spatial import cKDTree

CHAIN = np.array(
    [
        [0.75, 0.42, 0.38],
        [0.42, 0.55, 0.70],
        [0.55, 0.68, 0.45],
        [0.78, 0.66, 0.40],
        [0.60, 0.48, 0.66],
        [0.45, 0.66, 0.66],
        [0.80, 0.55, 0.45],
        [0.55, 0.55, 0.60],
        [0.70, 0.50, 0.62],
        [0.50, 0.62, 0.55],
    ]
)

CPK = {
    "C": [0.55, 0.55, 0.58],
    "N": [0.30, 0.45, 0.75],
    "O": [0.80, 0.35, 0.32],
    "S": [0.85, 0.72, 0.35],
    "P": [0.85, 0.55, 0.30],
    "H": [0.90, 0.90, 0.90],
    "FE": [0.80, 0.48, 0.28],
    "MG": [0.45, 0.70, 0.45],
    "ZN": [0.55, 0.60, 0.70],
}
_DEFAULT_ELEMENT = np.array([0.60, 0.55, 0.55])


def colors_for(atoms, by="chain"):
    if by == "element":
        return np.array([CPK.get(e, _DEFAULT_ELEMENT) for e in atoms["element"]], float)
    _, ci = np.unique(atoms["chain"], return_inverse=True)

    return CHAIN[ci % len(CHAIN)]


def saturate_exposed(xyz, colors, radius=4.5, strength=0.9):

    xyz = np.asarray(xyz, float)
    colors = np.asarray(colors, float)
    count = np.array(
        [len(n) for n in cKDTree(xyz).query_ball_point(xyz, radius)], float
    )
    med = max(np.median(count), 1e-6)
    exposure = np.clip((med - count) / med, 0, 1)
    luma = (colors @ np.array([0.299, 0.587, 0.114]))[:, None]
    return np.clip(luma + (colors - luma) * (1.0 + strength * exposure)[:, None], 0, 1)
