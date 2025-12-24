import { useState, useCallback, useEffect } from 'react';
import Controls from './components/Controls';
import STLViewer from './components/STLViewer';
import { DepthMapConfig, MeshData } from './types';
import { processImage } from './utils/depthMapProcessor';
import { generateMesh } from './utils/meshGenerator';
import { exportSTL } from './utils/stlExporter';
import './App.css';

const defaultConfig: DepthMapConfig = {
  totalHeight: 3,
  minHeight: 0.5,
  wallHeight: 3,
  wallThickness: 2,
  wallPosition: 'flush-bottom',
  depthMode: 'brightness',
  invertDepth: false,
  contrastCurve: 3.0,
  maxSlope: 0.50,
  smoothingRadius: 0, // 0 = off
  cropShape: 'oval',
  cropWidth: 1.0,
  cropHeight: 1.0,
  flipHorizontal: false,
  flipVertical: false,
  rotate180: false,
  resolution: 10,
  addHangingLoop: false,
  loopDiameter: 3,
  loopHeight: 3,
  loopOffset: 2,
  addText: false,
  topText: '',
  bottomText: '',
  textSize: 10,
  textDepth: 1.0,
  textSpacing: 1.0,
};

function App() {
  const [config, setConfig] = useState<DepthMapConfig>(defaultConfig);
  const [sourceImage, setSourceImage] = useState<HTMLImageElement | null>(null);
  const [depthMapImage, setDepthMapImage] = useState<HTMLImageElement | null>(null);
  const [meshData, setMeshData] = useState<MeshData | null>(null);
  const [activeTab, setActiveTab] = useState<'images' | 'output'>('images');

  const handleSourceImageUpload = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        setSourceImage(img);
        // Clear depth map and mesh when new source is uploaded
        setDepthMapImage(null);
        setMeshData(null);
      };
      img.src = e.target?.result as string;
    };
    reader.readAsDataURL(file);
  }, []);

  const handleDepthMapUpload = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        setDepthMapImage(img);
        // Clear mesh when new depth map is uploaded
        setMeshData(null);
      };
      img.src = e.target?.result as string;
    };
    reader.readAsDataURL(file);
  }, []);

  // Auto-convert to STL when depth map or config changes
  useEffect(() => {
    if (!depthMapImage) {
      setMeshData(null);
      return;
    }

    try {
      console.log('Processing depth map image...', depthMapImage.width, depthMapImage.height);
      const processed = processImage(depthMapImage, config);
      console.log('Image processed:', processed);

      console.log('Generating mesh from image data...', processed);
      const mesh = generateMesh(processed, config);
      console.log('Mesh generated:', mesh, 'vertices:', mesh.vertices.length, 'indices:', mesh.indices.length);
      setMeshData(mesh);

      // Auto-switch to output tab when mesh is generated
      setActiveTab('output');
    } catch (error) {
      console.error('Error generating mesh:', error);
      setMeshData(null);
    }
  }, [depthMapImage, config]);

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
          onSourceImageUpload={handleSourceImageUpload}
          onDepthMapUpload={handleDepthMapUpload}
          onExportSTL={handleExportSTL}
          hasSourceImage={!!sourceImage}
          hasDepthMap={!!depthMapImage}
          hasMesh={!!meshData}
        />
      </div>
      <div className="viewer">
        <div className="viewer-tabs">
          <button
            className={`viewer-tab ${activeTab === 'images' ? 'active' : ''}`}
            onClick={() => setActiveTab('images')}
          >
            Images
          </button>
          <button
            className={`viewer-tab ${activeTab === 'output' ? 'active' : ''}`}
            onClick={() => setActiveTab('output')}
            disabled={!meshData}
          >
            Output
          </button>
        </div>
        <div className="viewer-content">
          <STLViewer
            sourceImage={sourceImage}
            depthMapImage={depthMapImage}
            meshData={meshData}
            config={config}
            activeTab={activeTab}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
