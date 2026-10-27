# SPDX-FileCopyrightText: 2026 m3shtry
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Noodle Comb, an add-on for Blender
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
#      name and say it is based on "Noodle Comb" by m3shtry.
#   3. The name "m3shtry" is not licensed for branding other products.

bl_info = {
    "name": "Noodle Comb",
    "author": "m3shtry",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "Node Editor > Sidebar > Nano Tools",
    "description": "Untangle a node tree with one button: columns from the output leftwards, no overlapping nodes, as few crossed links as the tree allows",
    "category": "Node",
}

# What it does
#   Lays nodes out so they can be read. Works in any node editor:
#   materials, geometry nodes, compositor.
#
# How it lays them out
#   The end node (material output) goes to the right. Everything feeding it
#   goes one column to the left, whatever feeds those goes further left, and
#   so on: every wire runs left to right. Inside a column a node sits level
#   with the socket its wire goes into, so wires barely cross. Nodes never
#   overlap.
#
# Long wires
#   A wire that spans several columns goes through reroute points, with room
#   kept for them in every column in between. So it never runs through other
#   nodes. All wires from one socket share one trunk and branch off at their
#   columns. The points can be removed with a button.
#
# What it can't do
#   No crossings at all is impossible when one slider feeds many places at
#   opposite ends of the tree: such a graph can't be drawn flat without
#   crossings at all. Nodes without a single wire are stacked below.

import bpy
from mathutils import Vector

LANE = 14.0           # step between vertical wire runs in one gap
ROW = 22.0            # socket row height
HEAD = 35.0           # node header
EXTRA = {'TEX_IMAGE': 110.0, 'VALTORGB': 110.0, 'RGB': 150.0, 'CURVE_RGB': 220.0, 'CURVE_VEC': 220.0, 'CURVE_FLOAT': 200.0,
         'MAPPING': 170.0, 'TEX_ENVIRONMENT': 80.0, 'VALUE': 10.0, 'NORMAL': 100.0}


def _absolute(node):
    """Node position in tree space: for a node inside a frame it is stored relative to the frame."""
    loc = Vector(node.location)
    parent = node.parent
    while parent is not None:
        loc += Vector(parent.location)
        parent = parent.parent
    return loc


def _place(node, where):
    offset = Vector((0.0, 0.0))
    parent = node.parent
    while parent is not None:
        offset += Vector(parent.location)
        parent = parent.parent
    node.location = (where[0] - offset.x, where[1] - offset.y)


def _rows(sockets):
    return [s for s in sockets if s.enabled and not s.hide]


def node_size(node, ui_scale):
    """Node width and height. In a live window Blender knows them exactly, without one we count by sockets."""
    width = node.width
    if node.type == 'REROUTE':
        return 16.0, 16.0
    if node.dimensions.y > 1.0:
        return max(width, node.dimensions.x / ui_scale), node.dimensions.y / ui_scale
    if node.hide:
        return width, HEAD
    return width, HEAD + ROW * (len(_rows(node.outputs)) + len(_rows(node.inputs))) + EXTRA.get(node.type, 0.0) + 12.0


def _tall(socket):
    """How many rows an input takes: an open vector (like on Mapping) is a label and three fields."""
    return 4 if (socket.type == 'VECTOR' and not socket.hide_value and not socket.is_linked) else 1


def _socket_drop(node, socket, is_output, ui_scale=1.0):
    """How far below the node top the socket sits."""
    if node.type == 'REROUTE':
        return 0.0
    if node.hide:
        return 8.0
    outs = _rows(node.outputs)
    if is_output:
        return HEAD + ROW * (outs.index(socket) if socket in outs else 0)
    ins = _rows(node.inputs)
    above = sum(_tall(s) for s in ins[:ins.index(socket)]) if socket in ins else 0
    if node.dimensions.y > 1.0:                        # in a live window: everything that isn't sockets is node buttons between outputs and inputs
        buttons = max(0.0, node.dimensions.y / ui_scale - (HEAD - ROW / 2.0) - ROW * (len(outs) + sum(_tall(s) for s in ins)) - 13.0)
    else:
        buttons = EXTRA.get(node.type, 0.0)
    return HEAD + ROW * len(outs) + buttons + ROW * above


MARK = "CombPoint"                # reroute points made by this addon are named so: that's how we know them


def _is_point(node):
    return node.type == 'REROUTE' and node.name.startswith(MARK)


class _Point:
    """A slot for a long wire bend in a column in between."""
    type = 'POINT'

    def __init__(self, source_socket):
        self.source_socket = source_socket
        self.node_name = None


def _tag(socket):
    """A socket is stored by node name and its identifier: after nodes are added and removed old socket refs may go stale."""
    return socket.node.name, socket.identifier, socket.is_output


def _find(tree, tag):
    node = tree.nodes.get(tag[0])
    if node is None:
        return None
    return next((sock for sock in (node.outputs if tag[2] else node.inputs) if sock.identifier == tag[1]), None)


def dissolve_points(tree, names=None):
    """Removes the reroute points made by the addon and wires straight again, as it was.
    names: node names to search among. Without it searches the whole tree."""
    removed = 0
    while True:
        point = next((n for n in tree.nodes if _is_point(n) and (names is None or n.name in names)), None)
        if point is None:
            break
        source = _tag(point.inputs[0].links[0].from_socket) if point.inputs[0].is_linked else None
        targets = [_tag(link.to_socket) for link in point.outputs[0].links]
        tree.nodes.remove(point)
        if source is not None:
            for target in targets:
                a, b = _find(tree, source), _find(tree, target)
                if a is not None and b is not None:
                    tree.links.new(a, b)
        removed += 1
    return removed


def arrange(tree, nodes, gap_x=70.0, gap_y=30.0, ui_scale=1.0, points=True, square=False):
    """Lays nodes out. Returns (columns, nodes in the layout, loose nodes, points made).
    square: wires go only horizontally and vertically, a point at every corner."""
    points = points or square
    names = [n.name for n in nodes]                    # after points are removed their old refs must not be touched: work by names
    dissolve_points(tree, set(names))
    nodes = [tree.nodes[name] for name in names if name in tree.nodes and tree.nodes[name].type != 'FRAME']
    if not nodes:
        return 0, 0, 0, 0
    inside = set(nodes)
    size = {n: node_size(n, ui_scale) for n in nodes}
    start = {n: _absolute(n) for n in nodes}
    feeds = {n: [] for n in nodes}                     # node -> [(target, input socket, output socket)]
    fed = {n: 0 for n in nodes}
    for link in tree.links:
        a, b = link.from_node, link.to_node
        if a in inside and b in inside and a is not b:
            feeds[a].append((b, link.to_socket, link.from_socket))
            fed[b] += 1
    wired = [n for n in nodes if feeds[n] or fed[n]]
    loose = [n for n in nodes if not feeds[n] and not fed[n]]

    # node column: one left of the leftmost node it feeds. End nodes are in column 0
    column = {}

    def depth(node, trail):
        if node in column:
            return column[node]
        if node in trail:                              # a loop in the tree: break it here
            return 0
        trail.add(node)
        column[node] = 1 + max((depth(target, trail) for target, _i, _o in feeds[node]), default=-1)
        trail.discard(node)
        return column[node]

    import sys
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(limit, len(nodes) * 4 + 1000))
    try:
        for node in wired:
            depth(node, set())
    finally:
        sys.setrecursionlimit(limit)
    count = (max(column.values()) + 1) if column else 0
    layers = [[n for n in wired if column[n] == k] for k in range(count)]

    # a long wire is cut into one-column pieces: room is kept for it in every column in between.
    # All wires from one socket share one trunk and branch off at their columns
    edges = []                                         # (left vertex, right vertex, output socket, input socket)
    trunks = []
    for u in wired:
        by_socket = {}
        for target, to_socket, from_socket in feeds[u]:
            by_socket.setdefault(from_socket, []).append((target, to_socket))
        for from_socket, targets in by_socket.items():
            nearest = min(column[t] for t, _s in targets)
            chain = {}
            previous, previous_socket = u, from_socket
            for k in range(column[u] - 1, nearest, -1):
                point = _Point(from_socket)
                column[point] = k
                size[point] = (16.0, 16.0)
                start[point] = Vector((0.0, start[u].y))
                layers[k].append(point)
                edges.append((previous, point, previous_socket, None))
                chain[k] = point
                previous, previous_socket = point, None
            if chain:
                trunks.append((u, from_socket, chain, targets))
            for target, to_socket in targets:
                k = column[target]
                if k == column[u] - 1:
                    edges.append((u, target, from_socket, to_socket))
                else:
                    edges.append((chain[k + 1], target, None, to_socket))

    def out_part(v, socket):                           # where the socket sits on the vertex, as a share of its height
        if v.type == 'POINT' or socket is None:
            return 0.5
        return _socket_drop(v, socket, True) / max(size[v][1], 1.0)

    def in_part(v, socket):
        if v.type == 'POINT' or socket is None:
            return 0.5
        return _socket_drop(v, socket, False) / max(size[v][1], 1.0)

    between = [[] for _ in range(max(count - 1, 0))]   # wires between columns k+1 and k
    for a, b, so, si in edges:
        between[column[b]].append((a, b, so, si))
    left_of = {}
    right_of = {}
    for a, b, so, si in edges:
        right_of.setdefault(a, []).append((b, si))
        left_of.setdefault(b, []).append((a, so))

    # order in columns: many passes back and forth, keep the one with the fewest crossings
    for k in range(count):
        layers[k].sort(key=lambda v: -start[v].y)

    def crossed(order):
        where = {v: i for layer in order for i, v in enumerate(layer)}
        total = 0
        for gap in between:
            ends = sorted((where[a] + out_part(a, so), where[b] + in_part(b, si)) for a, b, so, si in gap)
            seen = []
            import bisect
            for _left, right_end in ends:              # inversion count: how many wires lie "out of order"
                total += len(seen) - bisect.bisect_right(seen, right_end)
                bisect.insort(seen, right_end)
        return total

    best, best_count = [list(layer) for layer in layers], crossed(layers)
    for sweep in range(24):
        where = {v: i for layer in layers for i, v in enumerate(layer)}
        if sweep % 2 == 0:                             # right to left: each column follows the one to its right
            for k in range(1, count):
                key = {}
                for v in layers[k]:
                    marks = [where[b] + in_part(b, si) for b, si in right_of.get(v, [])]
                    key[v] = sum(marks) / len(marks) if marks else where[v]
                layers[k].sort(key=lambda v: key[v])
                for i, v in enumerate(layers[k]):
                    where[v] = i
        else:                                          # left to right
            for k in range(count - 2, -1, -1):
                key = {}
                for v in layers[k]:
                    marks = [where[a] + out_part(a, so) for a, so in left_of.get(v, [])]
                    key[v] = sum(marks) / len(marks) if marks else where[v]
                layers[k].sort(key=lambda v: key[v])
                for i, v in enumerate(layers[k]):
                    where[v] = i
        now = crossed(layers)
        if now < best_count:
            best, best_count = [list(layer) for layer in layers], now
    layers = best

    anchor = max(wired, key=lambda n: (column[n] == 0, start[n].x)) if wired else nodes[0]
    right = start[anchor].x + size[anchor][0]
    top_line = max(start[n].y for n in nodes)

    def space(v):
        return gap_y if v.type != 'POINT' else gap_y * 0.4

    y_top = {}
    for k in range(count):                             # plain stacks first
        cursor = top_line
        for v in layers[k]:
            y_top[v] = cursor
            cursor -= size[v][1] + space(v)

    def settle(k, want):
        """Puts the column's vertices as close as it can to the wanted heights, keeping order and never overlapping."""
        layer = layers[k]
        cursor = None
        for v in layer:
            target = want.get(v, y_top[v])
            y_top[v] = target if cursor is None else min(target, cursor)
            cursor = y_top[v] - size[v][1] - space(v)
        drift = [want[v] - y_top[v] for v in layer if v in want]
        if drift:
            shift = sum(drift) / len(drift)
            for v in layer:
                y_top[v] += shift

    def drop_out(v, socket):
        return 8.0 if v.type == 'POINT' else _socket_drop(v, socket, True, ui_scale)

    def drop_in(v, socket):
        return 8.0 if v.type == 'POINT' else _socket_drop(v, socket, False, ui_scale)

    for sweep in range(7):                             # a few passes back and forth, the last one right to left
        if sweep % 2 == 0:
            for k in range(1, count):
                want = {}
                for v in layers[k]:
                    marks = [y_top[b] - drop_in(b, si) + drop_out(v, so) for (b, si), so in zip(right_of.get(v, []), [e[2] for e in edges if e[0] is v])]
                    if marks:
                        want[v] = sum(marks) / len(marks)
                settle(k, want)
        else:
            for k in range(count - 2, -1, -1):
                want = {}
                for v in layers[k]:
                    marks = [y_top[a] - drop_out(a, so) + drop_in(v, si) for (a, so), si in zip(left_of.get(v, []), [e[3] for e in edges if e[1] is v])]
                    if marks:
                        want[v] = sum(marks) / len(marks)
                settle(k, want)
    if anchor in y_top:                                # the output node stays where it was: a second press moves nothing
        lift = start[anchor].y - y_top[anchor]
        for v in y_top:
            y_top[v] += lift
    # vertical runs: wires from one socket share one, the rest need their own in the gap
    stems = [[] for _ in between]                      # per gap: (source vertex, socket, output height, [(target vertex, socket, input height)])
    if square:
        for k, gap in enumerate(between):
            groups = {}
            for a, b, so, si in gap:
                key_so = so if a.type == 'POINT' else _tag(so)             # sockets are stored by name right away, before new nodes appear
                groups.setdefault((a, key_so), []).append((b, si if b.type == 'POINT' else _tag(si), y_top[b] - drop_in(b, si)))
            for (a, so), targets in groups.items():
                level = y_top[a] - (8.0 if a.type == 'POINT' else drop_out(a, _find(tree, so)))
                if any(abs(y - level) > 1.5 for _b, _si, y in targets):
                    stems[k].append((a, so, level, targets))
            # right-to-left order of runs is picked so that wires into them cross other runs less often
            down = sorted((st for st in stems[k] if sum(y for _b, _s, y in st[3]) / len(st[3]) <= st[2]), key=lambda st: -st[2])
            up = sorted((st for st in stems[k] if sum(y for _b, _s, y in st[3]) / len(st[3]) > st[2]), key=lambda st: st[2])
            stems[k] = down + up
    x_left, edge = {}, right
    lane_x = [[] for _ in between]
    for k in range(count):
        wide = max(size[v][0] for v in layers[k])
        edge -= wide
        for v in layers[k]:
            x_left[v] = edge + (wide - size[v][0])     # pressed to the right edge of the column: outputs in one line
        if k < len(between):
            if square:
                room = max(gap_x, 2.0 * LANE + LANE * len(stems[k]))
                lane_x[k] = [edge - LANE * 1.5 - LANE * i for i in range(len(stems[k]))]
                edge -= room
            else:
                edge -= gap_x * (1.0 + 0.02 * min(len(between[k]), 25))      # the more wires in a gap, the wider it is
    for n in wired:
        _place(n, (x_left[n], y_top[n]))
    # reroute points: real reroute nodes on the kept slots, wires are switched through them
    made = 0
    if points:
        plan = []                                      # write everything down by names first, then create: new nodes must not break refs
        for u, from_socket, chain, targets in trunks:
            far = [(column[target], _tag(to_socket)) for target, to_socket in targets if column[target] < column[u] - 1]
            plan.append((_tag(from_socket), [(k, (x_left[chain[k]] + 8.0, y_top[chain[k]] - 8.0)) for k in sorted(chain, reverse=True)], far, chain))
        for source, spots, far, chain in plan:
            previous = source
            at = {}
            for k, where in spots:
                node = tree.nodes.new("NodeReroute")
                node.name = MARK
                node.location = where
                at[k] = node.name
                chain[k].node_name = node.name
                a = _find(tree, previous)
                if a is not None:
                    tree.links.new(a, tree.nodes[at[k]].inputs[0])
                previous = (at[k], tree.nodes[at[k]].outputs[0].identifier, True)
                made += 1
            for k, target in far:
                a, b = _find(tree, (at[k + 1], tree.nodes[at[k + 1]].outputs[0].identifier, True)), _find(tree, target)
                if a is not None and b is not None:
                    tree.links.new(a, b)

    # right angles: from the socket flat to its vertical run, along it to the target height, and flat into the target
    if square:
        def socket_of(v, socket, output):
            if v.type == 'POINT':
                node = tree.nodes.get(getattr(v, "node_name", "") or "")
                if node is None:
                    return None
                return (node.name, node.outputs[0].identifier, True) if output else (node.name, node.inputs[0].identifier, False)
            return socket                              # already stored by name

        todo = []
        for k, gap_stems in enumerate(stems):
            for lane, (a, so, level, targets) in enumerate(gap_stems):
                source = socket_of(a, so, True)
                ends = [(y, socket_of(b, si, False)) for b, si, y in targets]
                if source is not None:
                    todo.append((lane_x[k][lane], level, source, [e for e in ends if e[1] is not None]))
        for x, level, source, ends in todo:
            def point_at(y, feed):
                node = tree.nodes.new("NodeReroute")
                node.name = MARK
                node.location = (x, y)
                name = node.name
                a = _find(tree, feed)
                if a is not None:
                    tree.links.new(a, tree.nodes[name].inputs[0])
                return (name, tree.nodes[name].outputs[0].identifier, True)

            straight = [e for e in ends if abs(e[0] - level) <= 1.5]
            above = sorted((e for e in ends if e[0] - level > 1.5), key=lambda e: e[0])
            below = sorted((e for e in ends if level - e[0] > 1.5), key=lambda e: -e[0])
            corner = point_at(level, source)
            made += 1
            for target in straight:
                a, b = _find(tree, corner), _find(tree, target[1])
                if a is not None and b is not None:
                    tree.links.new(a, b)
            for branch in (above, below):              # up and down from the corner: a point at the height of each target
                feed, last = corner, None
                for y, target in branch:
                    if last is None or abs(y - last) > 1.5:
                        feed = point_at(y, feed)
                        made += 1
                        last = y
                    a, b = _find(tree, feed), _find(tree, target)
                    if a is not None and b is not None:
                        tree.links.new(a, b)
    # loose nodes: in rows below the layout
    if loose:
        floor = min((y_top[v] - size[v][1] for v in y_top), default=top_line) - gap_y * 3.0
        left = min((x_left[v] for v in x_left), default=start[loose[0]].x)
        span = max(right - left, 800.0)
        x, y, tall = left, floor, 0.0
        for n in sorted(loose, key=lambda n: (n.type, n.name)):
            w, h = size[n]
            if x + w > left + span and x > left:
                x, y, tall = left, y - tall - gap_y, 0.0
            _place(n, (x, y))
            x += w + gap_x * 0.5
            tall = max(tall, h)
    return count, len(wired), len(loose), made


# --------------------------------------------------------------------------
#  Operator and panel
# --------------------------------------------------------------------------

class NanoNoodleCombSettings(bpy.types.PropertyGroup):
    gap_x: bpy.props.FloatProperty(name="Column Gap", default=70.0, min=10.0, soft_max=300.0,
                                   description="Space between node columns. Wider gives wires more room")
    gap_y: bpy.props.FloatProperty(name="Node Gap", default=30.0, min=0.0, soft_max=200.0, description="Space between nodes in one column")
    points: bpy.props.BoolProperty(name="Reroute Long Wires", default=True,
                                   description="A wire that spans several columns goes through reroute points in the gaps between nodes: "
                                               "so it never runs through other nodes. The points don't change how the tree works")
    square: bpy.props.BoolProperty(name="Right Angles", default=False,
                                   description="Wires go only horizontally and vertically, a point at every corner. Lots of points. "
                                               "Sets Noodle Curving in Blender preferences to 0, or the corners get rounded")
    only_selected: bpy.props.BoolProperty(name="Selected Only", default=False,
                                          description="Tidy only the selected nodes, leave the rest alone. Off: the whole tree")


class NODE_OT_nano_noodle_comb(bpy.types.Operator):
    bl_idname = "node.nano_noodle_comb"
    bl_label = "Tidy Nodes"
    bl_description = "Lay nodes out in columns from the output leftwards: no overlaps and the fewest crossed wires"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == 'NODE_EDITOR' and space.edit_tree is not None

    def execute(self, context):
        tree = context.space_data.edit_tree
        st = context.scene.nano_noodle_comb
        nodes = [n for n in tree.nodes if n.select] if st.only_selected else list(tree.nodes)
        if st.only_selected and len(nodes) < 2:
            self.report({'WARNING'}, "Select at least two nodes or turn off Selected Only")
            return {'CANCELLED'}
        columns, wired, loose, made = arrange(tree, nodes, st.gap_x, st.gap_y, context.preferences.system.ui_scale, st.points, st.square)
        flattened = False
        if st.square:
            try:
                theme = context.preferences.themes[0].node_editor
                if theme.noodle_curving != 0:
                    theme.noodle_curving = 0                  # straight wires: a shared node editor setting
                    flattened = True
            except Exception:
                pass
        try:
            bpy.ops.node.view_all()
        except RuntimeError:
            pass
        self.report({'INFO'}, "Tidied %d nodes in %d columns%s%s%s" % (wired, columns, (", %d reroutes on long wires" % made) if made else "",
                                                                       (", %d loose nodes stacked below" % loose) if loose else "",
                                                                       ". Noodle Curving set to 0" if flattened else ""))
        return {'FINISHED'}


class NODE_OT_nano_noodle_comb_clear(bpy.types.Operator):
    bl_idname = "node.nano_noodle_comb_clear"
    bl_label = "Remove Points"
    bl_description = "Remove the reroute points this addon made: wires go straight again. Nodes stay where they are"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == 'NODE_EDITOR' and space.edit_tree is not None

    def execute(self, context):
        removed = dissolve_points(context.space_data.edit_tree)
        self.report({'INFO'}, "Removed %d points" % removed)
        return {'FINISHED'}


class NODE_PT_nano_noodle_comb(bpy.types.Panel):
    bl_label = "Noodle Comb"
    bl_idname = "NODE_PT_nano_noodle_comb"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Nano Tools"
    bl_order = 10

    def draw(self, context):
        layout = self.layout
        st = context.scene.nano_noodle_comb
        row = layout.row()
        row.scale_y = 1.6
        row.operator("node.nano_noodle_comb", text="Tidy Nodes", icon='NODETREE')
        layout.prop(st, "square")
        sub = layout.row()
        sub.enabled = not st.square
        sub.prop(st, "points")
        layout.prop(st, "only_selected")
        col = layout.column(align=True)
        col.prop(st, "gap_x")
        col.prop(st, "gap_y")
        layout.operator("node.nano_noodle_comb_clear", text="Remove Points", icon='X')
        try:
            layout.prop(context.preferences.themes[0].node_editor, "noodle_curving", text="Noodle Curving")
        except Exception:
            pass


classes = (NanoNoodleCombSettings, NODE_OT_nano_noodle_comb, NODE_OT_nano_noodle_comb_clear, NODE_PT_nano_noodle_comb)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.nano_noodle_comb = bpy.props.PointerProperty(type=NanoNoodleCombSettings)


def unregister():
    if hasattr(bpy.types.Scene, "nano_noodle_comb"):
        del bpy.types.Scene.nano_noodle_comb
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
