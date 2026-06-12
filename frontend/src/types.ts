// ---- Backend API contract -------------------------------------------------

export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled';
export type JobType = 'text_to_3d' | 'image_to_3d' | 'texture';

export interface JobRecord {
  id: string;
  type: JobType;
  status: JobStatus;
  stage: string;
  progress: number; // 0..1
  message?: string;
  error?: string;
  asset_id?: string;
  created_at: string;
  params: Record<string, unknown>;
}

export type TextureMap = 'albedo' | 'normal' | 'roughness' | 'metallic' | 'ao';

export interface AssetMeta {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  source: {
    type: 'text' | 'image' | 'texture';
    prompt?: string;
    image_names?: string[];
  };
  stats: {
    vertices: number;
    triangles: number;
    materials: number;
    texture_size?: number;
    has_uv: boolean;
  };
  textures: TextureMap[];
  adapter: string;
}

export interface AdapterInfo {
  name: string;
  available: boolean;
  reason?: string;
}

export interface SystemInfo {
  version: string;
  gpu: { name: string; vram_mb: number } | null;
  blender: boolean;
  adapters: {
    image_to_3d: AdapterInfo[];
    text_to_image: AdapterInfo[];
    texturing: AdapterInfo[];
  };
  active: {
    image_to_3d: string;
    text_to_image: string;
    texturing: string;
  };
  mock_mode: boolean;
}

// ---- Frontend-only types --------------------------------------------------

export interface GenOptions {
  adapter?: string;
  target_polycount?: number;
  texture_size?: number;
  generate_pbr?: boolean;
  seed?: number;
}

export type ExportFormat = 'glb' | 'gltf' | 'obj' | 'fbx';

export type ShadingMode =
  | 'lit'
  | 'wireframe'
  | 'solid'
  | 'albedo'
  | 'normal'
  | 'roughness'
  | 'metallic'
  | 'ao';

export type EnvPreset = 'studio' | 'soft' | 'night';
export type ViewportBg = 'dark' | 'gray' | 'light';

export interface LiveModelStats {
  vertices: number;
  triangles: number;
  materials: number;
  textures: number;
  drawCalls: number;
  hasUv: boolean;
}
