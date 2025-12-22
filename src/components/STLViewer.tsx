import { useEffect, useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import * as THREE from 'three';
import { MeshData, DepthMapConfig } from '../types';

interface STLViewerProps {
  meshData: MeshData | null;
  config: DepthMapConfig;
}

function MeshModel({ meshData, config }: { meshData: MeshData; config: DepthMapConfig }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const geometryRef = useRef<THREE.BufferGeometry | null>(null);

  useEffect(() => {
    console.log('Creating mesh geometry with data:', meshData);

    // Dispose old geometry if it exists
    if (geometryRef.current) {
      geometryRef.current.dispose();
    }

    // Create new geometry
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(meshData.vertices, 3));
    geometry.setIndex(new THREE.BufferAttribute(meshData.indices, 1));
    geometry.computeVertexNormals();

    geometryRef.current = geometry;

    // Update mesh geometry
    if (meshRef.current) {
      meshRef.current.geometry = geometry;
      console.log('Mesh geometry updated, vertices:', meshData.vertices.length / 3, 'triangles:', meshData.indices.length / 3);
    }
  }, [meshData]);

  // Only apply rotate180 to the 3D model (flips are handled in image processing)
  const rotationZ = config.rotate180 ? Math.PI : 0;

  return (
    <mesh
      ref={meshRef}
      geometry={geometryRef.current || undefined}
      castShadow
      receiveShadow
      rotation={[0, 0, rotationZ]}
    >
      <meshStandardMaterial
        color="#8b9dc3"
        metalness={0.3}
        roughness={0.4}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

export default function STLViewer({ meshData, config }: STLViewerProps) {
  return (
    <div style={{ width: '100%', height: '100%', background: '#1a1a1a' }}>
      <Canvas shadows>
        <PerspectiveCamera makeDefault position={[0, -200, 150]} fov={50} />
        <OrbitControls
          enableDamping
          dampingFactor={0.05}
          minDistance={10}
          maxDistance={1000}
        />

        <ambientLight intensity={0.5} />
        <directionalLight
          position={[10, 10, 10]}
          intensity={1}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
        />
        <directionalLight position={[-10, -10, 10]} intensity={0.5} />

        {meshData && <MeshModel meshData={meshData} config={config} />}

        <gridHelper args={[200, 20, '#444444', '#222222']} />
      </Canvas>
    </div>
  );
}
