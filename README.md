# Depth Map to STL

Convert images to 3D printable STL files with real-time preview.

**Live Demo:** [https://j-east.github.io/depthmap-to-stl-2/](https://j-east.github.io/depthmap-to-stl-2/)

## Features

- **Multiple Depth Modes**: Brightness, RGB channels, or alpha channel
- **Flexible Cropping**: Rectangle, circle, oval, or hexagon shapes
- **Configurable Dimensions**: Control height, wall thickness, and positioning
- **Real-time Preview**: See changes instantly with 3D viewer
- **Export to STL**: Download binary STL files for 3D printing

## Getting Started

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Usage

1. Upload an image file
2. Adjust parameters in the sidebar
3. Preview the 3D model in real-time
4. Export to STL when satisfied

## Parameters

### Depth Mapping
- **Mode**: Choose how to interpret image data as depth
- **Invert Depth**: Flip the depth mapping

### Dimensions
- **Total Height**: Maximum height of the surface relief
- **Min Height**: Minimum height (base of the relief)
- **Wall Height**: Height of the supporting wall
- **Wall Thickness**: Thickness of the outer wall

### Wall Position
- **Flush Bottom**: Like a coin (wall flush with bottom)
- **Centered**: Like a framed picture (relief centered in wall)
- **Flush Top**: Wall flush with top of relief

### Crop Shape
- **Shape**: Rectangle, Circle, Oval, or Hexagon
- **Width/Height**: Size of the crop area

### Quality
- **Resolution**: Pixels per millimeter (higher = more detail)

## Cribbage Board Pipeline (`scripts/`)

A separate Python pipeline that turns NOAA CUDEM topobathy data (Deer Isle /
Penobscot Bay, Maine) into a 3-player cribbage board: real terrain and
bathymetry at 5x exaggeration, a hand-drawn 3-lane course with 121 holes per
lane, and a multicolor 3MF for multi-material printers.

```bash
python3 scripts/path_editor.py       # browser course editor at localhost:8765
python3 scripts/route_prototype.py   # course -> lanes/holes/labels (validated)
python3 scripts/make_board_3mf.py    # -> data/deer_isle_board.3mf (6 colored parts)
PYTHONPATH=.pydeps python3 scripts/make_terrain_stl.py  # plain terrain STL + renders
```

- The editor draws/crops the course over the real chart; the crop maps to a
  255 mm board. Save & Re-route validates hole capacity and collisions.
- `data/waypoints.json` (tracked) is the source of truth: the drawn course,
  crop, and min bend radius. Everything else under `data/` regenerates.
- DEM fetch: NOAA NCEI `DEM_all` ImageServer (CUDEM topobathy, ~3 m).
- Output parts: ocean (below datum), land, 3 lane ribbons, labels — assign
  one filament each in Bambu Studio.
- Python deps: numpy/scipy/Pillow (system), matplotlib in `.pydeps/`
  (`pip install --target .pydeps matplotlib`).
