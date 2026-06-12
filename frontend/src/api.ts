import type {
  AssetMeta,
  ExportFormat,
  GenOptions,
  JobRecord,
  SystemInfo,
  TextureMap,
} from './types';

const BASE = '/api';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(0, 'Backend unreachable');
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
      else if (body && typeof body.error === 'string') detail = body.error;
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

/** Strips undefined / empty values so we only send meaningful options. */
function cleanOptions(options: GenOptions): GenOptions {
  const out: GenOptions = {};
  if (options.adapter) out.adapter = options.adapter;
  if (typeof options.target_polycount === 'number' && options.target_polycount > 0)
    out.target_polycount = options.target_polycount;
  if (typeof options.texture_size === 'number') out.texture_size = options.texture_size;
  if (typeof options.generate_pbr === 'boolean') out.generate_pbr = options.generate_pbr;
  if (typeof options.seed === 'number' && Number.isFinite(options.seed)) out.seed = options.seed;
  return out;
}

export const api = {
  // -- system ---------------------------------------------------------------
  getSystem: () => request<SystemInfo>('/system'),

  // -- jobs -----------------------------------------------------------------
  getJobs: () => request<JobRecord[]>('/jobs'),
  getJob: (id: string) => request<JobRecord>(`/jobs/${id}`),
  cancelJob: (id: string) =>
    request<JobRecord>(`/jobs/${id}/cancel`, { method: 'POST' }),

  createTextTo3d: (prompt: string, options: GenOptions) =>
    request<JobRecord>(
      '/jobs/text-to-3d',
      jsonInit('POST', { prompt, options: cleanOptions(options) }),
    ),

  createImageTo3d: (images: File[], options: GenOptions) => {
    const fd = new FormData();
    for (const img of images) fd.append('images', img, img.name);
    fd.append('options', JSON.stringify(cleanOptions(options)));
    return request<JobRecord>('/jobs/image-to-3d', { method: 'POST', body: fd });
  },

  createTexture: (payload: {
    assetId?: string;
    mesh?: File;
    prompt?: string;
    image?: File;
    options: GenOptions;
  }) => {
    const fd = new FormData();
    if (payload.assetId) fd.append('asset_id', payload.assetId);
    if (payload.mesh) fd.append('mesh', payload.mesh, payload.mesh.name);
    if (payload.prompt) fd.append('prompt', payload.prompt);
    if (payload.image) fd.append('image', payload.image, payload.image.name);
    fd.append('options', JSON.stringify(cleanOptions(payload.options)));
    return request<JobRecord>('/jobs/texture', { method: 'POST', body: fd });
  },

  // -- assets ---------------------------------------------------------------
  getAssets: () => request<AssetMeta[]>('/assets'),
  getAsset: (id: string) => request<AssetMeta>(`/assets/${id}`),
  deleteAsset: (id: string) =>
    request<unknown>(`/assets/${id}`, { method: 'DELETE' }),
  renameAsset: (id: string, name: string) =>
    request<AssetMeta>(`/assets/${id}/rename`, jsonInit('POST', { name })),

  // -- file URLs ------------------------------------------------------------
  modelUrl: (id: string, version: string) =>
    `${BASE}/assets/${id}/model.glb?v=${encodeURIComponent(version)}`,
  textureUrl: (id: string, map: TextureMap, version: string) =>
    `${BASE}/assets/${id}/textures/${map}.png?v=${encodeURIComponent(version)}`,
  exportUrl: (id: string, format: ExportFormat) =>
    `${BASE}/assets/${id}/export?format=${format}`,
};

/** Triggers a browser download without navigating away. */
export function triggerDownload(url: string): void {
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
}
