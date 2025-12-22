import { DepthMapConfig, ImageData, MeshData } from '../types';
import { getDepthValue, isInCropShape } from './depthMapProcessor';

function limitSlope(
  heightMap: (number | null)[][],
  width: number,
  height: number,
  maxSlope: number
): void {
  // Adaptive slope limiting: preserve detail in highlights (subject),
  // only smooth the rolloff into background (like a coin)
  if (maxSlope <= 0) return;

  // Find the height range to determine what's "subject" vs "background"
  let maxHeight = -Infinity;
  let minHeight = Infinity;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (heightMap[y][x] !== null) {
        maxHeight = Math.max(maxHeight, heightMap[y][x]!);
        minHeight = Math.min(minHeight, heightMap[y][x]!);
      }
    }
  }

  const heightRange = maxHeight - minHeight;
  if (heightRange === 0) return;

  // Subject threshold: top 30% of height range is considered "subject" with full detail
  const subjectThreshold = maxHeight - heightRange * 0.3;

  const iterations = 10;

  for (let iter = 0; iter < iterations; iter++) {
    let changed = false;

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (heightMap[y][x] === null) continue;

        const current = heightMap[y][x]!;

        // If this pixel is in the subject area (highlights), skip slope limiting
        // to preserve all detail
        if (current >= subjectThreshold) continue;

        const neighbors = [
          { x: x - 1, y: y },
          { x: x + 1, y: y },
          { x: x, y: y - 1 },
          { x: x, y: y + 1 },
        ];

        // Apply slope limiting, but only constrain downward from higher neighbors
        // This creates smooth rolloff from subject into background
        let minAllowed = -Infinity;

        for (const neighbor of neighbors) {
          if (
            neighbor.x >= 0 &&
            neighbor.x < width &&
            neighbor.y >= 0 &&
            neighbor.y < height &&
            heightMap[neighbor.y][neighbor.x] !== null
          ) {
            const neighborHeight = heightMap[neighbor.y][neighbor.x]!;

            // Only enforce slope limit when neighbor is higher (rolling off from subject)
            if (neighborHeight > current) {
              minAllowed = Math.max(minAllowed, neighborHeight - maxSlope);
            }
          }
        }

        if (minAllowed > current) {
          heightMap[y][x] = minAllowed;
          changed = true;
        }
      }
    }

    if (!changed) break;
  }
}

function applyGaussianSmoothing(
  heightMap: (number | null)[][],
  width: number,
  height: number,
  radius: number
): void {
  // Apply Gaussian blur to soften the result
  if (radius <= 0) return;

  const kernelSize = Math.ceil(radius * 3) * 2 + 1;
  const kernel: number[][] = [];
  const center = Math.floor(kernelSize / 2);
  let kernelSum = 0;

  // Create Gaussian kernel
  for (let ky = 0; ky < kernelSize; ky++) {
    kernel[ky] = [];
    for (let kx = 0; kx < kernelSize; kx++) {
      const dx = kx - center;
      const dy = ky - center;
      const distance = Math.sqrt(dx * dx + dy * dy);
      const weight = Math.exp(-(distance * distance) / (2 * radius * radius));
      kernel[ky][kx] = weight;
      kernelSum += weight;
    }
  }

  // Normalize kernel
  for (let ky = 0; ky < kernelSize; ky++) {
    for (let kx = 0; kx < kernelSize; kx++) {
      kernel[ky][kx] /= kernelSum;
    }
  }

  // Apply blur
  const smoothed: (number | null)[][] = [];

  for (let y = 0; y < height; y++) {
    smoothed[y] = [];
    for (let x = 0; x < width; x++) {
      if (heightMap[y][x] === null) {
        smoothed[y][x] = null;
        continue;
      }

      let sum = 0;
      let weightSum = 0;

      for (let ky = 0; ky < kernelSize; ky++) {
        for (let kx = 0; kx < kernelSize; kx++) {
          const nx = x + kx - center;
          const ny = y + ky - center;

          if (nx >= 0 && nx < width && ny >= 0 && ny < height && heightMap[ny][nx] !== null) {
            sum += heightMap[ny][nx]! * kernel[ky][kx];
            weightSum += kernel[ky][kx];
          }
        }
      }

      smoothed[y][x] = weightSum > 0 ? sum / weightSum : heightMap[y][x];
    }
  }

  // Copy back
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      heightMap[y][x] = smoothed[y][x];
    }
  }
}

export function generateMesh(
  imageData: ImageData,
  config: DepthMapConfig
): MeshData {
  const { width, height } = imageData;
  const vertices: number[] = [];
  const indices: number[] = [];

  // Calculate the actual dimensions in mm based on resolution
  const physicalWidth = width / config.resolution;
  const physicalHeight = height / config.resolution;

  // Build a height map
  const heightMap: (number | null)[][] = [];
  for (let y = 0; y < height; y++) {
    heightMap[y] = [];
    for (let x = 0; x < width; x++) {
      if (isInCropShape(x, y, width, height, config)) {
        const depth = getDepthValue(imageData, x, y, config);
        const heightRange = config.totalHeight - config.minHeight;
        const surfaceHeight = config.minHeight + depth * heightRange;
        heightMap[y][x] = surfaceHeight;
      } else {
        heightMap[y][x] = null;
      }
    }
  }

  // Apply slope limiting if enabled
  if (config.maxSlope > 0) {
    limitSlope(heightMap, width, height, config.maxSlope);
  }

  // Apply Gaussian smoothing if enabled
  if (config.smoothingRadius > 0) {
    applyGaussianSmoothing(heightMap, width, height, config.smoothingRadius);
  }

  // Build vertex map for top surface
  const vertexMap: (number | null)[][] = [];
  for (let y = 0; y < height; y++) {
    vertexMap[y] = [];
    for (let x = 0; x < width; x++) {
      if (heightMap[y][x] !== null) {
        const vx = (x / width - 0.5) * physicalWidth;
        const vy = (y / height - 0.5) * physicalHeight;
        const vz = calculateVertexHeight(heightMap[y][x]!, config);

        vertexMap[y][x] = vertices.length / 3;
        vertices.push(vx, vy, vz);
      } else {
        vertexMap[y][x] = null;
      }
    }
  }

  // Build top surface triangles
  for (let y = 0; y < height - 1; y++) {
    for (let x = 0; x < width - 1; x++) {
      const tl = vertexMap[y][x];
      const tr = vertexMap[y][x + 1];
      const bl = vertexMap[y + 1][x];
      const br = vertexMap[y + 1][x + 1];

      if (tl !== null && tr !== null && bl !== null && br !== null) {
        // Two triangles for this quad
        indices.push(tl, bl, tr);
        indices.push(tr, bl, br);
      }
    }
  }

  // Find bounding box of valid pixels for solid base
  let minX = width, maxX = 0, minY = height, maxY = 0;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (heightMap[y][x] !== null) {
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
      }
    }
  }

  // Build solid rectangular bottom surface (for 3D printability)
  const baseHeight = getBaseHeight(config);
  const bottomVertexOffset = vertices.length / 3;

  // Create bottom vertices matching the top surface
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (heightMap[y][x] !== null) {
        const vx = (x / width - 0.5) * physicalWidth;
        const vy = (y / height - 0.5) * physicalHeight;
        vertices.push(vx, vy, baseHeight);
      }
    }
  }

  // Build bottom surface triangles (inverted winding order)
  for (let y = 0; y < height - 1; y++) {
    for (let x = 0; x < width - 1; x++) {
      const tl = vertexMap[y][x];
      const tr = vertexMap[y][x + 1];
      const bl = vertexMap[y + 1][x];
      const br = vertexMap[y + 1][x + 1];

      if (tl !== null && tr !== null && bl !== null && br !== null) {
        // Add bottom vertex offset and reverse winding
        indices.push(
          tl + bottomVertexOffset,
          tr + bottomVertexOffset,
          bl + bottomVertexOffset
        );
        indices.push(
          tr + bottomVertexOffset,
          br + bottomVertexOffset,
          bl + bottomVertexOffset
        );
      }
    }
  }

  // Build walls (side faces)
  addWalls(vertices, indices, vertexMap, heightMap, width, height, bottomVertexOffset, baseHeight, physicalWidth, physicalHeight, config);

  // Calculate and log mesh bounds for debugging
  let minZ = Infinity, maxZ = -Infinity;
  for (let i = 2; i < vertices.length; i += 3) {
    minZ = Math.min(minZ, vertices[i]);
    maxZ = Math.max(maxZ, vertices[i]);
  }
  console.log('Mesh Z bounds:', { minZ, maxZ, range: maxZ - minZ });

  return {
    vertices: new Float32Array(vertices),
    indices: new Uint32Array(indices),
  };
}

function calculateVertexHeight(surfaceHeight: number, config: DepthMapConfig): number {
  switch (config.wallPosition) {
    case 'flush-bottom':
      // Wall bottom is at 0, surface extends upward
      return config.wallHeight + surfaceHeight;

    case 'centered':
      // Wall is centered, surface in middle
      return config.wallHeight / 2 + surfaceHeight;

    case 'flush-top':
      // Wall top is at max height, surface extends downward
      return config.wallHeight - (config.totalHeight - surfaceHeight);
  }
}

function getBaseHeight(config: DepthMapConfig): number {
  let height: number;
  switch (config.wallPosition) {
    case 'flush-bottom':
      height = 0;
      break;
    case 'centered':
      height = config.wallHeight / 2 - config.totalHeight;
      break;
    case 'flush-top':
      height = config.wallHeight - config.totalHeight;
      break;
  }
  // Ensure base is never below z=0 for 3D printability
  return Math.max(0, height);
}

function addWalls(
  _vertices: number[],
  indices: number[],
  vertexMap: (number | null)[][],
  heightMap: (number | null)[][],
  width: number,
  height: number,
  bottomVertexOffset: number,
  _baseHeight: number,
  _physicalWidth: number,
  _physicalHeight: number,
  _config: DepthMapConfig
): void {

  // Simple approach: create wall quads between all adjacent valid pixels at boundaries

  // Vertical walls (along X axis)
  for (let y = 0; y < height - 1; y++) {
    for (let x = 0; x < width; x++) {
      const top = heightMap[y][x];
      const bottom = heightMap[y + 1][x];

      if (top !== null && bottom !== null) {
        // Both pixels valid - check if this is a boundary edge
        const leftIsValid = x > 0 && heightMap[y][x - 1] !== null && heightMap[y + 1][x - 1] !== null;
        const rightIsValid = x < width - 1 && heightMap[y][x + 1] !== null && heightMap[y + 1][x + 1] !== null;

        const topV = vertexMap[y][x]!;
        const bottomV = vertexMap[y + 1][x]!;
        const topBot = topV + bottomVertexOffset;
        const bottomBot = bottomV + bottomVertexOffset;

        // Add wall on left if needed
        if (!leftIsValid) {
          indices.push(topV, bottomV, topBot);
          indices.push(topBot, bottomV, bottomBot);
        }

        // Add wall on right if needed
        if (!rightIsValid) {
          indices.push(topV, topBot, bottomV);
          indices.push(topBot, bottomBot, bottomV);
        }
      }
    }
  }

  // Horizontal walls (along Y axis)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width - 1; x++) {
      const left = heightMap[y][x];
      const right = heightMap[y][x + 1];

      if (left !== null && right !== null) {
        // Both pixels valid - check if this is a boundary edge
        const topIsValid = y > 0 && heightMap[y - 1][x] !== null && heightMap[y - 1][x + 1] !== null;
        const bottomIsValid = y < height - 1 && heightMap[y + 1][x] !== null && heightMap[y + 1][x + 1] !== null;

        const leftV = vertexMap[y][x]!;
        const rightV = vertexMap[y][x + 1]!;
        const leftBot = leftV + bottomVertexOffset;
        const rightBot = rightV + bottomVertexOffset;

        // Add wall on top if needed
        if (!topIsValid) {
          indices.push(leftV, rightV, leftBot);
          indices.push(leftBot, rightV, rightBot);
        }

        // Add wall on bottom if needed
        if (!bottomIsValid) {
          indices.push(leftV, leftBot, rightV);
          indices.push(leftBot, rightBot, rightV);
        }
      }
    }
  }
}
