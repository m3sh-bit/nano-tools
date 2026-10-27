# True Up

Stand a tilted, turned prop straight.

Part of **Nano Tools**, small everyday add-ons by **m3shtry**. Blender 4.2 or newer.

## Install

Edit > Preferences > Get Extensions, arrow menu at the top right > **Install from Disk**, pick the zip.
Or drag the zip into the Blender window.
To remove it: Get Extensions, find the add-on, its arrow menu > **Uninstall**.

## Where

3D View, Sidebar (**N**), tab **Nano Tools**, panel **True Up**. One button, **Straighten**.

## Object Mode

Select one prop or several, press **Straighten**.

The add-on reads the prop's own axes from its faces: on a man-made object most of the surface faces three directions.
The prop turns in place around its middle so these axes line up with the world. Up is the axis closest to vertical, front is the one closest to -Y.
A prop laid on its side by object rotation stands up the way it was modeled.
Rotation and scale go into the mesh: the object ends up with zero rotation and scale 1.

## Edit Mode

When the guess is wrong, or the shape doesn't show its axes (a sphere, a blob, a sculpt), go to Edit Mode,
pick something for each axis you want, one, two or three of X, Y, Z, any side, and press **Straighten** again:

- a face or a patch of faces: the axis it faces;
- an edge loop or a curved run of edges, like a ring around a sphere: the axis it goes around;
- a straight edge: the axis it runs along;
- three or more verts: the axis across them;
- an edge or a vert along an axis you already picked, like a side edge of a cylinder with its cap picked:
  the turn around that axis, the edge goes onto the nearest axis. A cap and two side edges a quarter apart
  stand the cylinder up and put those edges on X and Y.

Each picked axis turns to its nearest world axis. Picks on opposite sides are one axis.
Only the mesh turns, in place around its middle: the object and its origin stay as they are.

## License

GNU GPL v3 or later, see `LICENSE.txt`. Additional terms in `NOTICE.txt`.

Copyright (C) 2026 m3shtry
