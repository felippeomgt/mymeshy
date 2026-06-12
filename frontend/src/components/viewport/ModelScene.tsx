import { useEffect, useMemo } from 'react';
import * as THREE from 'three';
import { useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { useStore } from '../../store';
import type { LiveModelStats, ShadingMode } from '../../types';

type ChannelMode = 'albedo' | 'normal' | 'roughness' | 'metallic' | 'ao';

interface OrbitLike {
  target: THREE.Vector3;
  update: () => void;
}

function isMesh(o: THREE.Object3D): o is THREE.Mesh {
  return (o as THREE.Mesh).isMesh === true;
}

function firstMaterial(m: THREE.Material | THREE.Material[]): THREE.Material {
  return Array.isArray(m) ? m[0] : m;
}

function channelTexture(mat: THREE.Material, channel: ChannelMode): THREE.Texture | null {
  const std = mat as THREE.MeshStandardMaterial;
  switch (channel) {
    case 'albedo':
      return std.map ?? null;
    case 'normal':
      return std.normalMap ?? null;
    case 'roughness':
      return std.roughnessMap ?? null;
    case 'metallic':
      return std.metalnessMap ?? null;
    case 'ao':
      return std.aoMap ?? null;
  }
}

function makeOverrideMaterial(
  shading: ShadingMode,
  original: THREE.Material,
): THREE.Material | null {
  if (shading === 'lit' || shading === 'wireframe') return null;

  if (shading === 'solid') {
    return new THREE.MeshStandardMaterial({
      color: new THREE.Color('#b9bec7'),
      roughness: 0.8,
      metalness: 0.02,
    });
  }

  // Per-channel inspection: unlit material showing just that texture.
  const tex = channelTexture(original, shading);
  const mat = new THREE.MeshBasicMaterial({ toneMapped: false });
  if (tex) {
    mat.map = tex;
    if (shading === 'albedo') {
      const std = original as THREE.MeshStandardMaterial;
      if (std.color) mat.color.copy(std.color);
    }
  } else {
    // Map missing on this material — flat indicator gray.
    mat.color.set('#3a3f49');
  }
  return mat;
}

function computeStats(root: THREE.Object3D): Omit<LiveModelStats, 'drawCalls'> {
  let vertices = 0;
  let triangles = 0;
  let hasUv = false;
  const materials = new Set<string>();
  const textures = new Set<string>();

  root.traverse((o) => {
    if (!isMesh(o)) return;
    const geo = o.geometry as THREE.BufferGeometry;
    const pos = geo.getAttribute('position');
    if (pos) {
      vertices += pos.count;
      triangles += geo.index ? geo.index.count / 3 : pos.count / 3;
    }
    if (geo.getAttribute('uv')) hasUv = true;

    const mats = Array.isArray(o.material) ? o.material : [o.material];
    for (const m of mats) {
      if (!m) continue;
      materials.add(m.uuid);
      for (const value of Object.values(m)) {
        if (value && (value as THREE.Texture).isTexture) {
          textures.add((value as THREE.Texture).uuid);
        }
      }
    }
  });

  return {
    vertices,
    triangles: Math.round(triangles),
    materials: materials.size,
    textures: textures.size,
    hasUv,
  };
}

/** Positions the camera so the object fills the view nicely. */
function frameObject(
  object: THREE.Object3D,
  camera: THREE.Camera,
  controls: OrbitLike | null,
) {
  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) return;
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const radius = Math.max(sphere.radius, 0.001);

  const persp = camera as THREE.PerspectiveCamera;
  const fov = ((persp.fov ?? 45) * Math.PI) / 180;
  const dist = (radius / Math.sin(fov / 2)) * 1.25;

  const dir = new THREE.Vector3(1, 0.55, 1).normalize();
  camera.position.copy(sphere.center).addScaledVector(dir, dist);
  if (persp.isPerspectiveCamera) {
    persp.near = Math.max(dist / 100, 0.01);
    persp.far = dist * 100;
    persp.updateProjectionMatrix();
  }
  camera.lookAt(sphere.center);

  if (controls) {
    controls.target.copy(sphere.center);
    controls.update();
  }
}

interface Props {
  url: string;
}

export function ModelScene({ url }: Props) {
  const { scene } = useGLTF(url);
  const shading = useStore((s) => s.shading);
  const frameRequest = useStore((s) => s.frameRequest);
  const setLiveStats = useStore((s) => s.setLiveStats);
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as unknown as OrbitLike | null;

  // Geometry-derived stats for the right panel + overlay.
  useEffect(() => {
    const stats = computeStats(scene);
    setLiveStats({ ...stats, drawCalls: 0 });
    return () => setLiveStats(null);
  }, [scene, setLiveStats]);

  // Auto-frame on load / on demand.
  useEffect(() => {
    frameObject(scene, camera, controls);
  }, [scene, camera, controls, frameRequest]);

  // Shading overrides — swap materials, restore on change/unmount.
  useEffect(() => {
    const created: THREE.Material[] = [];
    scene.traverse((o) => {
      if (!isMesh(o)) return;
      if (!o.userData.__origMaterial) o.userData.__origMaterial = o.material;
      const original = o.userData.__origMaterial as THREE.Material | THREE.Material[];
      const override = makeOverrideMaterial(shading, firstMaterial(original));
      if (override) {
        created.push(override);
        o.material = override;
      } else {
        o.material = original;
      }
    });
    return () => {
      scene.traverse((o) => {
        if (isMesh(o) && o.userData.__origMaterial) {
          o.material = o.userData.__origMaterial as THREE.Material | THREE.Material[];
        }
      });
      created.forEach((m) => m.dispose());
    };
  }, [scene, shading]);

  // Wireframe overlay clone (shares geometry; one shared line material).
  const wireframe = useMemo(() => {
    const material = new THREE.MeshBasicMaterial({
      wireframe: true,
      color: new THREE.Color('#46e0ff'),
      transparent: true,
      opacity: 0.32,
      depthWrite: false,
      toneMapped: false,
    });
    const clone = scene.clone(true);
    clone.traverse((o) => {
      if (isMesh(o)) o.material = material;
    });
    return { clone, material };
  }, [scene]);

  useEffect(() => () => wireframe.material.dispose(), [wireframe]);

  return (
    <group>
      <primitive object={scene} />
      {shading === 'wireframe' && <primitive object={wireframe.clone} />}
    </group>
  );
}
