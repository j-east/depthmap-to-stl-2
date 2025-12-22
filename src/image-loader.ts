/**
 * Load an image file and extract grayscale depth values
 */

export interface DepthData {
  width: number;
  height: number;
  values: Float32Array;  // normalized 0-1, row-major
}

/**
 * Load an image from a File and extract grayscale values
 */
export async function loadImageAsDepthData(file: File): Promise<DepthData> {
  const img = await loadImage(file);
  return extractDepthData(img);
}

/**
 * Load an image from a URL and extract grayscale values
 */
export async function loadImageUrlAsDepthData(url: string): Promise<DepthData> {
  const img = await loadImageFromUrl(url);
  return extractDepthData(img);
}

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(img.src);
      resolve(img);
    };
    img.onerror = () => reject(new Error('Failed to load image'));
    img.src = URL.createObjectURL(file);
  });
}

function loadImageFromUrl(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Failed to load image from URL'));
    img.src = url;
  });
}

function extractDepthData(img: HTMLImageElement): DepthData {
  const canvas = document.createElement('canvas');
  canvas.width = img.width;
  canvas.height = img.height;

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error('Could not get 2D context');
  }

  ctx.drawImage(img, 0, 0);
  const imageData = ctx.getImageData(0, 0, img.width, img.height);
  const pixels = imageData.data;

  const values = new Float32Array(img.width * img.height);

  for (let i = 0; i < values.length; i++) {
    const r = pixels[i * 4];
    const g = pixels[i * 4 + 1];
    const b = pixels[i * 4 + 2];
    // Convert to grayscale using luminance formula
    const gray = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    values[i] = gray;
  }

  return {
    width: img.width,
    height: img.height,
    values,
  };
}

/**
 * Get depth value at a specific pixel coordinate
 */
export function getDepthAt(data: DepthData, x: number, y: number): number {
  if (x < 0 || x >= data.width || y < 0 || y >= data.height) {
    return 0;
  }
  return data.values[y * data.width + x];
}
