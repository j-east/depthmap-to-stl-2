import type { CropShape } from './types';

/**
 * Generate a mask for cropping the depth map
 * Returns a Float32Array where 1 = inside, 0 = outside
 */
export function generateCropMask(
  width: number,
  height: number,
  shape: CropShape
): Float32Array {
  const mask = new Float32Array(width * height);

  const centerX = width / 2;
  const centerY = height / 2;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = y * width + x;
      mask[idx] = isInsideShape(x, y, width, height, centerX, centerY, shape) ? 1 : 0;
    }
  }

  return mask;
}

function isInsideShape(
  x: number,
  y: number,
  width: number,
  height: number,
  centerX: number,
  centerY: number,
  shape: CropShape
): boolean {
  switch (shape.type) {
    case 'rectangle':
      return true; // Everything is inside a rectangle

    case 'ellipse': {
      // Ellipse inscribed in the image bounds
      const rx = width / 2;
      const ry = height / 2;
      const dx = (x - centerX) / rx;
      const dy = (y - centerY) / ry;
      return dx * dx + dy * dy <= 1;
    }

    case 'polygon': {
      return isInsideRegularPolygon(
        x,
        y,
        centerX,
        centerY,
        Math.min(width, height) / 2,
        shape.sides,
        shape.rotation
      );
    }
  }
}

/**
 * Check if a point is inside a regular polygon
 */
function isInsideRegularPolygon(
  x: number,
  y: number,
  centerX: number,
  centerY: number,
  radius: number,
  sides: number,
  rotationDeg: number
): boolean {
  // Generate polygon vertices
  const vertices: [number, number][] = [];
  const rotationRad = (rotationDeg * Math.PI) / 180;

  for (let i = 0; i < sides; i++) {
    const angle = (2 * Math.PI * i) / sides + rotationRad - Math.PI / 2;
    vertices.push([
      centerX + radius * Math.cos(angle),
      centerY + radius * Math.sin(angle),
    ]);
  }

  // Ray casting algorithm
  let inside = false;
  for (let i = 0, j = sides - 1; i < sides; j = i++) {
    const xi = vertices[i][0], yi = vertices[i][1];
    const xj = vertices[j][0], yj = vertices[j][1];

    if (
      yi > y !== yj > y &&
      x < ((xj - xi) * (y - yi)) / (yj - yi) + xi
    ) {
      inside = !inside;
    }
  }

  return inside;
}

/**
 * Get the boundary pixels of the mask (for wall generation)
 * Returns array of [x, y] coordinates that are inside but adjacent to outside
 */
export function getMaskBoundary(
  mask: Float32Array,
  width: number,
  height: number
): [number, number][] {
  const boundary: [number, number][] = [];

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = y * width + x;
      if (mask[idx] === 0) continue;

      // Check if any neighbor is outside
      const hasOutsideNeighbor =
        x === 0 ||
        x === width - 1 ||
        y === 0 ||
        y === height - 1 ||
        mask[idx - 1] === 0 ||
        mask[idx + 1] === 0 ||
        mask[idx - width] === 0 ||
        mask[idx + width] === 0;

      if (hasOutsideNeighbor) {
        boundary.push([x, y]);
      }
    }
  }

  return boundary;
}

/**
 * Get ordered contour of the mask for wall generation
 * Uses marching squares to find the outline
 */
export function getOrderedContour(
  mask: Float32Array,
  width: number,
  height: number
): [number, number][] {
  // Find starting point on the boundary
  let startX = -1, startY = -1;
  
  outer: for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (mask[y * width + x] === 1) {
        // Check if it's on the edge
        if (x === 0 || mask[y * width + (x - 1)] === 0) {
          startX = x;
          startY = y;
          break outer;
        }
      }
    }
  }

  if (startX === -1) {
    return []; // No mask
  }

  // Trace the contour using a simple boundary following algorithm
  const contour: [number, number][] = [];
  const visited = new Set<string>();
  
  // Direction vectors: right, down, left, up
  const dx = [1, 0, -1, 0];
  const dy = [0, 1, 0, -1];
  
  let x = startX;
  let y = startY;
  let dir = 0; // Start going right
  
  const getMask = (px: number, py: number): number => {
    if (px < 0 || px >= width || py < 0 || py >= height) return 0;
    return mask[py * width + px];
  };

  do {
    const key = `${x},${y}`;
    if (!visited.has(key)) {
      contour.push([x, y]);
      visited.add(key);
    }

    // Try to turn left first (to follow the boundary)
    let found = false;
    for (let i = 0; i < 4; i++) {
      const newDir = (dir + 3 + i) % 4; // Try left, straight, right, back
      const nx = x + dx[newDir];
      const ny = y + dy[newDir];
      
      if (getMask(nx, ny) === 1) {
        x = nx;
        y = ny;
        dir = newDir;
        found = true;
        break;
      }
    }

    if (!found) break;

  } while (x !== startX || y !== startY || contour.length < 4);

  return contour;
}
