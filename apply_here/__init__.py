# SPDX-FileCopyrightText: 2026 m3shtry
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Apply Here, an add-on for Blender
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
#      name and say it is based on "Apply Here" by m3shtry.
#   3. The name "m3shtry" is not licensed for branding other products.

bl_info = {
    "name": "Apply Here",
    "author": "m3shtry",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > Nano Tools",
    "description": "Apply one chosen modifier without leaving Edit Mode, the rest stay in the stack",
    "category": "Object",
}

# What it does
#   Applies one chosen modifier without leaving Edit Mode. The rest stay in the stack as they were.
#   The modifier list is in the Nano Tools tab of the Sidebar. The addon takes no hotkeys by itself (Hard Ops
#   has its own menu on Q). The Modifier List button can go to Quick Favorites: RMB → Add to Quick Favorites.
#   The addon preferences have an optional "Q in Edit Mode" tick, off by default.
#   The addon drops to Object Mode for a moment, applies the modifier and goes back to Edit Mode. Selection stays.
#   If the modifier is not first in the stack, Blender applies it to the base mesh as if nothing is above it:
#   exactly "this one only, skip the rest".

import bpy

MENU_ID = "VIEW3D_MT_nano_apply_here"
_keymaps = []


def _icon(mod):
    try:
        return bpy.types.Modifier.bl_rna.properties["type"].enum_items[mod.type].icon
    except (KeyError, AttributeError):
        return 'MODIFIER'


MARK = "nano_apply_here_step"              # mesh property that only our undo step carries


def _undo_push(ob, was_edit, message):
    """Writes the undo step while still in Object Mode. An undo step written in Edit Mode keeps only the mesh,
    not the modifier stack: Ctrl+Z would bring the old shape back but lose the modifier.
    A step written in Object Mode would bring you back to Object Mode on redo, so it carries a mark: see _back_to_edit()."""
    if was_edit:
        ob.data[MARK] = True                  # on the mesh: it is reloaded on every undo out of Edit Mode, the object may be kept as is
    try:
        bpy.ops.ed.undo_push(message=message)
    except RuntimeError:                      # no window, e.g. a background script: there is no undo anyway
        pass
    if MARK in ob.data:
        del ob.data[MARK]


@bpy.app.handlers.persistent
def _back_to_edit(*_args):
    """After undo or redo lands on our step: it was written in Object Mode, but the user was in Edit Mode, so go back there."""
    layer = bpy.context.view_layer
    ob = layer.objects.active if layer is not None else None
    if ob is None or ob.type != 'MESH' or MARK not in ob.data:
        return
    del ob.data[MARK]
    if ob.mode == 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='EDIT')
        except RuntimeError:
            pass


class OBJECT_OT_nano_apply_here(bpy.types.Operator):
    bl_idname = "object.nano_apply_here"
    bl_label = "Apply Modifier"
    bl_description = "Apply only this modifier and stay in Edit Mode. The rest stay in the stack"
    bl_options = {'REGISTER'}             # the undo step is written by hand, in Object Mode: see execute()

    modifier: bpy.props.StringProperty(name="Modifier")

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH' and len(ob.modifiers) > 0

    def execute(self, context):
        ob = context.active_object
        mod = ob.modifiers.get(self.modifier)
        if mod is None:
            self.report({'WARNING'}, "No modifier \"%s\" on %s" % (self.modifier, ob.name))
            return {'CANCELLED'}
        was_edit = ob.mode == 'EDIT'
        first = ob.modifiers[0] == mod
        name = mod.name
        hidden = not mod.show_viewport
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        try:
            if hidden:
                mod.show_viewport = True          # Blender won't apply a modifier that is off
            with context.temp_override(object=ob, active_object=ob):
                bpy.ops.object.modifier_apply(modifier=name, report=False)
            _undo_push(ob, was_edit, "Apply Modifier")
        except RuntimeError as ex:
            msg = str(ex).replace("Error: ", "").strip()
            if hidden and ob.modifiers.get(name):
                ob.modifiers[name].show_viewport = False
            if "shape key" in msg.lower():
                msg = "mesh has shape keys, this modifier can't be applied with them"
            elif "multi-user" in msg.lower():
                msg = "mesh is shared with other objects: make it Single User first"
            elif "disabled" in msg.lower():
                msg = "modifier does nothing right now: check its settings"
            self.report({'WARNING'}, "\"%s\" not applied: %s" % (name, msg))
            return {'CANCELLED'}
        finally:
            if was_edit:
                bpy.ops.object.mode_set(mode='EDIT')
        if first:
            self.report({'INFO'}, "\"%s\" applied" % name)
        else:
            self.report({'INFO'}, "\"%s\" applied to the base mesh as if nothing is above it. The rest stay" % name)
        return {'FINISHED'}


class VIEW3D_MT_nano_apply_here(bpy.types.Menu):
    bl_idname = MENU_ID
    bl_label = "Apply Modifier"

    def draw(self, context):
        lay = self.layout
        ob = context.active_object
        if ob is None or ob.type != 'MESH' or not ob.modifiers:
            lay.label(text="No modifiers", icon='INFO')
            return
        for mod in ob.modifiers:
            op = lay.operator(OBJECT_OT_nano_apply_here.bl_idname, text=mod.name, icon=_icon(mod))
            op.modifier = mod.name


class VIEW3D_PT_nano_apply_here(bpy.types.Panel):
    bl_label = "Apply Here"
    bl_idname = "VIEW3D_PT_nano_apply_here"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Nano Tools"
    bl_order = 30

    def draw(self, context):
        lay = self.layout
        ob = context.active_object
        if ob is None or ob.type != 'MESH':
            lay.label(text="Select a mesh", icon='INFO')
            return
        if not ob.modifiers:
            lay.label(text="No modifiers on %s" % ob.name, icon='INFO')
            return
        col = lay.column(align=True)
        for mod in ob.modifiers:
            row = col.row(align=True)
            row.label(text=mod.name, icon=_icon(mod))
            if not mod.show_viewport:
                row.label(text="", icon='HIDE_ON')
            op = row.operator(OBJECT_OT_nano_apply_here.bl_idname, text="Apply")
            op.modifier = mod.name
        lay.separator()
        lay.label(text="The rest stay in the stack", icon='INFO')
        op = lay.operator("wm.call_menu", text="Modifier List", icon='MODIFIER')
        op.name = MENU_ID
        lay.label(text="RMB the button above →")
        lay.label(text="Add to Quick Favorites")


def _register_keymap():
    _unregister_keymap()
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm else None
    if kc is None:
        return
    km = kc.keymaps.new(name="Mesh", space_type='EMPTY')
    kmi = km.keymap_items.new("wm.call_menu", 'Q', 'PRESS')
    kmi.properties.name = MENU_ID
    _keymaps.append((km, kmi))


def _unregister_keymap():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _keymaps.clear()


def _upd_q(self, context):
    if self.bind_q:
        _register_keymap()
    else:
        _unregister_keymap()


class NanoApplyHerePreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    bind_q: bpy.props.BoolProperty(
        name="Q in Edit Mode opens the modifier list", default=False, update=_upd_q,
        description="Off by default: Q stays with Hard Ops or Quick Favorites. "
                    "Easier: RMB the Modifier List button → Add to Quick Favorites")

    def draw(self, context):
        self.layout.prop(self, "bind_q")
        self.layout.label(text="Off: the addon takes no hotkeys", icon='INFO')


classes = (OBJECT_OT_nano_apply_here, VIEW3D_MT_nano_apply_here, VIEW3D_PT_nano_apply_here, NanoApplyHerePreferences)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _back_to_edit not in handlers:
            handlers.append(_back_to_edit)
    prefs = bpy.context.preferences.addons.get(__name__)
    if prefs is not None and prefs.preferences.bind_q:
        _register_keymap()


def unregister():
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _back_to_edit in handlers:
            handlers.remove(_back_to_edit)
    _unregister_keymap()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
