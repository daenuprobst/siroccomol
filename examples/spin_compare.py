import siroccomol

out = siroccomol.compare_spin(
    "4HHB",
    styles=("matte", "cel"),
    frames=48,
    fps=30,
    px=700,
    out="compare_spin.mp4",
)
print("wrote", out)
