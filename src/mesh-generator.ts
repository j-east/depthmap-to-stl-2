import type { DepthMapConfig, Triangle, Vec3 } from './types';
import type { DepthData } from './image-loader';
import { generateCropMask } from './crop-mask';

export interface GeneratedMesh {
  triangles: Triangle[];
}

/**
 * Generate a complete 3D mesh from depth data and configuration
 */
export function generateMesh(data: DepthData, config: DepthMapConfig): GeneratedMesh {
  const triangles: Triangle[] = [];

  // Calculate scale factor (pixels to mm)
  const scale = config.outputWidthMm / data.width;

  // Generate crop mask
  const mask = generateCropMask(data.width, data.height, config.cropShape);

  // Calculate z positions based on wall style
  const { baseZ, reliefBaseZ, wallTopZ } = calculateZPositions(config);

  // Generate top surface (the relief)
  const topSurfaceTriangles = generateTopSurface(
    data,
    mask,
    config,
    scale,
    reliefBaseZ
  );
  triangles.push(...topSurfaceTriangles);

  // Generate bottom surface (flat base)
  const bottomTriangles = generateBottomSurface(
    data.width,
    data.height,
    mask,
    scale,
    baseZ
  );
  triangles.push(...bottomTriangles);

  // Generate walls around the perimeter
  const wallTriangles = generateWalls(
    data,
    mask,
    config,
    scale,
    baseZ,
    wallTopZ,
    reliefBaseZ
  );
  triangles.push(...wallTriangles);

  return { triangles };
}

/**
 * Calculate the Z positions for different parts of the model
 */
function calculateZPositions(config: DepthMapConfig): {
  baseZ: number;
  reliefBaseZ: number;
  wallTopZ: number;
} {
  const baseZ = 0;
  const wallTopZ = config.baseThicknessMm + config.wallHeightMm;

  let reliefBaseZ: number;
  switch (config.wallStyle) {
    case 'flush-bottom':
      reliefBaseZ = config.baseThicknessMm;
      break;
    case 'flush-top':
      reliefBaseZ = wallTopZ - config.reliefDepthMm;
      break;
    case 'centered':
      const reliefCenter = config.baseThicknessMm + config.wallHeightMm / 2;
      reliefBaseZ = reliefCenter - config.reliefDepthMm / 2;
      break;
  }

  return { baseZ, reliefBaseZ, wallTopZ };
}

/**
 * Generate the top surface triangles from the depth map
 */
function generateTopSurface(
  data: DepthData,
  mask: Float32Array,
  config: DepthMapConfig,
  scale: number,
  reliefBaseZ: number
): Triangle[] {
  const triangles: Triangle[] = [];
  const { width, height, values } = data;

  // Create height map
  const getZ = (x: number, y: number): number => {
    const idx = y * width + x;
    const isInside = mask[idx] === 1;
    
    if (!isInside) {
      // Outside mask - return wall top or base
      return config.baseThicknessMm + config.wallHeightMm;
    }

    let depth = values[idx];
    if (config.invertDepth) {
      depth = 1 - depth;
    }
    return reliefBaseZ + depth * config.reliefDepthMm;
  };

  // Generate triangles for each quad in the grid
  for (let y = 0; y < height - 1; y++) {
    for (let x = 0; x < width - 1; x++) {
      const x0 = x * scale;
      const x1 = (x + 1) * scale;
      const y0 = y * scale;
      const y1 = (y + 1) * scale;

      const z00 = getZ(x, y);
      const z10 = getZ(x + 1, y);
      const z01 = getZ(x, y + 1);
      const z11 = getZ(x + 1, y + 1);

      // Two triangles per quad
      // Triangle 1: top-left
      triangles.push({
        v1: { x: x0, y: y0, z: z00 },
        v2: { x: x1, y: y0, z: z10 },
        v3: { x: x0, y: y1, z: z01 },
      });

      // Triangle 2: bottom-right
      triangles.push({
        v1: { x: x1, y: y0, z: z10 },
        v2: { x: x1, y: y1, z: z11 },
        v3: { x: x0, y: y1, z: z01 },
      });
    }
  }

  return triangles;
}

/**
 * Generate the bottom surface (flat base)
 */
function generateBottomSurface(
  width: number,
  height: number,
  mask: Float32Array,
  scale: number,
  baseZ: number
): Triangle[] {
  const triangles: Triangle[] = [];

  // For the bottom, we only need to cover the bounding box
  // since it's flat and will be against the print bed
  for (let y = 0; y < height - 1; y++) {
    for (let x = 0; x < width - 1; x++) {
      // Check if any corner is inside the mask (need base there)
      const idx00 = y * width + x;
      const idx10 = y * width + (x + 1);
      const idx01 = (y + 1) * width + x;
      const idx11 = (y + 1) * width + (x + 1);

      const anyInside =
        mask[idx00] === 1 ||
        mask[idx10] === 1 ||
        mask[idx01] === 1 ||
        mask[idx11] === 1;

      if (!anyInside) continue;

      const x0 = x * scale;
      const x1 = (x + 1) * scale;
      const y0 = y * scale;
      const y1 = (y + 1) * scale;

      // Bottom faces have reversed winding order
      triangles.push({
        v1: { x: x0, y: y0, z: baseZ },
        v2: { x: x0, y: y1, z: baseZ },
        v3: { x: x1, y: y0, z: baseZ },
      });

      triangles.push({
        v1: { x: x1, y: y0, z: baseZ },
        v2: { x: x0, y: y1, z: baseZ },
        v3: { x: x1, y: y1, z: baseZ },
      });
    }
  }

  return triangles;
}

/**
 * Generate walls around the perimeter
 */
function generateWalls(
  data: DepthData,
  mask: Float32Array,
  config: DepthMapConfig,
  scale: number,
  baseZ: number,
  wallTopZ: number,
  reliefBaseZ: number
): Triangle[] {
  const triangles: Triangle[] = [];
  const { width, height, values } = data;

  // Helper to get surface Z at a point
  const getSurfaceZ = (x: number, y: number): number => {
    const idx = y * width + x;
    let depth = values[idx];
    if (config.invertDepth) depth = 1 - depth;
    return reliefBaseZ + depth * config.reliefDepthMm;
  };

  // Generate walls along the edges of the mask
  // We need to find transitions from inside to outside

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = y * width + x;
      if (mask[idx] === 0) continue;

      // Check each neighbor
      const neighbors = [
        { dx: 1, dy: 0 },  // right
        { dx: -1, dy: 0 }, // left
        { dx: 0, dy: 1 },  // down
        { dx: 0, dy: -1 }, // up
      ];

      for (const { dx, dy } of neighbors) {
        const nx = x + dx;
        const ny = y + dy;

        // Is neighbor outside?
        const neighborOutside =
          nx < 0 ||
          nx >= width ||
          ny < 0 ||
          ny >= height ||
          mask[ny * width + nx] === 0;

        if (!neighborOutside) continue;

        // Generate wall quad between this pixel and the outside
        const surfaceZ = getSurfaceZ(x, y);

        // Wall goes from baseZ to either wallTopZ or surfaceZ depending on position
        // Actually, we want a proper wall that connects the surface to the base

        let wx1: number, wy1: number, wx2: number, wy2: number;
        
        if (dx === 1) { // right edge
          wx1 = (x + 1) * scale;
          wy1 = y * scale;
          wx2 = (x + 1) * scale;
          wy2 = (y + 1) * scale;
        } else if (dx === -1) { // left edge
          wx1 = x * scale;
          wy1 = (y + 1) * scale;
          wx2 = x * scale;
          wy2 = y * scale;
        } else if (dy === 1) { // bottom edge
          wx1 = (x + 1) * scale;
          wy1 = (y + 1) * scale;
          wx2 = x * scale;
          wy2 = (y + 1) * scale;
        } else { // top edge
          wx1 = x * scale;
          wy1 = y * scale;
          wx2 = (x + 1) * scale;
          wy2 = y * scale;
        }

        // Wall from base to top
        const topZ = Math.max(surfaceZ, wallTopZ);
        
        // Wall quad (two triangles)
        triangles.push({
          v1: { x: wx1, y: wy1, z: baseZ },
          v2: { x: wx2, y: wy2, z: baseZ },
          v3: { x: wx1, y: wy1, z: topZ },
        });

        triangles.push({
          v1: { x: wx2, y: wy2, z: baseZ },
          v2: { x: wx2, y: wy2, z: topZ },
          v3: { x: wx1, y: wy1, z: topZ },
        });
      }
    }
  }

  return triangles;
}

/**
 * Calculate the normal vector for a triangle
 */
export function calculateNormal(tri: Triangle): Vec3 {
  const u: Vec3 = {
    x: tri.v2.x - tri.v1.x,
    y: tri.v2.y - tri.v1.y,
    z: tri.v2.z - tri.v1.z,
  };
  const v: Vec3 = {
    x: tri.v3.x - tri.v1.x,
    y: tri.v3.y - tri.v1.y,
    z: tri.v3.z - tri.v1.z,
  };

  const normal: Vec3 = {
    x: u.y * v.z - u.z * v.y,
    y: u.z * v.x - u.x * v.z,
    z: u.x * v.y - u.y * v.x,
  };

  // Normalize
  const len = Math.sqrt(normal.x ** 2 + normal.y ** 2 + normal.z ** 2);
  if (len > 0) {
    normal.x /= len;
    normal.y /= len;
    normal.z /= len;
  }

  return normal;
}
