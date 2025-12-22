import { useState, useEffect, useCallback } from 'react';
import Controls from './components/Controls';
import STLViewer from './components/STLViewer';
import { DepthMapConfig, ImageData, MeshData } from './types';
import { processImage } from './utils/depthMapProcessor';
import { generateMesh } from './utils/meshGenerator';
import { exportSTL } from './utils/stlExporter';
import './App.css';

const defaultConfig: DepthMapConfig = {
  totalHeight: 5,
  minHeight: 0.5,
  wallHeight: 10,
  wallThickness: 2,
  wallPosition: 'flush-bottom',
  depthMode: 'brightness',
  invertDepth: false,
  contrastCurve: 1.0,
  maxSlope: 0, // 0 = no limit
  smoothingRadius: 0, // 0 = off
  cropShape: 'rectangle',
  cropWidth: 0.9,
  cropHeight: 0.9,
  flipHorizontal: false,
  flipVertical: false,
  rotate180: true,
  resolution: 2,
};

function App() {
  const [config, setConfig] = useState<DepthMapConfig>(defaultConfig);
  const [imageElement, setImageElement] = useState<HTMLImageElement | null>(null);
  const [imageData, setImageData] = useState<ImageData | null>(null);
  const [meshData, setMeshData] = useState<MeshData | null>(null);

  const handleImageUpload = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        setImageElement(img);
      };
      img.src = e.target?.result as string;
    };
    reader.readAsDataURL(file);
  }, []);

  // Process image when it changes
  useEffect(() => {
    if (!imageElement) {
      setImageData(null);
      return;
    }

    console.log('Processing image...', imageElement.width, imageElement.height);
    const processed = processImage(imageElement, config);
    console.log('Image processed:', processed);
    setImageData(processed);
  }, [imageElement, config]);

  // Generate mesh when image data or config changes
  useEffect(() => {
    if (!imageData) {
      setMeshData(null);
      return;
    }

    try {
      console.log('Generating mesh from image data...', imageData);
      const mesh = generateMesh(imageData, config);
      console.log('Mesh generated:', mesh, 'vertices:', mesh.vertices.length, 'indices:', mesh.indices.length);
      setMeshData(mesh);
    } catch (error) {
      console.error('Error generating mesh:', error);
    }
  }, [imageData, config]);

  const handleExportSTL = useCallback(() => {
    if (!meshData) return;
    exportSTL(meshData, 'depthmap-model.stl');
  }, [meshData]);

  return (
    <div className="app">
      <div className="sidebar">
        <Controls
          config={config}
          onConfigChange={setConfig}
          onImageUpload={handleImageUpload}
          onExportSTL={handleExportSTL}
          hasImage={!!imageElement}
        />
      </div>
      <div className="viewer">
        <STLViewer meshData={meshData} config={config} />
      </div>
    </div>
  );
}

export default App;
