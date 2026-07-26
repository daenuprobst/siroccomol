import os
import tempfile
import urllib.request

import numpy as np


def fetch_pdb(pdb_id, dest=None):
    pdb_id = pdb_id.upper()
    dest = dest or os.path.join(tempfile.gettempdir(), f"{pdb_id}.pdb")

    if not os.path.exists(dest):
        urllib.request.urlretrieve(
            f"https://files.rcsb.org/download/{pdb_id}.pdb", dest
        )

    return dest


def load_atoms(source, hetatm=False):
    if not os.path.exists(source) and len(source) == 4 and source.isalnum():
        source = fetch_pdb(source)

    recs = ("ATOM", "HETATM") if hetatm else ("ATOM",)
    xyz, chain, element = [], [], []

    with open(source) as f:
        for line in f:
            if not line.startswith(recs):
                continue
            try:
                xyz.append([float(line[30:38]), float(line[38:46]), float(line[46:54])])
            except ValueError:
                continue
            chain.append(line[21])
            el = (
                line[76:78].strip()
                or "".join(c for c in line[12:16] if c.isalpha())[:1]
            )
            element.append(el.upper())

    if not xyz:
        raise ValueError(f"no atoms parsed from {source!r}")

    return {
        "xyz": np.asarray(xyz, float),
        "chain": np.asarray(chain),
        "element": np.asarray(element),
    }
