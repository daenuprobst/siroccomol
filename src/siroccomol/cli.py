import argparse
import sys

from .render import render_protein, compare, spin, compare_spin


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="siroccomol",
        description="Illustrative space-filling molecular surface renderer (matte / cel styles).",
    )
    p.add_argument(
        "source",
        help="path to a .pdb file, or a 4-character PDB id (fetched from RCSB)",
    )
    p.add_argument(
        "-o",
        "--out",
        default=None,
        help="output path (.png for stills, .mp4/.mov/.mkv with --spin)",
    )
    p.add_argument("-s", "--style", default="cel", choices=["cel", "matte"])
    p.add_argument(
        "--compare", action="store_true", help="render matte AND cel side by side"
    )
    p.add_argument(
        "--spin",
        action="store_true",
        help="render a rotating turntable video (needs ffmpeg)",
    )
    p.add_argument(
        "--frames", type=int, default=144, help="frames per turn (with --spin)"
    )
    p.add_argument("--fps", type=int, default=30, help="video frame rate (with --spin)")
    p.add_argument(
        "--ss", type=int, default=2, help="supersampling factor (with --spin)"
    )
    p.add_argument("--color-by", default="chain", choices=["chain", "element"])
    p.add_argument(
        "--hetatm", action="store_true", help="include HETATM records (ligands, water)"
    )
    p.add_argument("--px", type=int, default=1100, help="output size in pixels")
    p.add_argument(
        "--grid",
        type=int,
        default=None,
        help="voxel grid resolution (default: auto, scales with structure size)",
    )
    p.add_argument(
        "--iso",
        type=float,
        default=0.45,
        help="isosurface level (surface tightness; lower inflates atoms)",
    )
    p.add_argument(
        "--sfrac",
        type=float,
        default=0.56,
        help="kernel width as a fraction of atom spacing (with --no-vdw)",
    )
    p.add_argument(
        "--no-vdw",
        action="store_true",
        help="uniform atom kernel instead of van der Waals (Bondi) radii",
    )
    p.add_argument(
        "--sky",
        action="store_true",
        help="Ghibli-style sky-gradient backdrop (cel style only)",
    )
    args = p.parse_args(argv)
    if args.out is None:
        args.out = "spin.mp4" if args.spin else "molecule.png"

    common = dict(
        color_by=args.color_by,
        out=args.out,
        hetatm=args.hetatm,
        grid=args.grid,
        iso=args.iso,
        sfrac=args.sfrac,
        vdw=not args.no_vdw,
        sky=args.sky,
    )
    if args.spin:
        spin_kw = dict(common, frames=args.frames, fps=args.fps, ss=args.ss, px=args.px)
        if args.compare:
            compare_spin(args.source, **spin_kw)
        else:
            spin(args.source, style=args.style, **spin_kw)
    elif args.compare:
        compare(args.source, px=args.px, **common)
    else:
        render_protein(args.source, style=args.style, px=args.px, **common)
    print(f"-> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
