# Name Drop

Batch rename objects together with their meshes and materials.

Part of **Nano Tools**, small everyday add-ons by **m3shtry**. Blender 4.2 or newer.

## Install

Edit > Preferences > Get Extensions, arrow menu at the top right > **Install from Disk**, pick the zip.
Or drag the zip into the Blender window.
To remove it: Get Extensions, find the add-on, its arrow menu > **Uninstall**.

## Where

- **F2** in Object Mode.
- 3D View, Sidebar (**N**), tab **Nano Tools**, panel **Name Drop**.

## How it works

Select objects, press **F2**, type a name, press **OK**.
The objects become `Crate_1`, `Crate_2`, `Crate_3`, in the order of their old names. Their meshes get the same names.

Numbers already taken by other objects are skipped. A mesh used by several objects keeps its name.

## Options

- **Copy Materials**: each object gets its own copies of its materials, named after it.
  One material becomes `Crate_1`, several become `Crate_1_Metal`, `Crate_1_Glass`.
  Off: materials are not touched.
- **Zero Pad**: numbers with a leading zero, `Crate_01`, `Crate_02`.
- **Start**: the first number.

The hotkey and the default ticks for the F2 dialog are in the add-on preferences.

## License

GNU GPL v3 or later, see `LICENSE.txt`. Additional terms in `NOTICE.txt`.

Copyright (C) 2026 m3shtry
