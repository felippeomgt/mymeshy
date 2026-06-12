import { create } from 'zustand';
import { api } from './api';
import type {
  AssetMeta,
  EnvPreset,
  JobRecord,
  LiveModelStats,
  ShadingMode,
  SystemInfo,
  ViewportBg,
} from './types';

interface AppState {
  // backend data
  system: SystemInfo | null;
  backendDown: boolean;
  jobs: JobRecord[];
  jobsInitialized: boolean;
  assets: AssetMeta[];
  selectedAssetId: string | null;

  // viewport state
  shading: ShadingMode;
  envPreset: EnvPreset;
  showGrid: boolean;
  viewportBg: ViewportBg;
  frameRequest: number; // bump to re-frame camera
  liveStats: LiveModelStats | null;

  // actions
  fetchSystem: () => Promise<void>;
  fetchJobs: () => Promise<void>;
  fetchAssets: () => Promise<void>;
  selectAsset: (id: string | null) => void;
  cancelJob: (id: string) => Promise<void>;
  deleteAsset: (id: string) => Promise<void>;
  renameAsset: (id: string, name: string) => Promise<void>;
  setShading: (mode: ShadingMode) => void;
  setEnvPreset: (preset: EnvPreset) => void;
  toggleGrid: () => void;
  cycleBg: () => void;
  requestFrame: () => void;
  setLiveStats: (stats: LiveModelStats | null) => void;
}

const BG_CYCLE: ViewportBg[] = ['dark', 'gray', 'light'];

export const useStore = create<AppState>((set, get) => ({
  system: null,
  backendDown: false,
  jobs: [],
  jobsInitialized: false,
  assets: [],
  selectedAssetId: null,

  shading: 'lit',
  envPreset: 'studio',
  showGrid: true,
  viewportBg: 'dark',
  frameRequest: 0,
  liveStats: null,

  fetchSystem: async () => {
    try {
      const system = await api.getSystem();
      set({ system, backendDown: false });
    } catch {
      set({ backendDown: true });
    }
  },

  fetchJobs: async () => {
    try {
      const jobs = await api.getJobs();
      const { jobs: prev, jobsInitialized } = get();

      // Detect jobs that just finished and produced an asset.
      let newAssetId: string | null = null;
      if (jobsInitialized) {
        for (const job of jobs) {
          if (job.status !== 'done' || !job.asset_id) continue;
          const before = prev.find((p) => p.id === job.id);
          if (before && before.status !== 'done') newAssetId = job.asset_id;
        }
      }

      set({ jobs, jobsInitialized: true });

      if (newAssetId) {
        await get().fetchAssets();
        set({ selectedAssetId: newAssetId });
      }
    } catch {
      /* polling failure — banner driven by fetchSystem */
    }
  },

  fetchAssets: async () => {
    try {
      const assets = await api.getAssets();
      assets.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
      const { selectedAssetId } = get();
      const stillExists =
        selectedAssetId !== null && assets.some((a) => a.id === selectedAssetId);
      set({
        assets,
        selectedAssetId: stillExists ? selectedAssetId : null,
      });
    } catch {
      /* keep previous list */
    }
  },

  selectAsset: (id) => {
    if (id !== get().selectedAssetId) set({ selectedAssetId: id, liveStats: null });
  },

  cancelJob: async (id) => {
    try {
      await api.cancelJob(id);
    } catch {
      /* refresh will reconcile */
    }
    await get().fetchJobs();
  },

  deleteAsset: async (id) => {
    try {
      await api.deleteAsset(id);
    } catch {
      /* refresh will reconcile */
    }
    if (get().selectedAssetId === id) set({ selectedAssetId: null, liveStats: null });
    await get().fetchAssets();
  },

  renameAsset: async (id, name) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      const updated = await api.renameAsset(id, trimmed);
      set({
        assets: get().assets.map((a) => (a.id === id ? updated : a)),
      });
    } catch {
      /* leave old name */
    }
  },

  setShading: (mode) => set({ shading: mode }),
  setEnvPreset: (preset) => set({ envPreset: preset }),
  toggleGrid: () => set({ showGrid: !get().showGrid }),
  cycleBg: () => {
    const i = BG_CYCLE.indexOf(get().viewportBg);
    set({ viewportBg: BG_CYCLE[(i + 1) % BG_CYCLE.length] });
  },
  requestFrame: () => set({ frameRequest: get().frameRequest + 1 }),
  setLiveStats: (stats) => set({ liveStats: stats }),
}));

/** True when any job is queued or running. */
export function selectHasActiveJobs(state: AppState): boolean {
  return state.jobs.some((j) => j.status === 'queued' || j.status === 'running');
}

/** Currently selected asset, or null. */
export function selectSelectedAsset(state: AppState): AssetMeta | null {
  return state.assets.find((a) => a.id === state.selectedAssetId) ?? null;
}
