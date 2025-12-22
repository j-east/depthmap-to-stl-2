export type WallStyle = 'flush-bottom' | 'flush-top' | 'centered';

export type CropShape =
  | { type: 'rectangle' }
  | { type: 'ellipse' }
  | { type: 'polygon'; sides: number; rotation: number };

export interface DepthMapConfig {
  // Output dimensions
  outputWidthMm: number;

  // Heights
  baseThicknessMm: number;    // solid base below everything
  wallHeightMm: number;       // height of walls around the edge
  reliefDepthMm: number;      // z-range of the depth map relief

  // Wall style
  wallStyle: WallStyle;
  wallThicknessMm: number;

  // Crop/mask
  cropShape: CropShape;

  // Depth interpretation
  invertDepth: boolean;       // true = white is high, false = white is low
}

export const DEFAULT_CONFIG: DepthMapConfig = {
  outputWidthMm: 100,
  baseThicknessMm: 2,
  wallHeightMm: 5,
  reliefDepthMm: 3,
  wallStyle: 'flush-bottom',
  wallThicknessMm: 2,
  cropShape: { type: 'rectangle' },
  invertDepth: false,
};

// A simple 3D vertex
export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

// A triangle defined by three vertices
export interface Triangle {
  v1: Vec3;
  v2: Vec3;
  v3: Vec3;
}
