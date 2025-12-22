import { DepthMapConfig } from '../types';

interface ControlsProps {
  config: DepthMapConfig;
  onConfigChange: (config: DepthMapConfig) => void;
  onImageUpload: (file: File) => void;
  onExportSTL: () => void;
  hasImage: boolean;
}

export default function Controls({
  config,
  onConfigChange,
  onImageUpload,
  onExportSTL,
  hasImage,
}: ControlsProps) {
  const handleChange = <K extends keyof DepthMapConfig>(
    key: K,
    value: DepthMapConfig[K]
  ) => {
    onConfigChange({ ...config, [key]: value });
  };

  return (
    <div className="controls">
      <h2>Depth Map to STL</h2>

      <section>
        <h3>Image</h3>
        <input
          type="file"
          accept="image/*"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onImageUpload(file);
          }}
        />
      </section>

      <section>
        <h3>Depth Mapping</h3>
        <label>
          Mode:
          <select
            value={config.depthMode}
            onChange={(e) =>
              handleChange('depthMode', e.target.value as DepthMapConfig['depthMode'])
            }
          >
            <option value="brightness">Brightness</option>
            <option value="red">Red Channel</option>
            <option value="green">Green Channel</option>
            <option value="blue">Blue Channel</option>
            <option value="alpha">Alpha Channel</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={config.invertDepth}
            onChange={(e) => handleChange('invertDepth', e.target.checked)}
          />
          Invert Depth
        </label>
        <label>
          Contrast Curve:
          <input
            type="range"
            value={config.contrastCurve}
            onChange={(e) => handleChange('contrastCurve', parseFloat(e.target.value))}
            min="0.1"
            max="5"
            step="0.1"
          />
          <span>{config.contrastCurve.toFixed(1)} ({config.contrastCurve < 1 ? 'highlights' : config.contrastCurve > 1 ? 'shadows' : 'linear'})</span>
        </label>
        <label>
          Slope Threshold:
          <input
            type="range"
            value={config.maxSlope}
            onChange={(e) => handleChange('maxSlope', parseFloat(e.target.value))}
            min="0"
            max="3"
            step="0.05"
          />
          <span>{config.maxSlope.toFixed(2)}mm {config.maxSlope === 0 ? '(off)' : '(limit slopes)'}</span>
        </label>
        <label>
          Gaussian Smoothing:
          <input
            type="range"
            value={config.smoothingRadius}
            onChange={(e) => handleChange('smoothingRadius', parseFloat(e.target.value))}
            min="0"
            max="5"
            step="0.1"
          />
          <span>{config.smoothingRadius.toFixed(1)} pixels {config.smoothingRadius === 0 ? '(off)' : '(soften)'}</span>
        </label>
      </section>

      <section>
        <h3>Image Orientation</h3>
        <label>
          <input
            type="checkbox"
            checked={config.flipHorizontal}
            onChange={(e) => handleChange('flipHorizontal', e.target.checked)}
          />
          Flip Horizontal
        </label>
        <label>
          <input
            type="checkbox"
            checked={config.flipVertical}
            onChange={(e) => handleChange('flipVertical', e.target.checked)}
          />
          Flip Vertical
        </label>
        <label>
          <input
            type="checkbox"
            checked={config.rotate180}
            onChange={(e) => handleChange('rotate180', e.target.checked)}
          />
          Rotate 180°
        </label>
      </section>

      <section>
        <h3>Dimensions (mm)</h3>
        <label>
          Total Height:
          <input
            type="number"
            value={config.totalHeight}
            onChange={(e) => handleChange('totalHeight', parseFloat(e.target.value))}
            min="0.1"
            step="0.1"
          />
        </label>
        <label>
          Min Height:
          <input
            type="number"
            value={config.minHeight}
            onChange={(e) => handleChange('minHeight', parseFloat(e.target.value))}
            min="0"
            step="0.1"
          />
        </label>
        <label>
          Wall Height:
          <input
            type="number"
            value={config.wallHeight}
            onChange={(e) => handleChange('wallHeight', parseFloat(e.target.value))}
            min="0"
            step="0.1"
          />
        </label>
        <label>
          Wall Thickness:
          <input
            type="number"
            value={config.wallThickness}
            onChange={(e) => handleChange('wallThickness', parseFloat(e.target.value))}
            min="0.1"
            step="0.1"
          />
        </label>
      </section>

      <section>
        <h3>Wall Position</h3>
        <label>
          <input
            type="radio"
            checked={config.wallPosition === 'flush-bottom'}
            onChange={() => handleChange('wallPosition', 'flush-bottom')}
          />
          Flush Bottom (coin style)
        </label>
        <label>
          <input
            type="radio"
            checked={config.wallPosition === 'centered'}
            onChange={() => handleChange('wallPosition', 'centered')}
          />
          Centered (framed picture)
        </label>
        <label>
          <input
            type="radio"
            checked={config.wallPosition === 'flush-top'}
            onChange={() => handleChange('wallPosition', 'flush-top')}
          />
          Flush Top
        </label>
      </section>

      <section>
        <h3>Crop Shape</h3>
        <label>
          Shape:
          <select
            value={config.cropShape}
            onChange={(e) =>
              handleChange('cropShape', e.target.value as DepthMapConfig['cropShape'])
            }
          >
            <option value="rectangle">Rectangle</option>
            <option value="circle">Circle</option>
            <option value="oval">Oval</option>
            <option value="polygon">Hexagon</option>
          </select>
        </label>
        <label>
          Width:
          <input
            type="range"
            value={config.cropWidth}
            onChange={(e) => handleChange('cropWidth', parseFloat(e.target.value))}
            min="0.1"
            max="1"
            step="0.01"
          />
          <span>{Math.round(config.cropWidth * 100)}%</span>
        </label>
        <label>
          Height:
          <input
            type="range"
            value={config.cropHeight}
            onChange={(e) => handleChange('cropHeight', parseFloat(e.target.value))}
            min="0.1"
            max="1"
            step="0.01"
          />
          <span>{Math.round(config.cropHeight * 100)}%</span>
        </label>
      </section>

      <section>
        <h3>Quality</h3>
        <label>
          Resolution (pixels/mm):
          <input
            type="number"
            value={config.resolution}
            onChange={(e) => handleChange('resolution', parseFloat(e.target.value))}
            min="0.1"
            max="10"
            step="0.1"
          />
        </label>
      </section>

      <button onClick={onExportSTL} disabled={!hasImage} className="export-btn">
        Export STL
      </button>
    </div>
  );
}
