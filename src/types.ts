export interface DepthMapConfig {
  // Height parameters (in mm)
  totalHeight: number;
  minHeight: number;
  wallHeight: number;
  wallThickness: number;

  // Wall positioning
  wallPosition: 'flush-bottom' | 'centered' | 'flush-top';

  // Depth mapping
  depthMode: 'brightness' | 'red' | 'green' | 'blue' | 'alpha';
  invertDepth: boolean;
  contrastCurve: number; // 0.1 to 10, where 1 is linear, <1 emphasizes highlights, >1 emphasizes shadows
  maxSlope: number; // Maximum height difference between adjacent pixels (hard limit)
  smoothingRadius: number; // Gaussian blur radius to soften transitions (0 = off)

  // Cropping
  cropShape: 'rectangle' | 'circle' | 'oval' | 'polygon';
  cropWidth: number;  // 0-1, percentage of image width
  cropHeight: number; // 0-1, percentage of image height

  // Image orientation
  flipHorizontal: boolean;
  flipVertical: boolean;
  rotate180: boolean;

  // Quality
  resolution: number; // pixels per mm
}

export interface ImageData {
  data: Uint8ClampedArray;
  width: number;
  height: number;
}

export interface MeshData {
  vertices: Float32Array;
  indices: Uint32Array;
}
