import { useState, useEffect } from 'react';
import { DepthMapConfig } from '../types';
import {
  generateAIDepthMap,
  initiatePKCEFlow,
  exchangeCodeForToken,
  getStoredAccessToken,
  clearAccessToken
} from '../utils/aiDepthMap';

interface ControlsProps {
  config: DepthMapConfig;
  onConfigChange: (config: DepthMapConfig) => void;
  onSourceImageUpload: (file: File) => void;
  onDepthMapUpload: (file: File) => void;
  onExportSTL: () => void;
  hasSourceImage: boolean;
  hasDepthMap: boolean;
  hasMesh: boolean;
}

export default function Controls({
  config,
  onConfigChange,
  onSourceImageUpload,
  onDepthMapUpload,
  onExportSTL,
  hasSourceImage,
  hasDepthMap,
  hasMesh,
}: ControlsProps) {
  const [isGeneratingAI, setIsGeneratingAI] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [sourceImageFile, setSourceImageFile] = useState<File | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAuthenticating, setIsAuthenticating] = useState(false);

  // Check for existing access token on mount
  useEffect(() => {
    const token = getStoredAccessToken();
    if (token) {
      setIsAuthenticated(true);
    }

    // Check for OAuth callback code in URL
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');

    if (code) {
      setIsAuthenticating(true);
      exchangeCodeForToken(code)
        .then(() => {
          setIsAuthenticated(true);
          setAiError(null);
          // Clean up URL
          window.history.replaceState({}, document.title, window.location.pathname);
        })
        .catch((error) => {
          console.error('Token exchange failed:', error);
          setAiError(error instanceof Error ? error.message : 'Authentication failed');
        })
        .finally(() => {
          setIsAuthenticating(false);
        });
    }
  }, []);

  const handleChange = <K extends keyof DepthMapConfig>(
    key: K,
    value: DepthMapConfig[K]
  ) => {
    onConfigChange({ ...config, [key]: value });
  };

  const handleAuthenticate = () => {
    initiatePKCEFlow();
  };

  const handleLogout = () => {
    clearAccessToken();
    setIsAuthenticated(false);
  };

  const handleGenerateAIDepthMap = async () => {
    if (!sourceImageFile) {
      setAiError('Please upload an image first');
      return;
    }

    if (!isAuthenticated) {
      setAiError('Please authenticate with OpenRouter first');
      return;
    }

    setIsGeneratingAI(true);
    setAiError(null);

    try {
      console.log('Generating AI depth map from image...');
      const depthMapDataUrl = await generateAIDepthMap(sourceImageFile);
      console.log('AI depth map generated, loading image...');

      // Convert the data URL to a File object for consistency
      const response = await fetch(depthMapDataUrl);
      const blob = await response.blob();
      const depthMapFile = new File([blob], 'ai-depth-map.png', { type: 'image/png' });

      // Upload the generated depth map as the depth map
      onDepthMapUpload(depthMapFile);
      console.log('AI depth map loaded successfully');
    } catch (error) {
      console.error('Error generating AI depth map:', error);
      setAiError(error instanceof Error ? error.message : 'Failed to generate AI depth map');
    } finally {
      setIsGeneratingAI(false);
    }
  };

  return (
    <div className="controls">
      <h2>Depth Map to STL</h2>

      <section>
        <h3>Source Image</h3>
        <input
          type="file"
          accept="image/*"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              setSourceImageFile(file);
              onSourceImageUpload(file);
            }
          }}
        />
        {hasSourceImage && (
          <p style={{ fontSize: '0.8em', color: '#5a9e6f', marginTop: '8px' }}>
            ✓ Source image loaded
          </p>
        )}
      </section>

      <section>
        <h3>AI Depth Map Generator</h3>

        {isAuthenticating ? (
          <div style={{ padding: '12px', textAlign: 'center', color: '#aaa' }}>
            Completing authentication...
          </div>
        ) : !isAuthenticated ? (
          <>
            <button
              onClick={handleAuthenticate}
              className="ai-auth-btn"
            >
              Sign in with OpenRouter
            </button>
            <p style={{ fontSize: '0.8em', color: '#666', marginTop: '8px' }}>
              Click to authenticate with OpenRouter using OAuth (PKCE)
            </p>
          </>
        ) : (
          <>
            <div style={{ marginBottom: '12px', fontSize: '0.9em', color: '#5a9e6f' }}>
              ✓ Authenticated with OpenRouter
              <button
                onClick={handleLogout}
                style={{
                  marginLeft: '12px',
                  padding: '4px 8px',
                  fontSize: '0.8em',
                  background: 'transparent',
                  border: '1px solid #666',
                  borderRadius: '4px',
                  color: '#aaa',
                  cursor: 'pointer'
                }}
              >
                Logout
              </button>
            </div>
            <button
              onClick={handleGenerateAIDepthMap}
              disabled={!sourceImageFile || isGeneratingAI}
              className="ai-generate-btn"
            >
              {isGeneratingAI ? 'Generating...' : 'Generate AI Depth Map'}
            </button>
            <p style={{ fontSize: '0.8em', color: '#666', marginTop: '8px' }}>
              Upload an image above, then click to generate a depth map using AI.
            </p>
          </>
        )}

        {aiError && <div className="error-message">{aiError}</div>}

        <button onClick={onExportSTL} disabled={!hasMesh} className="export-btn">
          Export STL File
        </button>
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
          Gradient Threshold:
          <input
            type="range"
            value={config.maxSlope}
            onChange={(e) => handleChange('maxSlope', parseFloat(e.target.value))}
            min="0"
            max="3"
            step="0.05"
          />
          <span>{config.maxSlope.toFixed(2)}mm {config.maxSlope === 0 ? '(off)' : '(limit steepness)'}</span>
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
        <h3>Hanging Loop</h3>
        <label>
          <input
            type="checkbox"
            checked={config.addHangingLoop}
            onChange={(e) => handleChange('addHangingLoop', e.target.checked)}
          />
          Add Hanging Loop
        </label>
        {config.addHangingLoop && (
          <>
            <label>
              Hole Diameter (mm):
              <input
                type="number"
                value={config.loopDiameter}
                onChange={(e) => handleChange('loopDiameter', parseFloat(e.target.value))}
                min="1"
                max="10"
                step="0.5"
              />
            </label>
            <label>
              Hole Depth (mm):
              <input
                type="number"
                value={config.loopHeight}
                onChange={(e) => handleChange('loopHeight', parseFloat(e.target.value))}
                min="1"
                max="10"
                step="0.5"
              />
            </label>
            <label>
              Distance from Top (mm):
              <input
                type="number"
                value={config.loopOffset}
                onChange={(e) => handleChange('loopOffset', parseFloat(e.target.value))}
                min="0"
                max="20"
                step="0.5"
              />
            </label>
          </>
        )}
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
        <h3>Text Around Edge</h3>
        <label>
          <input
            type="checkbox"
            checked={config.addText}
            onChange={(e) => handleChange('addText', e.target.checked)}
          />
          Add Text Around Circle
        </label>
        {config.addText && (
          <>
            <label>
              Text:
              <input
                type="text"
                value={config.textContent}
                onChange={(e) => handleChange('textContent', e.target.value)}
                placeholder="Enter text..."
                maxLength={50}
              />
            </label>
            <label>
              Text Size:
              <input
                type="range"
                value={config.textSize}
                onChange={(e) => handleChange('textSize', parseFloat(e.target.value))}
                min="5"
                max="20"
                step="0.5"
              />
              <span>{config.textSize.toFixed(1)}%</span>
            </label>
            <label>
              Text Height (emboss):
              <input
                type="range"
                value={config.textDepth}
                onChange={(e) => handleChange('textDepth', parseFloat(e.target.value))}
                min="0"
                max="1"
                step="0.05"
              />
              <span>{(config.textDepth * 100).toFixed(0)}%</span>
            </label>
          </>
        )}
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

      <section>
        <h3>Manual Depth Map Upload</h3>
        <input
          type="file"
          accept="image/*"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onDepthMapUpload(file);
          }}
        />
        {hasDepthMap && (
          <p style={{ fontSize: '0.8em', color: '#5a9e6f', marginTop: '8px' }}>
            ✓ Depth map loaded
          </p>
        )}
        <p style={{ fontSize: '0.8em', color: '#666', marginTop: '8px' }}>
          Optional: Upload a pre-made depth map instead of generating one with AI
        </p>
      </section>
    </div>
  );
}
