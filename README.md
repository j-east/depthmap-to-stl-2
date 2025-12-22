# Depth Map to STL Converter

A browser-based tool that converts depth map images to 3D printable STL files. No server required - runs entirely in your browser.

## Features

- **Pure client-side** - All processing happens in your browser, no uploads to servers
- **Configurable output**:
  - Output width in mm
  - Base thickness
  - Wall height and thickness
  - Relief depth (z-range of the depth map)
- **Wall styles**:
  - Flush bottom (like a coin/lithophane)
  - Flush top (recessed relief)
  - Centered (framed, picture-style)
- **Crop shapes**:
  - Rectangle
  - Ellipse/Circle
  - Regular polygon (3-20 sides, with rotation)
- **Depth interpretation** - Toggle whether white = high or white = low
- **Binary STL export** - Compact file format ready for slicers

## Usage

1. Visit the [live demo](https://YOUR_USERNAME.github.io/depthmap-to-stl/)
2. Drop a depth map image (PNG, JPG, WebP)
3. Adjust the parameters to your liking
4. Click "Generate STL" to download

## What is a depth map?

A depth map is a grayscale image where brightness represents height/depth. Common sources include:

- AI depth estimation tools
- 3D scanning software
- Photogrammetry exports
- Manually painted heightmaps

## Development

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Deployment

The project includes a GitHub Actions workflow that automatically deploys to GitHub Pages when you push to `main`.

To deploy manually:
1. Run `npm run build`
2. Deploy the `dist/` folder to any static hosting

## License

MIT
