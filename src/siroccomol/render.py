import numpy as np
import moderngl
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
from PIL import Image, ImageDraw, ImageFont
from PIL import Image
import shutil
import subprocess
from .pdb import load_atoms
from .palettes import colors_for, saturate_exposed

GROUND = (0.97, 0.97, 0.96)
INK = (0.05, 0.05, 0.06)
INK_CEL = (0.14, 0.10, 0.09)
SKYTOP = (0.72, 0.83, 0.92)
SKYHORIZON = (0.98, 0.95, 0.88)
SHADOWTINT = (0.12, 0.15, 0.24)
LIGHTDIR = (-0.30, 0.45, 0.84)

_VS = "#version 330\nin vec2 p; out vec2 uv; void main(){uv=p*0.5+0.5; gl_Position=vec4(p,0,1);}"

_SHADE = """
    vec3 sh;
    if(cel==1){
        float luma = dot(col, vec3(0.299,0.587,0.114));
        vec3 c = clamp(mix(vec3(luma), col, 1.45), 0.0, 1.0);
        float bb = 0.5 + 0.5*b;
        if(bb > 0.62)      sh = mix(c*1.12, vec3(1.0,0.96,0.82), 0.20);
        else if(bb > 0.36) sh = c*0.96;
        else               sh = mix(c*0.55, shadowtint, 0.42);
        if(occ > 0.5) sh = mix(c*0.70, shadowtint, 0.28);
        else { float rim = pow(1.0 - abs(ndotv), 3.0); sh += rim * 0.30 * vec3(1.0, 0.97, 0.90); }
        sh = clamp(sh, 0.0, 1.0);
    } else {
        float shad = clamp(1.0 - occ*0.35, 0.0, 1.0);
        sh = col * (0.72 + 0.28*clamp(b, 0.0, 1.0)) * (0.55 + 0.45*shad);
    }
"""

_OCCL = """
uniform int shadowsteps; uniform float shadowoff, shadowstep;
float occl(vec3 p, vec3 n, vec3 l){
    float occ = 0.0;
    for(int i=0;i<shadowsteps;i++){
        vec3 q = p + n*shadowoff + l*shadowstep*float(i+1);
        if(any(lessThan(q, vec3(0.0))) || any(greaterThan(q, vec3(1.0)))) break;
        if(texture(vol, q).a >= iso) occ += 1.0;
    }
    return occ;
}
"""

_SKY = """
uniform vec3 skytop, skyhorizon; uniform int skyon;
vec3 background(int cel, vec2 uv, vec3 ground){
    return (cel == 1 && skyon == 1) ? mix(skyhorizon, skytop, uv.y) : ground;
}
"""

_MARCH_FS = (
    """
#version 330
in vec2 uv; out vec4 o;
uniform sampler3D vol; uniform float iso; uniform int steps; uniform vec3 texel3;
uniform vec3 lightdir, ground, shadowtint; uniform int cel;
"""
    + _OCCL
    + _SKY
    + """
void main(){
    bool hit=false; float rh=0.0, dprev=0.0, rprev=1.0;
    for(int i=0;i<steps;i++){
        float r = 1.0 - float(i)/float(steps-1);
        float d = texture(vol, vec3(uv, r)).a;
        if(d>=iso){ rh = mix(rprev, r, (iso-dprev)/max(d-dprev,1e-5)); hit=true; break; }
        dprev=d; rprev=r;
    }
    if(!hit){ o=vec4(background(cel, uv, ground),0.0); return; }
    vec3 col = texture(vol, vec3(uv, rh)).rgb;
    float dx=texture(vol,vec3(uv+vec2(texel3.x,0),rh)).a-texture(vol,vec3(uv-vec2(texel3.x,0),rh)).a;
    float dy=texture(vol,vec3(uv+vec2(0,texel3.y),rh)).a-texture(vol,vec3(uv-vec2(0,texel3.y),rh)).a;
    float dz=texture(vol,vec3(uv,rh+texel3.z)).a-texture(vol,vec3(uv,rh-texel3.z)).a;
    vec3 n = normalize(-vec3(dx,dy,dz));
    vec3 lv = normalize(lightdir);
    float b = dot(n, lv);
    float ndotv = n.z;
    float occ = occl(vec3(uv, rh), n, lv);
"""
    + _SHADE
    + """
    o = vec4(sh, rh);
}
"""
)

_MARCH_ANIM_FS = (
    """
#version 330
in vec2 uv; out vec4 o;
uniform sampler3D vol; uniform float iso, hw; uniform int steps; uniform vec3 texel3;
uniform vec3 camR, camU, camF, lightdir, ground, shadowtint; uniform int cel;
"""
    + _OCCL
    + _SKY
    + """
void main(){
    vec3 c0 = vec3(0.5);
    vec3 base = c0 + (uv.x-0.5)*2.0*hw*camR + (uv.y-0.5)*2.0*hw*camU;
    bool hit=false; float th=0.0, dprev=0.0, tprev=0.0;
    for(int i=0;i<steps;i++){
        float t = float(i)/float(steps-1);
        vec3 p = base + (t-0.5)*2.0*hw*camF;
        if(any(lessThan(p, vec3(0.0))) || any(greaterThan(p, vec3(1.0)))){ dprev=0.0; tprev=t; continue; }
        float d = texture(vol, p).a;
        if(d>=iso){ th = mix(tprev, t, (iso-dprev)/max(d-dprev,1e-5)); hit=true; break; }
        dprev=d; tprev=t;
    }
    if(!hit){ o=vec4(background(cel, uv, ground),0.0); return; }
    vec3 ph = base + (th-0.5)*2.0*hw*camF;
    vec3 col = texture(vol, ph).rgb;
    float dx=texture(vol,ph+vec3(texel3.x,0,0)).a-texture(vol,ph-vec3(texel3.x,0,0)).a;
    float dy=texture(vol,ph+vec3(0,texel3.y,0)).a-texture(vol,ph-vec3(0,texel3.y,0)).a;
    float dz=texture(vol,ph+vec3(0,0,texel3.z)).a-texture(vol,ph-vec3(0,0,texel3.z)).a;
    vec3 n = normalize(-vec3(dx,dy,dz));
    vec3 wl = normalize(lightdir.x*camR + lightdir.y*camU - lightdir.z*camF);
    float b = dot(n, wl);
    float ndotv = dot(n, camF);
    float occ = occl(ph, n, wl);
"""
    + _SHADE
    + """
    o = vec4(sh, 1.0 - th);
}
"""
)

_CONTOUR_FS = """
#version 330
in vec2 uv; out vec4 o; uniform sampler2D tex; uniform vec2 texel;
uniform float t0,t1,outline,cedge,ct0,ct1; uniform vec3 ink; uniform int rad;
void main(){
    vec4 s=texture(tex,uv); float n0=s.a,g=0.0,cg=0.0; bool sil=false;
    for(int dx=-rad;dx<=rad;dx++) for(int dy=-rad;dy<=rad;dy++){
        vec4 sn=texture(tex, uv+vec2(dx,dy)*texel);
        g=max(g,abs(n0-sn.a)); cg=max(cg,distance(s.rgb,sn.rgb));
        if(sn.a<=0.001) sil=true;
    }
    float ed=clamp((g-t0)/(t1-t0),0.0,1.0);
    ed=max(ed, cedge*clamp((cg-ct0)/(ct1-ct0),0.0,1.0));
    if(n0>0.001 && sil) ed=1.0; if(n0<=0.001) ed=0.0;
    o=vec4(mix(s.rgb, ink, outline*ed), 1.0);
}
"""


def make_context():
    try:
        return moderngl.create_context(standalone=True, backend="egl")
    except Exception:
        return moderngl.create_standalone_context()


def voxelize(xyz, colors, grid=None, sfrac=0.56, meta=False, radii=None):
    xyz = np.asarray(xyz, float)
    colors = np.asarray(colors, float)
    Cc = xyz - xyz.mean(0)
    Vt = np.linalg.svd(Cc, full_matrices=False)[2]
    P = Cc @ Vt.T

    if grid is None:
        grid = int(np.clip(np.ceil(np.ptp(P, 0).max() / 0.463), 192, 336))

    half = 0.5 * (P.max(0) + P.min(0))
    rad = 0.54 * np.ptp(P, 0).max()
    g = np.clip((P - half) / (2 * rad) + 0.5, 0, 1) * (grid - 1)
    dnn = float(np.median(cKDTree(g).query(g, k=2)[0][:, 1]))

    ix, iy, iz = (
        g[:, 0].round().astype(int),
        g[:, 1].round().astype(int),
        g[:, 2].round().astype(int),
    )

    if radii is None:
        buckets = [(np.s_[:], max(sfrac * dnn, 0.6))]
    else:
        sig = np.asarray(radii, float) / 2.146 * (grid - 1) / (2 * rad)
        buckets = [(np.flatnonzero(sig == s), s) for s in np.unique(sig)]

    dens = np.zeros((grid, grid, grid), np.float32)
    csum = np.zeros((grid, grid, grid, 3), np.float32)

    for idx, sigma in buckets:
        norm = (2 * np.pi) ** 1.5 * sigma**3
        d = np.zeros((grid, grid, grid), np.float32)
        np.add.at(d, (iz[idx], iy[idx], ix[idx]), 1.0)
        dens += gaussian_filter(d, sigma) * norm
        c = np.zeros((grid, grid, grid, 3), np.float32)
        np.add.at(c, (iz[idx], iy[idx], ix[idx]), colors[idx].astype(np.float32))
        csum += gaussian_filter(c, (sigma, sigma, sigma, 0)) * norm

    color = csum / np.clip(dens[..., None], 1e-6, None)
    vol = np.concatenate(
        [np.clip(color, 0, 1), np.clip(dens, 0, 8)[..., None]], -1
    ).astype("f4")

    return (vol, dnn) if meta else vol


def _ink_radius(dnn, grid, W):
    if dnn is None:
        return 3
    return int(np.clip(round(0.09 * dnn / grid * W), 1, 3))


VDW = {
    "H": 1.20,
    "C": 1.70,
    "N": 1.55,
    "O": 1.52,
    "S": 1.80,
    "P": 1.80,
    "FE": 2.00,
    "MG": 1.73,
    "ZN": 1.39,
}


def vdw_radii(elements, default=1.70):
    return np.array([VDW.get(e, default) for e in elements], float)


class _Scene:
    def __init__(
        self, rgba, px=1100, ss=2, iso=0.45, steps=224, outline=1.0, dnn=None, sky=False
    ):
        self.px, self.ss, self.W = px, ss, px * ss
        self.grid = rgba.shape[0]
        self.ctx = ctx = make_context()
        self.vol = ctx.texture3d((self.grid,) * 3, 4, rgba.tobytes(), dtype="f4")
        self.vol.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.vol.repeat_x = self.vol.repeat_y = self.vol.repeat_z = False
        self.march = ctx.program(vertex_shader=_VS, fragment_shader=_MARCH_FS)
        for u, v in (
            ("lightdir", LIGHTDIR),
            ("ground", GROUND),
            ("shadowtint", SHADOWTINT),
            ("skytop", SKYTOP),
            ("skyhorizon", SKYHORIZON),
        ):
            self.march[u].value = v
        self.march["iso"].value = iso
        self.march["steps"].value = steps
        self.march["texel3"].value = (1.0 / self.grid,) * 3
        self.march["shadowsteps"].value = 16
        self.march["shadowoff"].value = 2.5 / self.grid
        self.march["shadowstep"].value = 2.0 / self.grid
        self.march["skyon"].value = 1 if sky else 0
        self.contour = ctx.program(vertex_shader=_VS, fragment_shader=_CONTOUR_FS)
        self.contour["texel"].value = (1.0 / self.W, 1.0 / self.W)
        self.contour["t0"].value = 0.015
        self.contour["t1"].value = 0.09
        self.contour["outline"].value = outline
        self.contour["ink"].value = INK
        self.contour["cedge"].value = 0.9
        self.contour["ct0"].value = 0.1
        self.contour["ct1"].value = 0.3
        self.contour["rad"].value = _ink_radius(dnn, self.grid, self.W)
        self.tex1 = ctx.texture((self.W, self.W), 4, dtype="f4")
        self.tex2 = ctx.texture((self.W, self.W), 4, dtype="f4")
        self.fbo1 = ctx.framebuffer(color_attachments=[self.tex1])
        self.fbo2 = ctx.framebuffer(color_attachments=[self.tex2])
        quad = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], "f4").tobytes())
        self.va_m = ctx.vertex_array(self.march, [(quad, "2f", "p")])
        self.va_c = ctx.vertex_array(self.contour, [(quad, "2f", "p")])

    def render(self, style="cel"):
        self.march["cel"].value = 1 if style == "cel" else 0
        self.contour["ink"].value = INK_CEL if style == "cel" else INK
        self.fbo1.use()
        self.vol.use(0)
        self.march["vol"].value = 0
        self.va_m.render(moderngl.TRIANGLES)
        self.fbo2.use()
        self.tex1.use(0)
        self.contour["tex"].value = 0
        self.va_c.render(moderngl.TRIANGLES)
        img = np.frombuffer(self.tex2.read(), "f4").reshape(self.W, self.W, 4)[
            ::-1, :, :3
        ]

        return np.clip(
            img.reshape(self.px, self.ss, self.px, self.ss, 3).mean((1, 3)), 0, 1
        )

    def release(self):
        self.ctx.release()


def render_array(
    xyz, colors, style="cel", px=1100, grid=None, sfrac=0.56, iso=0.45, steps=224
):
    rgba = voxelize(xyz, colors, grid=grid, sfrac=sfrac)
    sc = _Scene(rgba, px=px, iso=iso, steps=steps)

    try:
        return sc.render(style)
    finally:
        sc.release()


def render_protein(
    source,
    style="cel",
    color_by="chain",
    out=None,
    hetatm=False,
    px=1100,
    grid=None,
    sfrac=0.56,
    iso=0.45,
    steps=224,
    vdw=True,
    sky=False,
):
    atoms = load_atoms(source, hetatm=hetatm)
    colors = saturate_exposed(atoms["xyz"], colors_for(atoms, by=color_by))
    radii = vdw_radii(atoms["element"]) if vdw else None
    rgba, dnn = voxelize(
        atoms["xyz"], colors, grid=grid, sfrac=sfrac, meta=True, radii=radii
    )
    sc = _Scene(rgba, px=px, iso=iso, steps=steps, dnn=dnn, sky=sky)

    try:
        img = sc.render(style)
    finally:
        sc.release()

    if out is not None:
        save_image(img, out)

    return img


def compare(
    source,
    styles=("matte", "cel"),
    color_by="chain",
    out=None,
    hetatm=False,
    px=1100,
    grid=None,
    sfrac=0.56,
    iso=0.45,
    steps=224,
    gap=24,
    labels=True,
    vdw=True,
    sky=False,
):
    atoms = load_atoms(source, hetatm=hetatm)
    colors = saturate_exposed(atoms["xyz"], colors_for(atoms, by=color_by))
    radii = vdw_radii(atoms["element"]) if vdw else None
    rgba, dnn = voxelize(
        atoms["xyz"], colors, grid=grid, sfrac=sfrac, meta=True, radii=radii
    )
    sc = _Scene(rgba, px=px, iso=iso, steps=steps, dnn=dnn, sky=sky)

    try:
        imgs = [sc.render(s) for s in styles]
    finally:
        sc.release()

    strip = np.ones((px, gap, 3))
    row = imgs[0]

    for im in imgs[1:]:
        row = np.concatenate([row, strip, im], axis=1)

    if labels:
        row = _label(row, styles, px, gap)

    if out is not None:
        save_image(row, out)

    return row


def _label(row, styles, px, gap):
    pad = max(46, px // 18)
    canvas = np.ones((px + pad, row.shape[1], 3))
    canvas[pad:] = row
    im = Image.fromarray((canvas * 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)

    try:
        font = ImageFont.load_default(size=int(pad * 0.55))
    except TypeError:
        font = ImageFont.load_default()

    for i, s in enumerate(styles):
        cx = int((i + 0.5) * px + i * gap)
        dr.text(
            (cx, pad // 2), s.capitalize(), fill=(30, 30, 30), anchor="mm", font=font
        )

    return np.asarray(im, float) / 255.0


def save_image(img, path):
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path)


def _basis(azim, elev):
    a, e = np.radians(azim), np.radians(elev)
    r0 = np.array([np.cos(a), 0.0, np.sin(a)])
    u0 = np.array([0.0, 1.0, 0.0])
    f0 = np.array([-np.sin(a), 0.0, np.cos(a)])
    u = u0 * np.cos(e) - f0 * np.sin(e)
    f = f0 * np.cos(e) + u0 * np.sin(e)

    return tuple(r0), tuple(u), tuple(f)


class _AnimScene:
    def __init__(
        self,
        rgba,
        px=700,
        ss=2,
        iso=0.45,
        steps=240,
        hw=0.72,
        outline=1.0,
        dnn=None,
        sky=False,
    ):
        self.px, self.ss, self.W = px, ss, px * ss
        self.grid = rgba.shape[0]
        self.ctx = ctx = make_context()
        self.vol = ctx.texture3d((self.grid,) * 3, 4, rgba.tobytes(), dtype="f4")
        self.vol.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.vol.repeat_x = self.vol.repeat_y = self.vol.repeat_z = False
        self.march = ctx.program(vertex_shader=_VS, fragment_shader=_MARCH_ANIM_FS)

        for u, v in (
            ("lightdir", LIGHTDIR),
            ("ground", GROUND),
            ("shadowtint", SHADOWTINT),
            ("skytop", SKYTOP),
            ("skyhorizon", SKYHORIZON),
        ):
            self.march[u].value = v

        self.march["iso"].value = iso
        self.march["steps"].value = steps
        self.march["hw"].value = hw
        self.march["texel3"].value = (1.0 / self.grid,) * 3
        self.march["shadowsteps"].value = 16
        self.march["shadowoff"].value = 2.5 / self.grid
        self.march["shadowstep"].value = 2.0 / self.grid
        self.march["skyon"].value = 1 if sky else 0
        self.contour = ctx.program(vertex_shader=_VS, fragment_shader=_CONTOUR_FS)
        self.contour["texel"].value = (1.0 / self.W, 1.0 / self.W)
        self.contour["t0"].value = 0.015
        self.contour["t1"].value = 0.09
        self.contour["outline"].value = outline
        self.contour["ink"].value = INK
        self.contour["cedge"].value = 0.9
        self.contour["ct0"].value = 0.1
        self.contour["ct1"].value = 0.3
        self.contour["rad"].value = _ink_radius(dnn, self.grid, self.W)
        self.tex1 = ctx.texture((self.W, self.W), 4, dtype="f4")
        self.tex2 = ctx.texture((self.W, self.W), 4, dtype="f4")
        self.fbo1 = ctx.framebuffer(color_attachments=[self.tex1])
        self.fbo2 = ctx.framebuffer(color_attachments=[self.tex2])
        quad = ctx.buffer(np.array([-1, -1, 3, -1, -1, 3], "f4").tobytes())
        self.va_m = ctx.vertex_array(self.march, [(quad, "2f", "p")])
        self.va_c = ctx.vertex_array(self.contour, [(quad, "2f", "p")])

    def frame(self, style, azim, elev=18.0):
        R, U, F = _basis(azim, elev)
        self.march["camR"].value = R
        self.march["camU"].value = U
        self.march["camF"].value = F
        self.march["cel"].value = 1 if style == "cel" else 0
        self.contour["ink"].value = INK_CEL if style == "cel" else INK
        self.fbo1.use()
        self.vol.use(0)
        self.march["vol"].value = 0
        self.va_m.render(moderngl.TRIANGLES)
        self.fbo2.use()
        self.tex1.use(0)
        self.contour["tex"].value = 0
        self.va_c.render(moderngl.TRIANGLES)
        img = np.frombuffer(self.tex2.read(), "f4").reshape(self.W, self.W, 4)[
            ::-1, :, :3
        ]

        return np.clip(
            img.reshape(self.px, self.ss, self.px, self.ss, 3).mean((1, 3)), 0, 1
        )

    def release(self):
        self.ctx.release()


def save_video(frames, path, fps=30, crf=17):
    exe = shutil.which("ffmpeg")

    if exe is None:
        raise RuntimeError(
            "ffmpeg not found on PATH; install ffmpeg to write spin videos"
        )

    h, w = frames[0].shape[:2]
    cmd = [
        exe,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-vcodec",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        str(crf),
        "-vf",
        "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        path,
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    try:
        for f in frames:
            proc.stdin.write((np.clip(f, 0, 1) * 255).astype(np.uint8).tobytes())

        proc.stdin.close()
    except BrokenPipeError:
        pass

    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed to encode {path}")


def spin(
    source,
    style="cel",
    frames=144,
    out="spin.mp4",
    elev=18.0,
    color_by="chain",
    hetatm=False,
    px=700,
    grid=None,
    sfrac=0.56,
    iso=0.45,
    steps=240,
    hw=0.72,
    ss=2,
    fps=30,
    crf=17,
    vdw=True,
    sky=False,
):
    atoms = load_atoms(source, hetatm=hetatm)
    radii = vdw_radii(atoms["element"]) if vdw else None
    rgba, dnn = voxelize(
        atoms["xyz"],
        saturate_exposed(atoms["xyz"], colors_for(atoms, by=color_by)),
        grid=grid,
        sfrac=sfrac,
        meta=True,
        radii=radii,
    )
    sc = _AnimScene(rgba, px=px, ss=ss, iso=iso, steps=steps, hw=hw, dnn=dnn, sky=sky)

    try:
        seq = [sc.frame(style, 360.0 * f / frames, elev) for f in range(frames)]
    finally:
        sc.release()

    save_video(seq, out, fps=fps, crf=crf)

    return out


def compare_spin(
    source,
    styles=("matte", "cel"),
    frames=144,
    out="compare_spin.mp4",
    elev=18.0,
    gap=16,
    labels=True,
    color_by="chain",
    hetatm=False,
    px=700,
    grid=None,
    sfrac=0.56,
    iso=0.45,
    steps=240,
    hw=0.72,
    ss=2,
    fps=30,
    crf=17,
    vdw=True,
    sky=False,
):
    atoms = load_atoms(source, hetatm=hetatm)
    radii = vdw_radii(atoms["element"]) if vdw else None
    rgba, dnn = voxelize(
        atoms["xyz"],
        saturate_exposed(atoms["xyz"], colors_for(atoms, by=color_by)),
        grid=grid,
        sfrac=sfrac,
        meta=True,
        radii=radii,
    )
    sc = _AnimScene(rgba, px=px, ss=ss, iso=iso, steps=steps, hw=hw, dnn=dnn, sky=sky)
    strip = np.ones((px, gap, 3))
    seq = []

    try:
        for f in range(frames):
            az = 360.0 * f / frames
            row = None
            for s in styles:
                im = sc.frame(s, az, elev)
                row = im if row is None else np.concatenate([row, strip, im], axis=1)
            seq.append(_label(row, styles, px, gap) if labels else row)
    finally:
        sc.release()

    save_video(seq, out, fps=fps, crf=crf)

    return out
