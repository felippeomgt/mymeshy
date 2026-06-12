import { useStore } from '../store';
import { formatVram } from '../utils';
import { CubeIcon } from './Icons';

export function TopBar() {
  const system = useStore((s) => s.system);
  const backendDown = useStore((s) => s.backendDown);

  const statusClass = backendDown
    ? 'status-dot--down'
    : system?.mock_mode
      ? 'status-dot--mock'
      : 'status-dot--live';

  const statusLabel = backendDown
    ? 'Offline'
    : system
      ? system.mock_mode
        ? 'Mock mode'
        : 'Live'
      : 'Connecting…';

  return (
    <header className="topbar">
      <div className="topbar__brand">
        <span className="topbar__logo">
          <CubeIcon size={20} />
        </span>
        <span className="topbar__name">
          My<em>Meshy</em>
        </span>
        {system && <span className="topbar__version">v{system.version}</span>}
        <span className="topbar__tagline">local-first AI 3D studio</span>
      </div>

      <div className="topbar__status">
        {system?.gpu && (
          <span className="topbar__chip" title="Detected GPU">
            <span className="topbar__chip-key">GPU</span>
            {system.gpu.name} · {formatVram(system.gpu.vram_mb)}
          </span>
        )}
        {system && !system.gpu && (
          <span className="topbar__chip topbar__chip--warn" title="No GPU detected">
            <span className="topbar__chip-key">GPU</span>none
          </span>
        )}
        {system && (
          <span className="topbar__chip" title="Active image-to-3D adapter">
            <span className="topbar__chip-key">ADAPTER</span>
            {system.active.image_to_3d}
          </span>
        )}
        {system && (
          <span
            className={`topbar__chip ${system.blender ? '' : 'topbar__chip--dim'}`}
            title={system.blender ? 'Blender available (FBX export enabled)' : 'Blender not found — FBX export disabled'}
          >
            <span className="topbar__chip-key">BLENDER</span>
            {system.blender ? 'yes' : 'no'}
          </span>
        )}
        <span
          className="topbar__mode"
          title={
            backendDown
              ? 'Backend unreachable'
              : system?.mock_mode
                ? 'Active image-to-3D adapter is "mock" — outputs are placeholders'
                : 'Real model adapter active'
          }
        >
          <span className={`status-dot ${statusClass}`} />
          {statusLabel}
        </span>
      </div>
    </header>
  );
}
