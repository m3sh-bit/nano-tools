# SPDX-FileCopyrightText: 2026 m3shtry
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# True Up, an add-on for Blender
# Copyright (C) 2026 m3shtry
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with this program in LICENSE.txt. If not, see <https://www.gnu.org/licenses/>.
#
# Additional terms under section 7 of the GNU GPL, in full in NOTICE.txt:
#   1. Keep this copyright line and credit "m3shtry" as the original author.
#   2. If you change the add-on and pass it on, free or paid, give it another
#      name and say it is based on "True Up" by m3shtry.
#   3. The name "m3shtry" is not licensed for branding other products.

bl_info = {
    "name": "True Up",
    "author": "m3shtry",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > Nano Tools",
    "description": "Stand a tilted, turned prop straight: finds its own axes by its faces and lines them up with the world",
    "category": "Object",
}

# Straighten a prop
#
# A prop stands at an angle, a bit tilted and turned. The addon finds its own
# axes by its faces: on a man-made thing almost all of the surface faces three
# perpendicular directions. Those three are its axes. Then the prop turns so
# its axes line up with the world axes: up is the one closest to vertical
# right now, front is the one closest to -Y. Closest is measured not to the
# world axes but to the object's own axes: if the prop was laid on its side
# by object rotation, it stands up the way it was modeled. If the rotation
# is baked into the mesh, object and world axes match and only the tilt is
# fixed. Then rotation and scale are baked into the mesh: the object has zero
# rotation and the mesh itself is straight, handy for texturing and modeling.
#
# Picks. When the faces don't tell (a sphere, a blob, a sculpt) or the guess
# is wrong (a mesh modeled lying on its side), pick the
# axes yourself in Edit Mode: faces, edges or verts, for one, two or three of
# X, Y, Z, any side. A face patch sets the axis it faces. A loop or a curved
# run of edges, like a ring around a sphere, sets the axis it goes around;
# a straight run sets the axis it goes along. Picks on opposite sides are one
# axis. Each picked axis goes to its nearest world axis, the smallest turn
# that does it. In Edit Mode only the mesh turns, in place around its middle:
# the object, its origin and its children stay as they were.

import itertools

import math

import bpy
import bmesh
from mathutils import Matrix, Vector


def _world_faces(obj, depsgraph):
    """Prop faces in world space: (normal, area). With modifiers."""
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    world = obj.matrix_world
    rot = world.to_3x3()
    scale_fix = rot.inverted().transposed() if abs(rot.determinant()) > 1e-12 else rot
    out = []
    for poly in mesh.polygons:
        n = (scale_fix @ poly.normal)
        if n.length < 1e-9:
            continue
        a = poly.area * abs(rot.determinant()) ** (2.0 / 3.0)
        out.append((n.normalized(), a))
    evaluated.to_mesh_clear()
    return out


def own_axes(faces, world_x=Vector((1, 0, 0))):
    """The prop's three own axes by its faces. Returns (axes, how sure: share of the area lying along them)."""
    if not faces:
        return None, 0.0
    total = sum(a for _n, a in faces)
    faces = sorted(faces, key=lambda f: -f[1])[:3000]
    cos_tol = math.cos(math.radians(7.0))

    def score(axis, allow):
        return sum(a for n, a in allow if abs(n.dot(axis)) >= cos_tol)

    # candidates: normals of big faces. A direction and its opposite are one axis
    candidates = []
    for n, a in faces[:400]:
        if all(abs(n.dot(c)) < 0.995 for c in candidates):
            candidates.append(n)
    best_a = max(candidates, key=lambda c: score(c, faces))
    # second axis: the best one among those perpendicular to the first
    side = [c for c in candidates if abs(c.dot(best_a)) < math.sin(math.radians(6.0))]
    flat = [(n, a) for n, a in faces if abs(n.dot(best_a)) < 0.5]
    if side and score(max(side, key=lambda c: score(c, flat)), flat) > 0.02 * total:
        best_b = max(side, key=lambda c: score(c, flat))
        best_b = (best_b - best_a * best_b.dot(best_a)).normalized()
    else:                                                  # round prop: no faces around the main axis. Take the direction closest to the current X
        best_b = (world_x - best_a * world_x.dot(best_a))
        best_b = best_b.normalized() if best_b.length > 1e-6 else best_a.orthogonal().normalized()
    best_c = best_a.cross(best_b).normalized()
    sure = (score(best_a, faces) + score(best_b, faces) + score(best_c, faces)) / max(total, 1e-12)
    return (best_a, best_b, best_c), sure


def straightening(axes, ref_up=Vector((0, 0, 1)), ref_forward=Vector((0, -1, 0))):
    """Rotation that lines the own axes up with the world. Up is the axis closest to ref_up, front the one closest to ref_forward.
    The object's own axes are passed as ref: if the prop was laid on its side by object rotation while the mesh inside is straight,
    up is found by the object's own Z and it stands the way it was modeled. If the rotation is baked into the mesh, the refs are the world axes."""
    pool = []
    for axis in axes:
        pool.append(axis)
        pool.append(-axis)
    up = max(pool, key=lambda v: v.dot(ref_up))
    rest = [v for v in pool if abs(v.dot(up)) < 0.5]
    forward = max(rest, key=lambda v: v.dot(ref_forward))      # the prop faces -Y, like everything in the kit
    y_axis = -forward
    z_axis = up
    x_axis = y_axis.cross(z_axis).normalized()            # right-handed: x = y × z. Another order gives a mirror and the prop flips
    # a matrix whose columns are the new axes in world space: it maps the world into the prop's axes. We need the inverse
    frame = Matrix((x_axis, y_axis, z_axis)).transposed()
    return frame.inverted()


def _line_or_plane(pts):
    """Axis of a run of points in world space: along it if the run is straight ('LINE'), else across the plane it lies in ('PLANE'),
    like the axis a ring goes around. Returns (direction, weight, kind) or None."""
    import numpy as np
    if len(pts) < 2:
        return None
    a = np.array([tuple(p) for p in pts])
    a -= a.mean(axis=0)
    vals, vecs = np.linalg.eigh(a.T @ a)                   # ascending: vecs[:, 2] runs along the points, vecs[:, 0] across their plane
    if vals[2] <= 1e-18:
        return None
    straight = len(pts) == 2 or vals[1] <= 1e-5 * vals[2]   # wider than 0.3% of its length is curved: two edges of a dense ring still count
    axis = Vector(tuple(vecs[:, 2] if straight else vecs[:, 0])).normalized()
    return axis, 4.0 * float(vals[1] + vals[2]) / len(pts), 'LINE' if straight else 'PLANE'   # weight ~ size squared, like a face area


def _pieces(run, closed, world, sharp=60.0):
    """Cuts a run of edges at sharp corners: two edges at the corner of a box are two lines.
    A ring around a low-poly cylinder, down to a hexagon, stays one ring."""
    n = len(run)
    pts = [world @ v.co for v in run]

    def bent(i):
        u, w = pts[i] - pts[i - 1], pts[(i + 1) % n] - pts[i]
        return u.length > 1e-12 and w.length > 1e-12 and u.angle(w) > math.radians(sharp) + 1e-6

    corners = [i for i in range(n) if (closed or 0 < i < n - 1) and bent(i)]
    if not corners:
        return [run]
    if closed:                                             # a closed ring starts and ends at its first corner
        s = corners[0]
        run = run[s:] + run[:s] + [run[s]]
        corners = sorted((i - s) % n for i in corners)[1:]
    cuts = [0] + corners + [len(run) - 1]
    return [run[a:b + 1] for a, b in zip(cuts, cuts[1:])]


def picked_directions(obj, bm, bend=40.0):
    """What is picked in Edit Mode, as axes in world space: [(direction, weight, verts, kind)], or (None, why).
    kind: 'PLANE' the verts lie across the direction, 'LINE' along it, None neither (a curved patch),
    ('AROUND', axis, anchor verts) an edge or vert that tells the turn around an axis: see _around() and _even_out().
    Faces glue into patches over edges that bend less than `bend` degrees, like the cap of a sphere: a patch gives its normal.
    Edges not on picked faces split into runs at their ends, forks and sharp corners: see _line_or_plane().
    Verts on no picked edge or face are one more run."""
    world = obj.matrix_world
    rot = world.to_3x3()
    scale_fix = rot.inverted().transposed() if abs(rot.determinant()) > 1e-12 else rot
    grow = abs(rot.determinant()) ** (2.0 / 3.0)
    shown = [f for f in bm.faces if not f.hide] or [v for v in bm.verts if not v.hide]
    if shown and all(x.select for x in shown):             # by faces: the whole side of a cylinder holds every vert, yet it is a fine pick
        return None, "everything is picked: pick only faces, edges or verts for 1 to 3 axes"
    bm.normal_update()
    out = []

    faces = [f for f in bm.faces if f.select and not f.hide]
    normal, area = {}, {}
    for f in faces:
        n = scale_fix @ f.normal
        if n.length > 1e-9 and f.calc_area() > 0.0:
            normal[f] = n.normalized()
            area[f] = f.calc_area() * grow
    cos_bend = math.cos(math.radians(bend))
    seen = set()
    for f in normal:
        if f in seen:
            continue
        seen.add(f)
        todo, total, size, members = [f], Vector(), 0.0, []
        while todo:                                        # grow the patch over edges while the surface bends gently
            g = todo.pop()
            members.append(g)
            total += normal[g] * area[g]
            size += area[g]
            for e in g.edges:
                for k in e.link_faces:
                    if k in normal and k not in seen and normal[k].dot(normal[g]) >= cos_bend:
                        seen.add(k)
                        todo.append(k)
        verts = list({v for g in members for v in g.verts})
        if total.length >= 0.3 * size:
            d = total.normalized()
            out.append((d, size, verts, 'PLANE' if all(normal[g].dot(d) > 1.0 - 1e-9 for g in members) else None))
        else:                                              # the normals cancel out: a band all around, like the side of a cylinder or a belt on a sphere
            import numpy as np                             # it sets the axis it goes around: the one its normals are all square to
            h = sum(np.outer(tuple(normal[g]), tuple(normal[g])) * area[g] for g in members)
            vals, vecs = np.linalg.eigh(h)
            out.append((Vector(tuple(vecs[:, 0])).normalized(), size, verts, None))

    on_faces = {v for f in faces for v in f.verts}
    # an edge between two picked faces, like a side edge between both picked caps of a cylinder, comes along by itself: not a pick
    edges = [e for e in bm.edges if e.select and not e.hide and not any(f.select for f in e.link_faces)
             and not all(v in on_faces for v in e.verts)]
    links = {}
    for e in edges:
        for v in e.verts:
            links.setdefault(v, []).append(e)
    used = set()

    def walk(v, e):
        run = [v]
        while True:
            used.add(e)
            v = e.other_vert(v)
            run.append(v)
            ahead = [x for x in links[v] if x not in used] if len(links[v]) == 2 else []
            if not ahead:
                return run
            e = ahead[0]

    runs = []
    for v, es in links.items():                            # runs from loose ends and forks: crossing rings split here
        if len(es) != 2:
            for e in es:
                if e not in used:
                    runs += _pieces(walk(v, e), False, world)
    for e in edges:                                        # what is left are closed rings: the walk ends at its first point
        if e not in used:
            runs += _pieces(walk(e.verts[0], e)[:-1], True, world)
    lone = [v for v in bm.verts if v.select and not v.hide and v not in links and not any(f.select for f in v.link_faces)]
    if len(lone) == 1:
        out.append((None, 0.0, lone, 'POINT'))
    else:
        runs.append(lone)
    for run in runs:
        got = _line_or_plane([world @ v.co for v in run])
        if got is not None:
            out.append((got[0], got[1], run, got[2]))
    out = _around(out, world)
    if not out:
        return None, "nothing picked: pick faces, edges or verts for 1 to 3 axes"
    return out, ""


def _around(picks, world, parallel=5.0):
    """A side edge of a cylinder whose cap is picked runs along the axis the cap already gives: as a direction it adds nothing.
    It tells where around that axis it should sit, though: the way from the axis out to it turns to its nearest axis too.
    So a cap and two side edges a quarter apart stand the cylinder up and turn those edges onto X and Y.
    A single picked vert works the same way. The axis comes from the biggest pick that isn't a straight line: a face, a ring, a band."""
    cos_par = math.cos(math.radians(parallel))

    def middle(verts):
        return sum((world @ v.co for v in verts), Vector()) / len(verts)

    anchors = sorted(((d, middle(verts), w, verts) for d, w, verts, kind in picks if kind not in ('LINE', 'POINT') and verts), key=lambda a: -a[2])
    pts = [world @ v.co for _d, _w, verts, _k in picks for v in verts]
    size = max((max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)), default=0.0) if pts else 0.0
    out = []
    for d, w, verts, kind in picks:
        if kind not in ('LINE', 'POINT'):
            out.append((d, w, verts, kind))
            continue
        axis = next((a for a in anchors if kind == 'POINT' or abs(d.dot(a[0])) >= cos_par), None)
        if axis is None:
            if kind == 'LINE':                             # a straight edge on its own: the axis it runs along
                out.append((d, w, verts, kind))
            continue
        out_way = middle(verts) - axis[1]
        out_way -= axis[0] * out_way.dot(axis[0])
        if out_way.length > 1e-5 * size:                   # an edge right on the axis says nothing about the turn
            out.append((out_way.normalized(), max(w, out_way.length ** 2), verts, ('AROUND', axis[0], axis[3])))
    return out


def picked_axes(faces, spread=30.0):
    """Groups picked patches by direction: within spread degrees, or on the opposite side, is one axis. Returns [(direction, area)]."""
    cos_tol = math.cos(math.radians(spread))
    groups = []                                            # [sum of normals by area, area]
    for n, a in sorted(faces, key=lambda f: -f[1]):
        for group in groups:
            d = group[0].normalized()
            if abs(n.dot(d)) >= cos_tol:
                group[0] += n * (a if n.dot(d) > 0.0 else -a)
                group[1] += a
                break
        else:
            groups.append([n * a, a])
    return [(g[0].normalized(), g[1]) for g in groups if g[0].length > 1e-12]


def aim(directions):
    """Rotation that turns each picked direction to its nearest world axis, each to its own one: the smallest turn that does it.
    Two or three directions are fitted together: the turn that misses all of them the least."""
    world = (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
    best = max(itertools.permutations(range(3), len(directions)),
               key=lambda order: sum(abs(d.dot(world[k])) for d, k in zip(directions, order)))
    targets = [world[k] * (1.0 if d.dot(world[k]) >= 0.0 else -1.0) for d, k in zip(directions, best)]
    if len(directions) == 1:
        return directions[0].rotation_difference(targets[0]).to_matrix()
    import numpy as np
    h = sum(np.outer(tuple(d), tuple(t)) for d, t in zip(directions, targets))
    u, _s, vt = np.linalg.svd(h)                           # Kabsch: the best rotation from pairs of directions
    flip = 1.0 if np.linalg.det(vt.T @ u.T) >= 0.0 else -1.0
    return Matrix((vt.T @ np.diag((1.0, 1.0, flip)) @ u.T).tolist())


def bounds(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    pts = [obj.matrix_world @ v.co for v in mesh.vertices]
    evaluated.to_mesh_clear()
    if not pts:
        return None, None
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _bake(obj, context):
    """Bakes rotation and scale into the mesh: the object keeps zeros, the mesh is straight by itself."""
    world = obj.matrix_world
    obj.data.transform(world.to_3x3().to_4x4())
    if world.to_3x3().determinant() < 0.0:                 # a mirrored object: baking the mirror turns the faces inside out
        obj.data.flip_normals()
    obj.matrix_world = Matrix.Translation(world.translation)
    context.view_layer.update()


def straighten(obj, context):
    """Straightens one prop in Object Mode: turns it in place around its middle, then bakes rotation and scale into the mesh.
    A mesh shared with other objects can't be baked: then only the object turns.
    Returns (rotation, sureness) or None if the prop has no faces."""
    depsgraph = context.evaluated_depsgraph_get()
    faces = _world_faces(obj, depsgraph)
    axes, sure = own_axes(faces, obj.matrix_world.to_3x3() @ Vector((1, 0, 0)))
    if axes is None:
        return None
    local = obj.matrix_world.to_3x3()
    ref_up = (local @ Vector((0, 0, 1))).normalized()
    ref_forward = (local @ Vector((0, -1, 0))).normalized()
    rot = straightening(axes, ref_up, ref_forward)
    kids ={child: child.matrix_world.copy() for child in obj.children}     # children (lamps, glass) turn with the prop
    lo, hi = bounds(obj, depsgraph)
    centre = (lo + hi) / 2.0
    spin = Matrix.Translation(centre) @ rot.to_4x4() @ Matrix.Translation(-centre)      # turn around the middle of the prop: it doesn't drift away
    obj.matrix_world = spin @ obj.matrix_world
    context.view_layer.update()
    if obj.type == 'MESH' and obj.data.users == 1:
        _bake(obj, context)
        _even_mesh(obj)
    for child, was in kids.items():                        # children: the same turn as the prop itself
        target = spin @ was
        # computed by hand, not via matrix_world: setting it on a child uses the stale parent matrix and misses
        child.matrix_basis = child.matrix_parent_inverse.inverted() @ obj.matrix_world.inverted() @ target
    context.view_layer.update()
    return rot, sure


def turn_mesh(obj, bm, rot):
    """Edit Mode: turns the mesh by a rotation in world space, in place around the middle of its bounds.
    The object, its origin and its children stay as they were, so Ctrl+Z in Edit Mode brings it all back."""
    world = obj.matrix_world
    if abs(world.determinant()) < 1e-12:
        return False
    pts = [world @ v.co for v in bm.verts]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre = (lo + hi) / 2.0
    spin = Matrix.Translation(centre) @ rot.to_4x4() @ Matrix.Translation(-centre)
    bm.transform(world.inverted() @ spin @ world)
    bmesh.update_edit_mesh(obj.data)
    return True


def _even_out(obj, bm, picks=(), rot=None, most=300000):
    """After a turn, faces, edges and picked rings that now lie along an axis do so up to the last digit Blender keeps.
    That last digit is evened out here: their coordinates along the axis become exactly equal, straight to 0.
    Only rounding is touched: a face counts if it is off by less than a millionth of its size.
    Only when the object itself is not turned: otherwise its world coordinates are rounded by its own rotation anyway."""
    m = obj.matrix_world.to_3x3()
    if any(abs(m[i][j]) > 1e-12 for i in range(3) for j in range(3) if i != j) or len(bm.faces) > most:
        return
    bm.verts.index_update()
    bm.verts.ensure_lookup_table()
    parent = [{}, {}, {}]                                  # per coordinate: verts that must share it, glued like union-find

    def root(i, a):
        p = parent[i]
        while p.setdefault(a, a) != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def glue(i, verts):
        first = root(i, verts[0].index)
        for v in verts[1:]:
            r = root(i, v.index)
            if r != first:
                parent[i][r] = first

    def even(verts, axes):
        lo = [min(v.co[i] for v in verts) for i in range(3)]
        hi = [max(v.co[i] for v in verts) for i in range(3)]
        size = max(h - l for h, l in zip(hi, lo))
        if size > 0.0 and all(hi[i] - lo[i] <= 1e-6 * size for i in axes):
            for i in axes:
                glue(i, verts)

    for d, _w, verts, kind in picks:
        if kind not in ('PLANE', 'LINE') or len(verts) < 2:
            continue
        t = rot @ d
        k = max(range(3), key=lambda i: abs(t[i]))
        if abs(t[k]) >= 1.0 - 1e-6:                        # fitted together with other picks, so not exactly on an axis: leave it
            even(list(verts), (k,) if kind == 'PLANE' else tuple(i for i in range(3) if i != k))
    for f in bm.faces:
        for i in range(3):
            even(list(f.verts), (i,))
    for e in bm.edges:
        for k in range(3):
            even(list(e.verts), tuple(i for i in range(3) if i != k))
    span = max(max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts) for i in range(3)) if bm.verts else 0.0
    for i in range(3):
        groups = {}
        for a in list(parent[i]):
            groups.setdefault(root(i, a), []).append(a)
        kept = []
        for group in groups.values():
            if len(group) < 2:
                continue
            vals = [bm.verts[a].co[i] for a in group]
            wide = max(max(bm.verts[a].co[j] for a in group) - min(bm.verts[a].co[j] for a in group) for j in range(3) if j != i)
            if max(vals) - min(vals) > 1e-5 * wide:        # glued across a gently curved surface: that is shape, not rounding
                continue
            kept.append((sum(vals) / len(vals), group))
        kept.sort(key=lambda g: g[0])
        merged = []                                        # separate bits at the same height, like two arcs of one ring: one height for all
        for mean, group in kept:
            if merged and mean - merged[-1][0] <= 1e-6 * span:
                last_mean, last = merged[-1]
                merged[-1] = ((last_mean * len(last) + mean * len(group)) / (len(last) + len(group)), last + group)
            else:
                merged.append((mean, group))
        for mean, group in merged:
            for a in group:
                bm.verts[a].co[i] = mean
    for d, _w, verts, kind in picks:                       # an edge or vert picked around an axis: right on the line from that axis out
        if not isinstance(kind, tuple) or rot is None:
            continue
        t, a = rot @ d, rot @ kind[1]
        k = max(range(3), key=lambda i: abs(t[i]))
        ka = max(range(3), key=lambda i: abs(a[i]))
        if k == ka or abs(t[k]) < 1.0 - 1e-6 or abs(a[ka]) < 1.0 - 1e-6:
            continue
        j = 3 - k - ka                                     # the one coordinate that must match the middle of the anchor
        centre = sum(v.co[j] for v in kind[2]) / len(kind[2])
        if all(abs(v.co[j] - centre) <= 1e-6 * span for v in verts):
            for v in verts:
                v.co[j] = centre


def _even_mesh(obj):
    """_even_out() for a mesh in Object Mode."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    _even_out(obj, bm)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def _turned(rot):
    """How the prop was turned, by axes: 'Z -26.3°'. Euler XYZ in degrees, zero axes left out."""
    parts = []
    for name, angle in zip("XYZ", rot.to_euler('XYZ')):
        text = ("%.4f" % math.degrees(angle)).rstrip("0").rstrip(".")
        if text not in ("0", "-0"):
            parts.append("%s %s°" % (name, text))
    return " ".join(parts) or "0°"


def _editing(context):
    return [o for o in context.objects_in_mode if o.type == 'MESH'] if context.mode == 'EDIT_MESH' else []


def _leave_edit(context):
    """Drops to Object Mode: in Edit Mode the mesh lives in its edit copy and our changes would be lost. Returns the mode to go back to."""
    obj = context.object
    if obj is None or obj.mode == 'OBJECT':
        return None
    mode = obj.mode
    bpy.ops.object.mode_set(mode='OBJECT')
    return mode


def _back(mode):
    if mode is not None:
        try:
            bpy.ops.object.mode_set(mode=mode)
        except RuntimeError:
            pass


class OBJECT_OT_nano_true_up(bpy.types.Operator):
    bl_idname = "object.nano_true_up"
    bl_label = "Straighten"
    bl_description = ("Stand the prop straight by its own faces. Didn't guess? In Edit Mode pick faces, edges or verts "
                      "for 1 to 3 axes and press again: each turns to its nearest axis")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects) or bool(_editing(context))

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            return self.by_picks(context)
        mode = _leave_edit(context)
        done, notes = 0, []
        for obj in [o for o in context.selected_objects if o.type == 'MESH']:
            result = straighten(obj, context)
            if result is None:
                continue
            rot, sure = result
            done += 1
            notes.append("%s: turned %s%s" % (obj.name, _turned(rot), "" if sure > 0.3 else ", axes unsure: pick them in Edit Mode"))
        _back(mode)
        if not done:
            self.report({'ERROR'}, "No faces in selection: select a mesh")
            return {'CANCELLED'}
        text = "; ".join(notes[:3]) + ("; %d more" % (done - 3) if done > 3 else "")
        self.report({'INFO'}, text)
        return {'FINISHED'}

    def by_picks(self, context):
        """Edit Mode: only the mesh turns, by what is picked."""
        done, notes, errors = 0, [], []
        for obj in _editing(context):
            bm = bmesh.from_edit_mesh(obj.data)
            found, why = picked_directions(obj, bm)
            if found is None:
                errors.append("%s: %s" % (obj.name, why))
                continue
            picked = picked_axes([(d, w) for d, w, _verts, _kind in found])
            if len(picked) > 3:
                errors.append("%s: picks point %d ways: pick for 3 axes at most" % (obj.name, len(picked)))
                continue
            rot = aim([d for d, _w in picked])
            if not turn_mesh(obj, bm, rot):
                errors.append("%s: object has zero scale: fix its scale" % obj.name)
                continue
            _even_out(obj, bm, found, rot)
            bmesh.update_edit_mesh(obj.data)
            done += 1
            notes.append("%s: turned %s by %d picked %s" % (obj.name, _turned(rot), len(picked), "axis" if len(picked) == 1 else "axes"))
        if not done:
            self.report({'ERROR'}, errors[0] if errors else "Nothing picked: pick faces, edges or verts for 1 to 3 axes")
            return {'CANCELLED'}
        text = "; ".join(notes[:3]) + ("; %d more" % (done - 3) if done > 3 else "")
        if errors:
            self.report({'WARNING'}, text + "; " + "; ".join(errors[:2]))
        else:
            self.report({'INFO'}, text)
        return {'FINISHED'}


class VIEW3D_PT_nano_true_up(bpy.types.Panel):
    bl_label = "True Up"
    bl_idname = "VIEW3D_PT_nano_true_up"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Nano Tools"
    bl_order = 20

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.scale_y = 1.4
        row.operator("object.nano_true_up", icon='ORIENTATION_GLOBAL')     # one button: Object Mode by itself, Edit Mode by the picks


classes = (OBJECT_OT_nano_true_up, VIEW3D_PT_nano_true_up)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
