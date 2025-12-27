import { useState, useRef, useEffect } from 'react';

interface ImageCropperProps {
  image: HTMLImageElement;
  containerWidth: number;
  containerHeight: number;
  onCropComplete: (croppedImage: HTMLImageElement) => void;
  applyRef: React.MutableRefObject<(() => void) | null>;
  resetRef: React.MutableRefObject<(() => void) | null>;
}

interface CropArea {
  x: number;
  y: number;
  width: number;
  height: number;
}

type DragMode = 'move' | 'resize-tl' | 'resize-tr' | 'resize-bl' | 'resize-br' | 'resize-t' | 'resize-b' | 'resize-l' | 'resize-r' | null;

export default function ImageCropper({ image, containerWidth, containerHeight, onCropComplete, applyRef, resetRef }: ImageCropperProps) {
  // Calculate initial crop area
  const getInitialCropArea = (): CropArea => {
    const aspect = image.width / image.height;
    const containerAspect = containerWidth / containerHeight;

    let displayWidth, displayHeight;
    if (aspect > containerAspect) {
      displayWidth = containerWidth;
      displayHeight = containerWidth / aspect;
    } else {
      displayHeight = containerHeight;
      displayWidth = containerHeight * aspect;
    }

    const cropWidth = displayWidth * 0.8;
    const cropHeight = displayHeight * 0.8;

    return {
      x: (containerWidth - cropWidth) / 2,
      y: (containerHeight - cropHeight) / 2,
      width: cropWidth,
      height: cropHeight,
    };
  };

  const [cropArea, setCropArea] = useState<CropArea>(getInitialCropArea());

  const [dragMode, setDragMode] = useState<DragMode>(null);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [aspectRatioLocked, setAspectRatioLocked] = useState(true);
  const overlayRef = useRef<HTMLDivElement>(null);

  const getMousePos = (e: React.MouseEvent<HTMLDivElement> | MouseEvent): { x: number; y: number } => {
    if (!overlayRef.current) return { x: 0, y: 0 };
    const rect = overlayRef.current.getBoundingClientRect();
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  };

  const getDragMode = (mouseX: number, mouseY: number): DragMode => {
    const handleSize = 12;
    const edgeThreshold = 8;
    const { x, y, width, height } = cropArea;

    // Check corner handles first (larger priority)
    if (Math.abs(mouseX - x) < handleSize && Math.abs(mouseY - y) < handleSize) return 'resize-tl';
    if (Math.abs(mouseX - (x + width)) < handleSize && Math.abs(mouseY - y) < handleSize) return 'resize-tr';
    if (Math.abs(mouseX - x) < handleSize && Math.abs(mouseY - (y + height)) < handleSize) return 'resize-bl';
    if (Math.abs(mouseX - (x + width)) < handleSize && Math.abs(mouseY - (y + height)) < handleSize) return 'resize-br';

    // Check edge handles
    if (Math.abs(mouseY - y) < edgeThreshold && mouseX > x + handleSize && mouseX < x + width - handleSize) return 'resize-t';
    if (Math.abs(mouseY - (y + height)) < edgeThreshold && mouseX > x + handleSize && mouseX < x + width - handleSize) return 'resize-b';
    if (Math.abs(mouseX - x) < edgeThreshold && mouseY > y + handleSize && mouseY < y + height - handleSize) return 'resize-l';
    if (Math.abs(mouseX - (x + width)) < edgeThreshold && mouseY > y + handleSize && mouseY < y + height - handleSize) return 'resize-r';

    // Check if inside crop area for move
    if (mouseX >= x && mouseX <= x + width && mouseY >= y && mouseY <= y + height) return 'move';

    return null;
  };

  const getCursor = (mode: DragMode): string => {
    if (!mode) return 'default';
    if (mode === 'move') return 'move';
    if (mode === 'resize-tl' || mode === 'resize-br') return 'nwse-resize';
    if (mode === 'resize-tr' || mode === 'resize-bl') return 'nesw-resize';
    if (mode === 'resize-t' || mode === 'resize-b') return 'ns-resize';
    if (mode === 'resize-l' || mode === 'resize-r') return 'ew-resize';
    return 'default';
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    const pos = getMousePos(e);
    const mode = getDragMode(pos.x, pos.y);
    if (mode) {
      setDragMode(mode);
      setDragStart(pos);
      e.preventDefault();
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const pos = getMousePos(e);

    if (dragMode) {
      const dx = pos.x - dragStart.x;
      const dy = pos.y - dragStart.y;
      let newCropArea = { ...cropArea };
      const aspectRatio = cropArea.width / cropArea.height;

      if (dragMode === 'move') {
        newCropArea.x = Math.max(0, Math.min(containerWidth - cropArea.width, cropArea.x + dx));
        newCropArea.y = Math.max(0, Math.min(containerHeight - cropArea.height, cropArea.y + dy));
      } else if (dragMode.startsWith('resize-')) {
        // Handle resize
        if (dragMode.includes('t')) {
          const newY = Math.max(0, cropArea.y + dy);
          const newHeight = cropArea.height + (cropArea.y - newY);
          if (newHeight > 50) {
            newCropArea.y = newY;
            newCropArea.height = newHeight;
            if (aspectRatioLocked && !dragMode.includes('l') && !dragMode.includes('r')) {
              newCropArea.width = newHeight * aspectRatio;
              newCropArea.x = cropArea.x + (cropArea.width - newCropArea.width) / 2;
            }
          }
        }
        if (dragMode.includes('b')) {
          const newHeight = Math.max(50, Math.min(containerHeight - cropArea.y, cropArea.height + dy));
          newCropArea.height = newHeight;
          if (aspectRatioLocked && !dragMode.includes('l') && !dragMode.includes('r')) {
            newCropArea.width = newHeight * aspectRatio;
            newCropArea.x = cropArea.x + (cropArea.width - newCropArea.width) / 2;
          }
        }
        if (dragMode.includes('l')) {
          const newX = Math.max(0, cropArea.x + dx);
          const newWidth = cropArea.width + (cropArea.x - newX);
          if (newWidth > 50) {
            newCropArea.x = newX;
            newCropArea.width = newWidth;
            if (aspectRatioLocked && !dragMode.includes('t') && !dragMode.includes('b')) {
              newCropArea.height = newWidth / aspectRatio;
              newCropArea.y = cropArea.y + (cropArea.height - newCropArea.height) / 2;
            }
          }
        }
        if (dragMode.includes('r')) {
          const newWidth = Math.max(50, Math.min(containerWidth - cropArea.x, cropArea.width + dx));
          newCropArea.width = newWidth;
          if (aspectRatioLocked && !dragMode.includes('t') && !dragMode.includes('b')) {
            newCropArea.height = newWidth / aspectRatio;
            newCropArea.y = cropArea.y + (cropArea.height - newCropArea.height) / 2;
          }
        }

        // For corner resizing with aspect ratio lock
        if (aspectRatioLocked && dragMode.length === 11) { // corner resize (e.g., 'resize-tl')
          if (dragMode === 'resize-tl' || dragMode === 'resize-br') {
            const avgDelta = (dx + dy) / 2;
            if (dragMode === 'resize-tl') {
              const newWidth = Math.max(50, cropArea.width - avgDelta);
              const newHeight = newWidth / aspectRatio;
              if (cropArea.x + cropArea.width - newWidth >= 0 && cropArea.y + cropArea.height - newHeight >= 0) {
                newCropArea.width = newWidth;
                newCropArea.height = newHeight;
                newCropArea.x = cropArea.x + cropArea.width - newWidth;
                newCropArea.y = cropArea.y + cropArea.height - newHeight;
              }
            } else {
              const newWidth = Math.max(50, cropArea.width + avgDelta);
              const newHeight = newWidth / aspectRatio;
              if (cropArea.x + newWidth <= containerWidth && cropArea.y + newHeight <= containerHeight) {
                newCropArea.width = newWidth;
                newCropArea.height = newHeight;
              }
            }
          } else if (dragMode === 'resize-tr' || dragMode === 'resize-bl') {
            const avgDelta = (dx - dy) / 2;
            if (dragMode === 'resize-tr') {
              const newWidth = Math.max(50, cropArea.width + avgDelta);
              const newHeight = newWidth / aspectRatio;
              if (cropArea.x + newWidth <= containerWidth && cropArea.y + cropArea.height - newHeight >= 0) {
                newCropArea.width = newWidth;
                newCropArea.height = newHeight;
                newCropArea.y = cropArea.y + cropArea.height - newHeight;
              }
            } else {
              const newWidth = Math.max(50, cropArea.width - avgDelta);
              const newHeight = newWidth / aspectRatio;
              if (cropArea.x + cropArea.width - newWidth >= 0 && cropArea.y + newHeight <= containerHeight) {
                newCropArea.width = newWidth;
                newCropArea.height = newHeight;
                newCropArea.x = cropArea.x + cropArea.width - newWidth;
              }
            }
          }
        }
      }

      setCropArea(newCropArea);
      setDragStart(pos);
    } else {
      // Update cursor
      const mode = getDragMode(pos.x, pos.y);
      if (overlayRef.current) {
        overlayRef.current.style.cursor = getCursor(mode);
      }
    }
  };

  const handleMouseUp = () => {
    setDragMode(null);
  };

  useEffect(() => {
    const handleGlobalMouseUp = () => setDragMode(null);
    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => window.removeEventListener('mouseup', handleGlobalMouseUp);
  }, []);

  // Reset function
  const handleReset = () => {
    setCropArea(getInitialCropArea());
    setAspectRatioLocked(true);
  };

  // Expose the handleCrop and handleReset functions to parent via refs
  useEffect(() => {
    applyRef.current = handleCrop;
    resetRef.current = handleReset;
  }, [cropArea, image, containerWidth, containerHeight]);

  const handleCrop = () => {
    // Calculate the actual image coordinates
    const aspect = image.width / image.height;
    const containerAspect = containerWidth / containerHeight;

    let displayWidth, displayHeight, offsetX, offsetY;
    if (aspect > containerAspect) {
      displayWidth = containerWidth;
      displayHeight = containerWidth / aspect;
      offsetX = 0;
      offsetY = (containerHeight - displayHeight) / 2;
    } else {
      displayHeight = containerHeight;
      displayWidth = containerHeight * aspect;
      offsetX = (containerWidth - displayWidth) / 2;
      offsetY = 0;
    }

    // Convert crop area from container coordinates to image coordinates
    const scaleX = image.width / displayWidth;
    const scaleY = image.height / displayHeight;

    const cropX = Math.max(0, (cropArea.x - offsetX) * scaleX);
    const cropY = Math.max(0, (cropArea.y - offsetY) * scaleY);
    const cropWidth = Math.min(image.width - cropX, cropArea.width * scaleX);
    const cropHeight = Math.min(image.height - cropY, cropArea.height * scaleY);

    // Create a new canvas for the cropped image
    const canvas = document.createElement('canvas');
    canvas.width = cropWidth;
    canvas.height = cropHeight;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.drawImage(
      image,
      cropX,
      cropY,
      cropWidth,
      cropHeight,
      0,
      0,
      cropWidth,
      cropHeight
    );

    // Convert canvas to image
    const croppedImage = new Image();
    croppedImage.onload = () => {
      onCropComplete(croppedImage);
    };
    croppedImage.src = canvas.toDataURL('image/png');
  };

  return (
    <div
      ref={overlayRef}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        cursor: getCursor(dragMode || getDragMode(0, 0)),
        userSelect: 'none',
      }}
    >
      {/* Dark overlay */}
      <svg
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
        }}
      >
        <defs>
          <mask id="crop-mask">
            <rect width="100%" height="100%" fill="white" />
            <rect
              x={cropArea.x}
              y={cropArea.y}
              width={cropArea.width}
              height={cropArea.height}
              fill="black"
            />
          </mask>
        </defs>
        <rect
          width="100%"
          height="100%"
          fill="rgba(0, 0, 0, 0.6)"
          mask="url(#crop-mask)"
        />
      </svg>

      {/* Crop border */}
      <div
        style={{
          position: 'absolute',
          left: cropArea.x,
          top: cropArea.y,
          width: cropArea.width,
          height: cropArea.height,
          border: '2px solid #4a7c59',
          boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.5)',
          pointerEvents: 'none',
        }}
      >
        {/* Grid lines */}
        <div style={{ position: 'absolute', top: '33.33%', left: 0, right: 0, height: '1px', background: 'rgba(74, 124, 89, 0.5)' }} />
        <div style={{ position: 'absolute', top: '66.66%', left: 0, right: 0, height: '1px', background: 'rgba(74, 124, 89, 0.5)' }} />
        <div style={{ position: 'absolute', left: '33.33%', top: 0, bottom: 0, width: '1px', background: 'rgba(74, 124, 89, 0.5)' }} />
        <div style={{ position: 'absolute', left: '66.66%', top: 0, bottom: 0, width: '1px', background: 'rgba(74, 124, 89, 0.5)' }} />
      </div>

      {/* Corner handles */}
      {['tl', 'tr', 'bl', 'br'].map((corner) => {
        const isLeft = corner.includes('l');
        const isTop = corner.includes('t');
        return (
          <div
            key={corner}
            style={{
              position: 'absolute',
              left: isLeft ? cropArea.x - 6 : cropArea.x + cropArea.width - 6,
              top: isTop ? cropArea.y - 6 : cropArea.y + cropArea.height - 6,
              width: 12,
              height: 12,
              background: '#4a7c59',
              border: '2px solid white',
              borderRadius: '50%',
              pointerEvents: 'auto',
              cursor: corner === 'tl' || corner === 'br' ? 'nwse-resize' : 'nesw-resize',
            }}
          />
        );
      })}

      {/* Edge handles */}
      {!aspectRatioLocked && ['t', 'b', 'l', 'r'].map((edge) => {
        const isVertical = edge === 't' || edge === 'b';
        return (
          <div
            key={edge}
            style={{
              position: 'absolute',
              left: edge === 'l' ? cropArea.x - 4 : edge === 'r' ? cropArea.x + cropArea.width - 4 : cropArea.x + cropArea.width / 2 - 4,
              top: edge === 't' ? cropArea.y - 4 : edge === 'b' ? cropArea.y + cropArea.height - 4 : cropArea.y + cropArea.height / 2 - 4,
              width: 8,
              height: 8,
              background: '#4a7c59',
              border: '2px solid white',
              borderRadius: '50%',
              pointerEvents: 'auto',
              cursor: isVertical ? 'ns-resize' : 'ew-resize',
            }}
          />
        );
      })}

      {/* Aspect ratio lock toggle */}
      <div
        style={{
          position: 'absolute',
          bottom: 20,
          left: '50%',
          transform: 'translateX(-50%)',
          pointerEvents: 'auto',
        }}
      >
        <button
          onClick={() => setAspectRatioLocked(!aspectRatioLocked)}
          style={{
            padding: '8px 16px',
            background: aspectRatioLocked ? '#4a7c59' : '#5a6c7d',
            border: 'none',
            borderRadius: '4px',
            color: '#fff',
            cursor: 'pointer',
            fontSize: '0.9em',
            fontWeight: '500',
          }}
        >
          {aspectRatioLocked ? '🔒 Locked' : '🔓 Free'}
        </button>
      </div>
    </div>
  );
}
