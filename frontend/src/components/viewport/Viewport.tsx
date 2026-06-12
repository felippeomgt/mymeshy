import { Component, Suspense, useEffect, useRef, useState, type ReactNode } from 'react';
import * as THREE from 'three';
import { Canvas, useFrame } from '@react-three/fiber';
import { Grid, Html, OrbitControls } from '@react-three/drei';
import { api } from '../../api';
import { selectSelectedAsset, useStore } from '../../store';
import type { ViewportBg } from '../../types';
import { formatCount } from '../../utils';
import { CubeIcon, WarnIcon } from '../Icons';
import { EnvRig } from './EnvRig';
import { ModelScene } from './ModelScene';
import { ViewportToolbar } from './ViewportToolbar';

const BG_COLORS: Record<ViewportBg, string> = {
  dark: '#0d1016',
  gray: '#43464d',
  light: '#d8dade',
};

/** Slowly rotating wireframe icosahedron shown when nothing is selected. */
function EmptyPlaceholder() {
  const outer = useRef<THREE.Mesh>(null);
  const inner = useRef<THREE.Mesh>(null);
  useFrame((_, dt) => {
    if (outer.current) {
      outer.current.rotation.y += dt * 0.22;
      outer.current.rotation.x += dt * 0.07;
    }
    if (inner.current) {
      inner.current.rotation.y -= dt * 0.3;
      inner.current.rotation.z += dt * 0.05;
    }
  });
  return (
    <group position={[0, 0.6, 0]}>
      <mesh ref={outer}>
        <icosahedronGeometry args={[1.15, 1]} />
        <meshBasicMaterial wireframe color="#3b4763" transparent opacity={0.85} toneMapped={false} />
      </mesh>
      <mesh ref={inner} scale={0.55}>
        <icosahedronGeometry args={[1, 0]} />
        <meshBasicMaterial wireframe color="#6e5fd0" transparent opacity={0.5} toneMapped={false} />
      </mesh>
    </group>
  );
}

/** Samples renderer draw calls without re-rendering React every frame. */
function RenderInfo({ onSample }: { onSample: (calls: number) => void }) {
  const last = useRef(0);
  const acc = useRef(0);
  useFrame(({ gl }, dt) => {
    acc.current += dt;
    if (acc.current < 0.5) return;
    acc.current = 0;
    const calls = gl.info.render.calls;
    if (calls !== last.current) {
      last.current = calls;
      onSample(calls);
    }
  });
  return null;
}

function LoadingIndicator() {
  return (
    <Html center>
      <div className="vp-loading">
        <span className="vp-loading__ring" />
        loading model…
      </div>
    </Html>
  );
}

interface BoundaryProps {
  onError: (message: string) => void;
  children: ReactNode;
}

class ModelBoundary extends Component<BoundaryProps, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    this.props.onError(error instanceof Error ? error.message : 'Failed to load model');
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export function Viewport() {
  const asset = useStore(selectSelectedAsset);
  const viewportBg = useStore((s) => s.viewportBg);
  const showGrid = useStore((s) => s.showGrid);
  const envPreset = useStore((s) => s.envPreset);
  const liveStats = useStore((s) => s.liveStats);

  const [drawCalls, setDrawCalls] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);

  const url = asset ? api.modelUrl(asset.id, asset.updated_at) : null;
  const light = viewportBg === 'light';

  // Clear stale load errors when switching assets.
  useEffect(() => setLoadError(null), [url]);

  return (
    <div className={`viewport ${light ? 'viewport--light' : ''}`}>
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [3.2, 2.2, 4.2], fov: 45, near: 0.05, far: 500 }}
        gl={{ antialias: true, powerPreference: 'high-performance' }}
      >
        <color attach="background" args={[BG_COLORS[viewportBg]]} />
        <EnvRig preset={envPreset} />

        {showGrid && (
          <Grid
            position={[0, -0.002, 0]}
            args={[10, 10]}
            cellSize={0.25}
            cellThickness={0.6}
            cellColor={light ? '#a9adb6' : '#262d3c'}
            sectionSize={1.25}
            sectionThickness={1}
            sectionColor={light ? '#8f95a3' : '#39435c'}
            fadeDistance={26}
            fadeStrength={1.5}
            infiniteGrid
            followCamera={false}
          />
        )}

        <Suspense fallback={<LoadingIndicator />}>
          {url ? (
            <ModelBoundary key={url} onError={setLoadError}>
              <ModelScene url={url} />
            </ModelBoundary>
          ) : (
            <EmptyPlaceholder />
          )}
        </Suspense>

        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.08}
          minDistance={0.05}
          maxDistance={200}
        />
        <RenderInfo onSample={setDrawCalls} />
      </Canvas>

      <ViewportToolbar />

      {asset && liveStats && (
        <div className="vp-stats">
          <span>
            <b>{formatCount(liveStats.triangles)}</b> tris
          </span>
          <span>
            <b>{formatCount(liveStats.vertices)}</b> verts
          </span>
          <span>
            <b>{liveStats.materials}</b> mat{liveStats.materials === 1 ? '' : 's'}
          </span>
          <span>
            <b>{liveStats.textures}</b> tex
          </span>
          <span>
            <b>{drawCalls}</b> draws
          </span>
        </div>
      )}

      {!asset && (
        <div className="vp-empty">
          <CubeIcon size={26} />
          <h3>No asset selected</h3>
          <p>
            Generate a model from the left panel,
            <br />
            or pick one from the library below.
          </p>
        </div>
      )}

      {asset && loadError && (
        <div className="vp-error" key={url ?? 'err'}>
          <WarnIcon size={18} />
          <div>
            <strong>Couldn’t load model</strong>
            <div className="vp-error__detail">{loadError}</div>
          </div>
        </div>
      )}
    </div>
  );
}
