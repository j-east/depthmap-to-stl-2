import { DepthMapConfig, ImageData } from '../types';

export function processImage(
  imageElement: HTMLImageElement,
  config: DepthMapConfig
): ImageData {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d')!;

  canvas.width = imageElement.width;
  canvas.height = imageElement.height;

  // Apply transformations
  ctx.save();

  // Apply flips using proper transform order
  if (config.flipHorizontal) {
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
  }

  if (config.flipVertical) {
    ctx.translate(0, canvas.height);
    ctx.scale(1, -1);
  }

  ctx.drawImage(imageElement, 0, 0);
  ctx.restore();

  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

  return {
    data: imageData.data,
    width: canvas.width,
    height: canvas.height,
  };
}

export function getDepthValue(
  imageData: ImageData,
  x: number,
  y: number,
  config: DepthMapConfig
): number {
  const index = (y * imageData.width + x) * 4;
  const r = imageData.data[index];
  const g = imageData.data[index + 1];
  const b = imageData.data[index + 2];
  const a = imageData.data[index + 3];

  let depth: number;

  switch (config.depthMode) {
    case 'brightness':
      // Convert to grayscale using luminance formula
      depth = 0.299 * r + 0.587 * g + 0.114 * b;
      break;
    case 'red':
      depth = r;
      break;
    case 'green':
      depth = g;
      break;
    case 'blue':
      depth = b;
      break;
    case 'alpha':
      depth = a;
      break;
  }

  // Normalize to 0-1
  depth = depth / 255;

  // Apply contrast curve (power function)
  // Values < 1 emphasize highlights (brighten shadows)
  // Values > 1 emphasize shadows (darken highlights)
  depth = Math.pow(depth, config.contrastCurve);

  // Invert if needed
  if (config.invertDepth) {
    depth = 1 - depth;
  }

  return depth;
}

export function isInCropShape(
  x: number,
  y: number,
  width: number,
  height: number,
  config: DepthMapConfig
): boolean {
  const centerX = width / 2;
  const centerY = height / 2;

  const cropW = width * config.cropWidth;
  const cropH = height * config.cropHeight;

  const dx = x - centerX;
  const dy = y - centerY;

  switch (config.cropShape) {
    case 'rectangle':
      return Math.abs(dx) <= cropW / 2 && Math.abs(dy) <= cropH / 2;

    case 'circle': {
      const radius = Math.min(cropW, cropH) / 2;
      return dx * dx + dy * dy <= radius * radius;
    }

    case 'oval': {
      const rx = cropW / 2;
      const ry = cropH / 2;
      return (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1;
    }

    case 'polygon':
      // Simple hexagon for now
      return isInHexagon(dx, dy, Math.min(cropW, cropH) / 2);
  }
}

function isInHexagon(dx: number, dy: number, radius: number): boolean {
  const angle = Math.atan2(dy, dx);
  const distance = Math.sqrt(dx * dx + dy * dy);

  // For a regular hexagon, calculate the distance to edge at this angle
  const sideAngle = Math.PI / 3; // 60 degrees
  const angleInSector = ((angle % sideAngle) + sideAngle) % sideAngle;
  const maxDistance = radius / Math.cos(angleInSector - sideAngle / 2);

  return distance <= maxDistance;
}
