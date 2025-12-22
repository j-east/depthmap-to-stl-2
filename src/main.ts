import './style.css';
import type { DepthMapConfig, CropShape, WallStyle } from './types';
import { DEFAULT_CONFIG } from './types';
import type { DepthData } from './image-loader';
import { loadImageAsDepthData } from './image-loader';
import { generateMesh } from './mesh-generator';
import { downloadSTL, getMeshStats } from './stl-exporter';

// Application state
let currentConfig: DepthMapConfig = { ...DEFAULT_CONFIG };
let currentDepthData: DepthData | null = null;
let previewCanvas: HTMLCanvasElement | null = null;

function init() {
  const app = document.querySelector<HTMLDivElement>('#app')!;
  
  app.innerHTML = `
    <div class="container">
      <header>
        <h1>Depth Map to STL</h1>
        <p class="subtitle">Convert depth maps to 3D printable STL files</p>
      </header>

      <div class="main-content">
        <div class="left-panel">
          <div class="drop-zone" id="dropZone">
            <div class="drop-zone-content">
              <svg class="drop-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <p>Drop an image here or click to select</p>
              <p class="hint">Supports PNG, JPG, WebP</p>
            </div>
            <input type="file" id="fileInput" accept="image/*" hidden>
          </div>

          <div class="preview-section" id="previewSection" style="display: none;">
            <h3>Preview</h3>
            <canvas id="previewCanvas"></canvas>
            <div class="image-info" id="imageInfo"></div>
          </div>
        </div>

        <div class="right-panel">
          <div class="config-section">
            <h3>Dimensions</h3>
            
            <div class="config-row">
              <label for="outputWidth">Output Width (mm)</label>
              <input type="number" id="outputWidth" value="${DEFAULT_CONFIG.outputWidthMm}" min="10" max="500" step="1">
            </div>
          </div>

          <div class="config-section">
            <h3>Heights</h3>
            
            <div class="config-row">
              <label for="baseThickness">Base Thickness (mm)</label>
              <input type="number" id="baseThickness" value="${DEFAULT_CONFIG.baseThicknessMm}" min="0.5" max="20" step="0.5">
            </div>
            
            <div class="config-row">
              <label for="wallHeight">Wall Height (mm)</label>
              <input type="number" id="wallHeight" value="${DEFAULT_CONFIG.wallHeightMm}" min="0" max="50" step="0.5">
            </div>
            
            <div class="config-row">
              <label for="reliefDepth">Relief Depth (mm)</label>
              <input type="number" id="reliefDepth" value="${DEFAULT_CONFIG.reliefDepthMm}" min="0.5" max="50" step="0.5">
            </div>
          </div>

          <div class="config-section">
            <h3>Wall Style</h3>
            
            <div class="config-row">
              <label for="wallStyle">Position</label>
              <select id="wallStyle">
                <option value="flush-bottom" ${DEFAULT_CONFIG.wallStyle === 'flush-bottom' ? 'selected' : ''}>Flush Bottom (like a coin)</option>
                <option value="flush-top" ${DEFAULT_CONFIG.wallStyle === 'flush-top' ? 'selected' : ''}>Flush Top (recessed)</option>
                <option value="centered" ${DEFAULT_CONFIG.wallStyle === 'centered' ? 'selected' : ''}>Centered (framed)</option>
              </select>
            </div>
            
            <div class="config-row">
              <label for="wallThickness">Wall Thickness (mm)</label>
              <input type="number" id="wallThickness" value="${DEFAULT_CONFIG.wallThicknessMm}" min="0" max="20" step="0.5">
            </div>
          </div>

          <div class="config-section">
            <h3>Crop Shape</h3>
            
            <div class="config-row">
              <label for="cropShape">Shape</label>
              <select id="cropShape">
                <option value="rectangle">Rectangle</option>
                <option value="ellipse">Ellipse / Circle</option>
                <option value="polygon">Regular Polygon</option>
              </select>
            </div>
            
            <div class="config-row polygon-options" id="polygonOptions" style="display: none;">
              <label for="polygonSides">Number of Sides</label>
              <input type="number" id="polygonSides" value="6" min="3" max="20" step="1">
            </div>
            
            <div class="config-row polygon-options" id="polygonRotationRow" style="display: none;">
              <label for="polygonRotation">Rotation (degrees)</label>
              <input type="number" id="polygonRotation" value="0" min="0" max="360" step="15">
            </div>
          </div>

          <div class="config-section">
            <h3>Depth Interpretation</h3>
            
            <div class="config-row checkbox-row">
              <label>
                <input type="checkbox" id="invertDepth" ${DEFAULT_CONFIG.invertDepth ? 'checked' : ''}>
                Invert depth (white = high)
              </label>
            </div>
          </div>

          <div class="action-section">
            <button id="generateBtn" class="primary-btn" disabled>
              Generate STL
            </button>
            <div class="stats" id="stats"></div>
          </div>
        </div>
      </div>
    </div>
  `;

  setupEventListeners();
}

function setupEventListeners() {
  const dropZone = document.getElementById('dropZone')!;
  const fileInput = document.getElementById('fileInput') as HTMLInputElement;
  const generateBtn = document.getElementById('generateBtn') as HTMLButtonElement;
  const cropShapeSelect = document.getElementById('cropShape') as HTMLSelectElement;

  // File drop handling
  dropZone.addEventListener('click', () => fileInput.click());
  
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
  
  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
  });
  
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer?.files[0];
    if (file) handleFile(file);
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) handleFile(file);
  });

  // Config inputs
  const configInputs = [
    'outputWidth', 'baseThickness', 'wallHeight', 'reliefDepth',
    'wallStyle', 'wallThickness', 'cropShape', 'polygonSides',
    'polygonRotation', 'invertDepth'
  ];

  for (const id of configInputs) {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', updateConfig);
      el.addEventListener('input', updateConfig);
    }
  }

  // Crop shape change - show/hide polygon options
  cropShapeSelect.addEventListener('change', () => {
    const isPolygon = cropShapeSelect.value === 'polygon';
    document.getElementById('polygonOptions')!.style.display = isPolygon ? 'flex' : 'none';
    document.getElementById('polygonRotationRow')!.style.display = isPolygon ? 'flex' : 'none';
    updateConfig();
  });

  // Generate button
  generateBtn.addEventListener('click', generateAndDownload);
}

async function handleFile(file: File) {
  try {
    currentDepthData = await loadImageAsDepthData(file);
    
    // Show preview
    const previewSection = document.getElementById('previewSection')!;
    previewSection.style.display = 'block';
    
    previewCanvas = document.getElementById('previewCanvas') as HTMLCanvasElement;
    renderPreview();
    
    // Show image info
    const imageInfo = document.getElementById('imageInfo')!;
    imageInfo.textContent = `${currentDepthData.width} × ${currentDepthData.height} pixels`;
    
    // Enable generate button
    (document.getElementById('generateBtn') as HTMLButtonElement).disabled = false;
    
    // Update drop zone
    const dropZone = document.getElementById('dropZone')!;
    dropZone.classList.add('has-image');
    dropZone.querySelector('.drop-zone-content p')!.textContent = file.name;

  } catch (error) {
    console.error('Error loading image:', error);
    alert('Failed to load image. Please try another file.');
  }
}

function renderPreview() {
  if (!currentDepthData || !previewCanvas) return;

  const ctx = previewCanvas.getContext('2d')!;
  const { width, height, values } = currentDepthData;

  // Scale preview to fit
  const maxSize = 300;
  const scale = Math.min(maxSize / width, maxSize / height);
  previewCanvas.width = Math.floor(width * scale);
  previewCanvas.height = Math.floor(height * scale);

  const imageData = ctx.createImageData(previewCanvas.width, previewCanvas.height);

  for (let y = 0; y < previewCanvas.height; y++) {
    for (let x = 0; x < previewCanvas.width; x++) {
      const srcX = Math.floor(x / scale);
      const srcY = Math.floor(y / scale);
      const srcIdx = srcY * width + srcX;
      
      let value = values[srcIdx];
      if (currentConfig.invertDepth) {
        value = 1 - value;
      }
      
      const gray = Math.floor(value * 255);
      const dstIdx = (y * previewCanvas.width + x) * 4;
      
      imageData.data[dstIdx] = gray;
      imageData.data[dstIdx + 1] = gray;
      imageData.data[dstIdx + 2] = gray;
      imageData.data[dstIdx + 3] = 255;
    }
  }

  ctx.putImageData(imageData, 0, 0);
}

function updateConfig() {
  currentConfig = {
    outputWidthMm: parseFloat((document.getElementById('outputWidth') as HTMLInputElement).value),
    baseThicknessMm: parseFloat((document.getElementById('baseThickness') as HTMLInputElement).value),
    wallHeightMm: parseFloat((document.getElementById('wallHeight') as HTMLInputElement).value),
    reliefDepthMm: parseFloat((document.getElementById('reliefDepth') as HTMLInputElement).value),
    wallStyle: (document.getElementById('wallStyle') as HTMLSelectElement).value as WallStyle,
    wallThicknessMm: parseFloat((document.getElementById('wallThickness') as HTMLInputElement).value),
    cropShape: getCropShape(),
    invertDepth: (document.getElementById('invertDepth') as HTMLInputElement).checked,
  };

  renderPreview();
}

function getCropShape(): CropShape {
  const shapeType = (document.getElementById('cropShape') as HTMLSelectElement).value;
  
  switch (shapeType) {
    case 'ellipse':
      return { type: 'ellipse' };
    case 'polygon':
      return {
        type: 'polygon',
        sides: parseInt((document.getElementById('polygonSides') as HTMLInputElement).value),
        rotation: parseFloat((document.getElementById('polygonRotation') as HTMLInputElement).value),
      };
    default:
      return { type: 'rectangle' };
  }
}

function generateAndDownload() {
  if (!currentDepthData) return;

  const generateBtn = document.getElementById('generateBtn') as HTMLButtonElement;
  const statsEl = document.getElementById('stats')!;
  
  generateBtn.disabled = true;
  generateBtn.textContent = 'Generating...';

  // Use setTimeout to allow UI to update
  setTimeout(() => {
    try {
      const mesh = generateMesh(currentDepthData!, currentConfig);
      const stats = getMeshStats(mesh);

      statsEl.innerHTML = `
        <p>Triangles: ${stats.triangleCount.toLocaleString()}</p>
        <p>File size: ~${stats.estimatedFileSizeMB.toFixed(2)} MB</p>
        <p>Dimensions: ${(stats.boundingBox.max.x - stats.boundingBox.min.x).toFixed(1)} × ${(stats.boundingBox.max.y - stats.boundingBox.min.y).toFixed(1)} × ${(stats.boundingBox.max.z - stats.boundingBox.min.z).toFixed(1)} mm</p>
      `;

      downloadSTL(mesh, 'depthmap.stl', true);

    } catch (error) {
      console.error('Error generating mesh:', error);
      alert('Failed to generate mesh. The image might be too large.');
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = 'Generate STL';
    }
  }, 50);
}

// Initialize
init();
