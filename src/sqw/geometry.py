"""Shared Manhattan geometry in micrometres: mask, mesh and connectivity use one source."""

from dataclasses import asdict, dataclass

import numpy as np
from scipy.ndimage import label

from .io import digest, write_json

NETS = {"ground": 10, "pad_a": 11, "pad_b": 12, "resonator": 13, "feedline": 14}


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError(f"Invalid rectangle: {self}")

    @property
    def area(self):
        return (self.x1-self.x0)*(self.y1-self.y0)

    def contains(self, x, y):
        return (self.x0 < x) & (x < self.x1) & (self.y0 < y) & (y < self.y1)

    def expanded(self, amount):
        return Rect(self.x0-amount, self.y0-amount, self.x1+amount, self.y1+amount)

    def polygon(self):
        return [(self.x0, self.y0), (self.x1, self.y0),
                (self.x1, self.y1), (self.x0, self.y1)]


def path_rectangles(points, width, end_extension=0):
    result = []
    half = width/2
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 == x1:
            result.append(Rect(x0-half, min(y0,y1)-half, x0+half, max(y0,y1)+half))
        elif y0 == y1:
            result.append(Rect(min(x0,x1)-half, y0-half, max(x0,x1)+half, y0+half))
        else:
            raise ValueError("Only orthogonal paths are supported")
    # Square ends include half a width beyond the centerline endpoint.
    return result


def _tile(xs, ys, grid, value):
    """Coalesce cells of a labelled exact coordinate arrangement into rectangles."""
    active, done = {}, []
    for j in range(len(ys)-1):
        spans, i = [], 0
        while i < len(xs)-1:
            if grid[j, i] != value:
                i += 1
                continue
            start = i
            while i < len(xs)-1 and grid[j, i] == value:
                i += 1
            spans.append((start, i))
        current = {}
        for span in spans:
            if span in active:
                r = active.pop(span)
                current[span] = Rect(r.x0, r.y0, r.x1, ys[j+1])
            else:
                current[span] = Rect(xs[span[0]], ys[j], xs[span[1]], ys[j+1])
        done.extend(active.values())
        active = current
    return done + list(active.values())


def build(cfg):
    p = cfg["layout"]
    half, w, h, gap, cy = (p[k] for k in
                           ("chip_size_um", "pad_width_um", "pad_height_um", "pad_gap_um", "pad_y_um"))
    half /= 2
    half_height = p.get("chip_height_um",p["chip_size_um"])/2
    chip = Rect(-half, -half_height, half, half_height)
    metal_box = chip.expanded(-p["die_edge_clearance_um"])
    pads = [Rect(-w-gap/2, cy-h/2, -gap/2, cy+h/2),
            Rect(gap/2, cy-h/2, w+gap/2, cy+h/2)]
    lead, jjgap = p["junction_lead_width_um"], p["junction_em_gap_um"]
    conductors = {
        "pad_a": [pads[0], Rect(-gap/2, cy-lead/2, -jjgap/2, cy+lead/2)],
        "pad_b": [pads[1], Rect(jjgap/2, cy-lead/2, gap/2, cy+lead/2)],
    }
    cpw_w, cpw_g = p["cpw_width_um"], p["cpw_gap_um"]
    ry = cy+h/2+p["qubit_coupler_gap_um"]+cpw_w/2
    # A half-wave open/open readout avoids a fictitious DC terminal at a grounded short.
    path = [(-gap/2, ry), (-1500.0, ry), (-1500.0, 450.0),
            (1500.0, 450.0), (1500.0, 1000.0)]
    used = sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a,b in zip(path,path[1:]))
    remaining = p["readout_length_um"]-used
    if remaining < 500 or remaining > 4000:
        raise ValueError("readout_length_um does not fit the teaching meander (change routing)")
    path.append((1500.0-remaining, 1000.0))
    conductors["resonator"] = path_rectangles(path, cpw_w)
    fy, launch_len, launch_w = p["feed_y_um"], p["launcher_length_um"], p["launcher_width_um"]
    fx = half-250
    conductors["feedline"] = [Rect(-fx, fy-cpw_w/2, fx, fy+cpw_w/2),
                              Rect(-fx, fy-launch_w/2, -fx+launch_len, fy+launch_w/2),
                              Rect(fx-launch_len, fy-launch_w/2, fx, fy+launch_w/2)]
    clear = [Rect(-w-gap/2-p["moat_um"], cy-h/2-p["moat_um"],
                  w+gap/2+p["moat_um"], cy+h/2+p["moat_um"])]
    for net in ("resonator", "feedline"):
        clear.extend(r.expanded(cpw_g) for r in conductors[net])
    endx = path[-1][0]
    c_len = p["feed_coupler_length_um"]
    clear.append(Rect(endx-cpw_w/2-cpw_g, 1000-cpw_w/2-cpw_g,
                      endx+c_len, fy+cpw_w/2+cpw_g))
    port_surfaces = {"junction": Rect(-jjgap/2, cy-lead/2, jjgap/2, cy+lead/2),
                     "input": Rect(-fx+launch_len/2-10, fy+launch_w/2,
                                   -fx+launch_len/2+10, fy+launch_w/2+cpw_g),
                     "output": Rect(fx-launch_len/2-10, fy+launch_w/2,
                                    fx-launch_len/2+10, fy+launch_w/2+cpw_g)}
    shapes = clear + [r for rr in conductors.values() for r in rr]
    for r in shapes:
        if r.x0 <= -half or r.x1 >= half or r.y0 <= -half_height or r.y1 >= half_height:
            raise ValueError("Device geometry reaches chip edge; increase chip or change routing")
    xs = sorted({round(x, 6) for r in [chip,metal_box]+shapes for x in (r.x0, r.x1)})
    ys = sorted({round(y, 6) for r in [chip,metal_box]+shapes for y in (r.y0, r.y1)})
    xx, yy = np.meshgrid((np.array(xs[:-1])+xs[1:])/2, (np.array(ys[:-1])+ys[1:])/2)
    grid = np.full(xx.shape, NETS["ground"], dtype=int)
    for r in clear:
        grid[r.contains(xx, yy)] = 0
    grid[~metal_box.contains(xx,yy)] = 0
    for net, rects in conductors.items():
        for r in rects:
            if r.x0 <= metal_box.x0 or r.x1 >= metal_box.x1 or r.y0 <= metal_box.y0 or r.y1 >= metal_box.y1:
                raise ValueError("Signal enters the die-edge keepout")
            inside = r.contains(xx, yy)
            if np.any(inside & ~np.isin(grid, [0, NETS[net]])):
                raise ValueError(f"Unexpected metal overlap: {net}")
            grid[inside] = NETS[net]
    # Each signal conductor must be connected and isolated from every other net.
    counts = {net: label(grid == tag)[1] for net,tag in NETS.items()}
    if any(counts[n] != 1 for n in NETS if n != "ground"):
        raise ValueError(f"Disconnected signal geometry: {counts}")
    for a,b in ((grid[:,:-1],grid[:,1:]), (grid[:-1,:],grid[1:,:])):
        if np.any((a != b) & (a != 0) & (b != 0)):
            raise ValueError("A signal touches another net or ground")
    metal = {net: [asdict(r) for r in _tile(xs, ys, grid, tag)] for net,tag in NETS.items()}
    data = {"schema_version": 1, "units": "um", "topology": "floating_transmon_halfwave_readout",
            "chip": asdict(chip), "metal": metal, "pads": [asdict(r) for r in pads],
            "ports": {name: asdict(r) for name,r in port_surfaces.items()},
            "resonator_path": path, "resonator_length_um": p["readout_length_um"],
            "connectivity_components": counts, "physical_tags": NETS,
            "junction_mask_qualified": p["junction_mask_qualified"]}
    data["geometry_sha256"] = digest(data)
    return data


def save(data, path):
    write_json(path, data)


def preview(data, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    colors = {"ground": "#cbd5e1", "pad_a": "#17a398", "pad_b": "#1d4ed8",
              "resonator": "#e87722", "feedline": "#9333ea"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for ax in axes:
        for net, rects in data["metal"].items():
            for rd in rects:
                r = Rect(**rd)
                ax.add_patch(Rectangle((r.x0,r.y0), r.x1-r.x0, r.y1-r.y0,
                                       facecolor=colors[net], linewidth=0))
        ax.set_aspect("equal")
        ax.set_xlabel("x (um)")
        ax.set_ylabel("y (um)")
    c = Rect(**data["chip"])
    axes[0].set(xlim=(c.x0,c.x1), ylim=(c.y0,c.y1), title="Positive metal mask")
    cy = (data["pads"][0]["y0"]+data["pads"][0]["y1"])/2
    axes[1].set(xlim=(-450,450), ylim=(cy-350,cy+400), title="Qubit and capacitive coupler")
    fig.suptitle("Al / high-resistivity Si | teaching geometry | fabrication HOLD")
    fig.savefig(path, dpi=170)
    plt.close(fig)
