import { useStore } from '../../store';
import type { EnvPreset, ShadingMode } from '../../types';
import { ContrastIcon, FrameIcon, GridIcon } from '../Icons';

const SHADE_GROUPS: { id: ShadingMode; label: string; title: string }[][] = [
  [
    { id: 'lit', label: 'Lit', title: 'PBR shading with environment lighting' },
    { id: 'wireframe', label: 'Wire', title: 'Wireframe overlay on shaded model' },
    { id: 'solid', label: 'Clay', title: 'Flat gray clay override' },
  ],
  [
    { id: 'albedo', label: 'Alb', title: 'Albedo / base color map only' },
    { id: 'normal', label: 'Nrm', title: 'Normal map' },
    { id: 'roughness', label: 'Rgh', title: 'Roughness map' },
    { id: 'metallic', label: 'Mtl', title: 'Metallic map' },
    { id: 'ao', label: 'AO', title: 'Ambient occlusion map' },
  ],
];

const ENV_PRESETS: { id: EnvPreset; label: string }[] = [
  { id: 'studio', label: 'Studio' },
  { id: 'soft', label: 'Soft' },
  { id: 'night', label: 'Night' },
];

export function ViewportToolbar() {
  const shading = useStore((s) => s.shading);
  const setShading = useStore((s) => s.setShading);
  const envPreset = useStore((s) => s.envPreset);
  const setEnvPreset = useStore((s) => s.setEnvPreset);
  const showGrid = useStore((s) => s.showGrid);
  const toggleGrid = useStore((s) => s.toggleGrid);
  const viewportBg = useStore((s) => s.viewportBg);
  const cycleBg = useStore((s) => s.cycleBg);
  const requestFrame = useStore((s) => s.requestFrame);

  return (
    <div className="vp-toolbar">
      {SHADE_GROUPS.map((group, gi) => (
        <div className="seg seg--toolbar" key={gi}>
          {group.map((m) => (
            <button
              key={m.id}
              className={`seg__btn ${shading === m.id ? 'seg__btn--active' : ''}`}
              title={m.title}
              onClick={() => setShading(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
      ))}

      <div className="seg seg--toolbar">
        {ENV_PRESETS.map((p) => (
          <button
            key={p.id}
            className={`seg__btn ${envPreset === p.id ? 'seg__btn--active' : ''}`}
            title={`${p.label} lighting (procedural, offline)`}
            onClick={() => setEnvPreset(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="vp-toolbar__spacer" />

      <button
        className={`icon-btn icon-btn--toolbar ${showGrid ? 'icon-btn--active' : ''}`}
        title="Toggle grid"
        onClick={toggleGrid}
      >
        <GridIcon size={14} />
      </button>
      <button
        className="icon-btn icon-btn--toolbar"
        title={`Background: ${viewportBg} — click to cycle`}
        onClick={cycleBg}
      >
        <ContrastIcon size={14} />
      </button>
      <button
        className="icon-btn icon-btn--toolbar"
        title="Re-frame model (fit to view)"
        onClick={requestFrame}
      >
        <FrameIcon size={14} />
      </button>
    </div>
  );
}
