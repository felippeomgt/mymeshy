import { Environment, Lightformer } from '@react-three/drei';
import type { EnvPreset } from '../../types';

/**
 * Procedural lighting rigs. Local-first by design: environments are rendered
 * from Lightformer planes into a cubemap (no HDR downloads at runtime).
 */
export function EnvRig({ preset }: { preset: EnvPreset }) {
  if (preset === 'studio') {
    return (
      <>
        <Environment key="studio" resolution={256} frames={1}>
          {/* big overhead softbox */}
          <Lightformer
            form="rect"
            intensity={5}
            position={[0, 6, 0]}
            rotation-x={Math.PI / 2}
            scale={[9, 9, 1]}
          />
          {/* key */}
          <Lightformer form="rect" intensity={3} position={[5, 2, 4]} scale={[4, 5, 1]} />
          {/* fill */}
          <Lightformer form="rect" intensity={1.1} position={[-6, 1, 2]} scale={[4, 6, 1]} color="#cfe0ff" />
          {/* rim strip */}
          <Lightformer form="rect" intensity={2.2} position={[0, 3, -7]} scale={[12, 1.2, 1]} color="#ffffff" />
        </Environment>
        <directionalLight position={[6, 9, 5]} intensity={1.4} />
        <directionalLight position={[-5, 3, -4]} intensity={0.35} color="#bcd0ff" />
        <ambientLight intensity={0.18} />
      </>
    );
  }

  if (preset === 'soft') {
    return (
      <>
        <Environment key="soft" resolution={256} frames={1}>
          {/* dome of gentle panels for shadowless, even light */}
          <Lightformer
            form="rect"
            intensity={2.2}
            position={[0, 7, 0]}
            rotation-x={Math.PI / 2}
            scale={[14, 14, 1]}
            color="#fff5e8"
          />
          <Lightformer form="rect" intensity={1.4} position={[8, 1, 0]} rotation-y={-Math.PI / 2} scale={[10, 6, 1]} color="#ffeede" />
          <Lightformer form="rect" intensity={1.4} position={[-8, 1, 0]} rotation-y={Math.PI / 2} scale={[10, 6, 1]} color="#e8f0ff" />
          <Lightformer form="rect" intensity={1.2} position={[0, 1, 9]} rotation-y={Math.PI} scale={[10, 6, 1]} />
        </Environment>
        <directionalLight position={[3, 6, 4]} intensity={0.6} color="#fff2e2" />
        <ambientLight intensity={0.5} />
      </>
    );
  }

  // night
  return (
    <>
      <Environment key="night" resolution={256} frames={1}>
        <Lightformer form="rect" intensity={1.6} position={[4, 3, 3]} scale={[2, 6, 1]} color="#7d6bf5" />
        <Lightformer form="rect" intensity={1.4} position={[-5, 2, -2]} scale={[2, 5, 1]} color="#21c7de" />
        <Lightformer
          form="circle"
          intensity={1.1}
          position={[0, 8, 0]}
          rotation-x={Math.PI / 2}
          scale={[4, 4, 1]}
          color="#3a4a7a"
        />
        <Lightformer form="rect" intensity={0.7} position={[0, 0.5, -8]} scale={[14, 0.8, 1]} color="#1c2a4f" />
      </Environment>
      <directionalLight position={[5, 6, 4]} intensity={0.5} color="#9b8cff" />
      <directionalLight position={[-6, 2, -3]} intensity={0.4} color="#27d3e8" />
      <ambientLight intensity={0.1} color="#33406b" />
    </>
  );
}
