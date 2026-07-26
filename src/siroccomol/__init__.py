"""Render proteins as space-filling molecular surfaces in two styles, matte and cel.

Named for the sirocco, the hot Mediterranean wind.

    import siroccomol
    siroccomol.render_protein("4HHB", style="cel", out="hemoglobin.png")
    siroccomol.compare("4HHB", out="compare.png")
    siroccomol.spin("4HHB", out="spin.mp4")
"""
from .render import (render_protein, compare, render_array, voxelize, save_image,
                     spin, compare_spin, save_video, vdw_radii)
from .pdb import load_atoms, fetch_pdb
from .palettes import colors_for, saturate_exposed

__version__ = "0.1.0"
__all__ = ["render_protein", "compare", "render_array", "voxelize", "save_image",
           "spin", "compare_spin", "save_video", "vdw_radii", "load_atoms", "fetch_pdb",
           "colors_for", "saturate_exposed"]
