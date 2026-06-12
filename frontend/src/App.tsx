import { useEffect } from 'react';
import { selectHasActiveJobs, useStore } from './store';
import { TopBar } from './components/TopBar';
import { LeftPanel } from './components/panels/LeftPanel';
import { RightPanel } from './components/panels/RightPanel';
import { AssetLibrary } from './components/library/AssetLibrary';
import { Viewport } from './components/viewport/Viewport';

const JOBS_FAST_MS = 1500;
const JOBS_SLOW_MS = 5000;
const SYSTEM_MS = 8000;

/** Keeps system / jobs polling alive for the whole app. */
function usePolling() {
  const fetchSystem = useStore((s) => s.fetchSystem);
  const fetchJobs = useStore((s) => s.fetchJobs);
  const fetchAssets = useStore((s) => s.fetchAssets);
  const hasActive = useStore(selectHasActiveJobs);

  // initial load
  useEffect(() => {
    void fetchSystem();
    void fetchAssets();
    void fetchJobs();
  }, [fetchSystem, fetchAssets, fetchJobs]);

  // system heartbeat
  useEffect(() => {
    const id = window.setInterval(() => void fetchSystem(), SYSTEM_MS);
    return () => window.clearInterval(id);
  }, [fetchSystem]);

  // jobs polling — fast while anything is active
  useEffect(() => {
    const id = window.setInterval(
      () => void fetchJobs(),
      hasActive ? JOBS_FAST_MS : JOBS_SLOW_MS,
    );
    return () => window.clearInterval(id);
  }, [fetchJobs, hasActive]);
}

export default function App() {
  usePolling();
  const backendDown = useStore((s) => s.backendDown);

  return (
    <div className="app-shell">
      <TopBar />
      {backendDown && (
        <div className="backend-banner" role="alert">
          <span className="backend-banner__dot" />
          Backend unreachable at 127.0.0.1:8420 — retrying… Generation and the asset
          library are unavailable until it comes back.
        </div>
      )}
      <div className="app-body">
        <LeftPanel />
        <main className="app-center">
          <Viewport />
          <AssetLibrary />
        </main>
        <RightPanel />
      </div>
    </div>
  );
}
