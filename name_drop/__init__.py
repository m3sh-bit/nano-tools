# SPDX-FileCopyrightText: 2026 m3shtry
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Name Drop, an add-on for Blender
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
#      name and say it is based on "Name Drop" by m3shtry.
#   3. The name "m3shtry" is not licensed for branding other products.

bl_info = {
    "name": "Name Drop",
    "author": "m3shtry",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Object Mode: F2, or Sidebar > Nano Tools",
    "description": "Batch rename selected objects to name_1, name_2 and on, meshes too, each with its own material copies",
    "category": "Object",
}

# Batch rename
#
# Select objects, press F2, type a name. Objects become name_1, name_2 and
# on, their meshes too. With Copy Materials on, each object gets its own
# copies of its materials, named after it: one material is name_1; several
# are name_1_Metal, name_1_Tape, where the tail is the old material name.
# With it off materials are left alone: shared materials stay shared.
#
# Numbering skips taken names so Blender never adds .001.

import re

import bpy
import rna_keymap_ui


def _clean(name):
    """Material name without the .001 tail and service prefixes."""
    name = re.sub(r"\.\d{3}$", "", name)
    for prefix in ("SK_", "Mobile_", "Wire_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def nano_name_drop(objects, base, materials=True, pad=False, start=1):
    """Renames objects, their meshes and, if asked, materials. Returns (objects, materials copied)."""
    base = base.strip()
    objects = sorted(objects, key=lambda o: (o.name.lower(), o.name))
    taken = {o.name for o in bpy.data.objects if o not in objects}
    width = max(2, len(str(start + len(objects) - 1))) if pad else 1
    copied = 0
    index = start
    for n, obj in enumerate(objects):                     # temp names first: otherwise a new name may be held by a neighbour from the same batch and Blender adds .001
        obj.name = "__renaming_%d" % n
    for obj in objects:
        while True:                                        # nearest free number
            name = "%s_%0*d" % (base, width, index)
            index += 1
            if name not in taken:
                break
        obj.name = name
        if obj.data is not None and obj.data.users == 1:  # mesh shared by several objects: keep its name
            obj.data.name = name
        if materials and obj.data is not None and hasattr(obj.data, "materials"):
            seen = {}
            for slot in obj.material_slots:
                mat = slot.material
                if mat is None:
                    continue
                if mat in seen:                            # same material in two slots: one copy
                    slot.material = seen[mat]
                    continue
                fresh = mat.copy()
                fresh.name = name if len([s for s in obj.material_slots if s.material is not None]) == 1 else "%s_%s" % (name, _clean(mat.name))
                slot.material = fresh
                seen[mat] = fresh
                copied += 1
    return len(objects), copied


class NanoNameDropPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    materials: bpy.props.BoolProperty(name="Copy Materials", default=True,
                                      description="Default for the F2 dialog. Each object gets its own material copies named after it")
    pad: bpy.props.BoolProperty(name="Zero Pad", default=False, description="Numbers like 01, 02: sort right in any app")

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Hotkey: click the field, press a key. Default is F2 in Object Mode", icon='INFO')
        kc = context.window_manager.keyconfigs.addon
        for km, kmi in _keymaps:
            km_user = context.window_manager.keyconfigs.user.keymaps.get(km.name)
            if km_user is None:
                continue
            kmi_user = next((k for k in km_user.keymap_items if k.idname == kmi.idname), None)
            if kmi_user is not None:
                rna_keymap_ui.draw_kmi([], kc, km_user, kmi_user, box.row(), 0)
        col = layout.column(align=True)
        col.prop(self, "materials")
        col.prop(self, "pad")


class OBJECT_OT_nano_name_drop(bpy.types.Operator):
    bl_idname = "object.nano_name_drop"
    bl_label = "Rename Selected"
    bl_description = "Rename selected objects to name_1, name_2 and on, meshes too, with own material copies if you want"
    bl_options = {'REGISTER', 'UNDO'}

    name: bpy.props.StringProperty(name="Name", default="")
    materials: bpy.props.BoolProperty(name="Copy Materials", default=True,
                                      description="On: each object gets its own material copies named after it. Off: materials stay as they are, shared ones stay shared")
    pad: bpy.props.BoolProperty(name="Zero Pad", default=False)
    start: bpy.props.IntProperty(name="Start", default=1, min=0)

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def invoke(self, context, event):
        prefs = context.preferences.addons.get(__name__)
        if prefs is not None:
            self.materials = prefs.preferences.materials
            self.pad = prefs.preferences.pad
        if not self.name:
            active = context.active_object or context.selected_objects[0]
            self.name = re.sub(r"[._]\d+$", "", active.name)      # old name without the number as a hint
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "name")
        layout.prop(self, "materials")
        row = layout.row(align=True)
        row.prop(self, "pad")
        row.prop(self, "start")
        count = len(context.selected_objects)
        layout.label(text="Objects: %d → %s_%s … %s_%s" % (count, self.name or "name", self.start, self.name or "name", self.start + count - 1))

    def execute(self, context):
        if not self.name.strip():
            self.report({'ERROR'}, "Name is empty: type a name")
            return {'CANCELLED'}
        objects, copied = nano_name_drop(list(context.selected_objects), self.name, self.materials, self.pad, self.start)
        self.report({'INFO'}, "Renamed %d objects%s" % (objects, (", copied %d materials" % copied) if copied else ""))
        return {'FINISHED'}


class NanoNameDropSettings(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", default="")
    materials: bpy.props.BoolProperty(name="Copy Materials", default=True,
                                      description="On: each object gets its own material copies named after it. Off: materials stay as they are, shared ones stay shared")
    pad: bpy.props.BoolProperty(name="Zero Pad", default=False)
    start: bpy.props.IntProperty(name="Start", default=1, min=0)


class OBJECT_OT_nano_name_drop_panel(bpy.types.Operator):
    bl_idname = "object.nano_name_drop_panel"
    bl_label = "Rename Selected"
    bl_description = "Rename selected objects by the panel fields"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects) and bool(context.scene.nano_name_drop.name.strip())

    def execute(self, context):
        st = context.scene.nano_name_drop
        objects, copied = nano_name_drop(list(context.selected_objects), st.name, st.materials, st.pad, st.start)
        self.report({'INFO'}, "Renamed %d objects%s" % (objects, (", copied %d materials" % copied) if copied else ""))
        return {'FINISHED'}


class VIEW3D_PT_nano_name_drop(bpy.types.Panel):
    bl_label = "Name Drop"
    bl_idname = "VIEW3D_PT_nano_name_drop"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Nano Tools"
    bl_order = 10

    def draw(self, context):
        layout = self.layout
        st = context.scene.nano_name_drop
        layout.prop(st, "name", text="")
        layout.prop(st, "materials")
        row = layout.row(align=True)
        row.prop(st, "pad")
        row.prop(st, "start")
        count = len(context.selected_objects)
        if count and st.name.strip():
            layout.label(text="%d → %s_%d … %s_%d" % (count, st.name, st.start, st.name, st.start + count - 1))
        else:
            layout.label(text="Select objects, type a name" if not count else "Type a name", icon='INFO')
        row = layout.row()
        row.scale_y = 1.3
        row.operator("object.nano_name_drop_panel", icon='SORTALPHA')
        layout.label(text="Or F2 in Object Mode")


_keymaps = []
classes = (NanoNameDropPreferences, NanoNameDropSettings, OBJECT_OT_nano_name_drop, OBJECT_OT_nano_name_drop_panel, VIEW3D_PT_nano_name_drop)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.nano_name_drop = bpy.props.PointerProperty(type=NanoNameDropSettings)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is not None:
        km = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
        kmi = km.keymap_items.new("object.nano_name_drop", 'F2', 'PRESS')
        _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _keymaps.clear()
    if hasattr(bpy.types.Scene, "nano_name_drop"):
        del bpy.types.Scene.nano_name_drop
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
