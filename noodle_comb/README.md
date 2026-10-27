# Noodle Comb

Untangle a node tree with one click.

Part of **Nano Tools**, small everyday add-ons by **m3shtry**. Blender 4.2 or newer.

## Install

Edit > Preferences > Get Extensions, arrow menu at the top right > **Install from Disk**, pick the zip.
Or drag the zip into the Blender window.
To remove it: Get Extensions, find the add-on, its arrow menu > **Uninstall**.

## Where

Node Editor, Sidebar (**N**), tab **Nano Tools**, panel **Noodle Comb**.
Works in any node tree: materials, geometry nodes, compositor.

## How it works

Press **Tidy Nodes**.

The output stays on the right. The nodes feeding it go one column to the left, the nodes feeding those one more column left, and so on:
every wire runs left to right. In a column each node sits level with the socket it feeds, so wires cross as little as the tree allows.
Nodes without wires are stacked below.

## Options

- **Right Angles**: wires run only flat and straight, with a reroute point at every corner. Sets **Noodle Curving** to 0 so the corners stay sharp.
- **Reroute Long Wires**: a wire that skips columns goes through reroute points in the gaps, not across other nodes.
- **Selected Only**: tidy only the selected nodes.
- **Column Gap**, **Node Gap**: space between columns and between nodes in a column.
- **Remove Points**: removes the reroute points made by the add-on.
- **Noodle Curving**: Blender's wire curve setting, right in the panel.

## License

GNU GPL v3 or later, see `LICENSE.txt`. Additional terms in `NOTICE.txt`.

Copyright (C) 2026 m3shtry
