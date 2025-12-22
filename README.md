# Depth Map to STL

Convert images to 3D printable STL files with real-time preview.

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
