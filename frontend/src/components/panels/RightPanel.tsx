import { useEffect, useState } from 'react';
import { api, triggerDownload } from '../../api';
import { selectSelectedAsset, useStore } from '../../store';
import type { AssetMeta, ExportFormat, TextureMap } from '../../types';
import { formatCount, formatDate } from '../../utils';
import { CheckIcon, CubeIcon, DownloadIcon, PencilIcon, sourceTypeIcon } from '../Icons';
import { Modal } from '../Modal';

const MAP_LABEL: Record<TextureMap, string> = {
  albedo: 'Albedo',
  normal: 'Normal',
  roughness: 'Roughness',
  metallic: 'Metallic',
  ao: 'AO',
};

const EXPORT_FORMATS: ExportFormat[] = ['glb', 'gltf', 'obj', 'fbx'];

function NameEditor({ asset }: { asset: AssetMeta }) {
  const renameAsset = useStore((s) => s.renameAsset);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(asset.name);

  useEffect(() => {
    setDraft(asset.name);
    setEditing(false);
  }, [asset.id, asset.name]);

  const commit = async () => {
    setEditing(false);
    if (draft.trim() && draft.trim() !== asset.name) {
      await renameAsset(asset.id, draft);
    } else {
      setDraft(asset.name);
    }
  };

  if (!editing) {
    return (
      <div className="asset-name">
        <h2 className="asset-name__text" title={asset.name}>
          {asset.name}
        </h2>
        <button
          className="icon-btn"
          title="Rename asset"
          onClick={() => {
            setDraft(asset.name);
            setEditing(true);
          }}
        >
          <PencilIcon size={13} />
        </button>
      </div>
    );
  }

  return (
    <div className="asset-name">
      <input
        className="input asset-name__input"
        value={draft}
        autoFocus
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void commit();
          if (e.key === 'Escape') {
            setDraft(asset.name);
            setEditing(false);
          }
        }}
      />
      <button className="icon-btn" title="Save name" onMouseDown={(e) => e.preventDefault()} onClick={() => void commit()}>
        <CheckIcon size={13} />
      </button>
    </div>
  );
}

function StatRow({ label, meta, live }: { label: string; meta: string; live?: string }) {
  return (
    <tr>
      <td className="stats__label">{label}</td>
      <td className="stats__val">{meta}</td>
      <td className="stats__val stats__val--live">{live ?? '—'}</td>
    </tr>
  );
}

export function RightPanel() {
  const asset = useStore(selectSelectedAsset);
  const liveStats = useStore((s) => s.liveStats);
  const system = useStore((s) => s.system);
  const [zoomMap, setZoomMap] = useState<TextureMap | null>(null);

  if (!asset) {
    return (
      <aside className="right-panel right-panel--empty">
        <CubeIcon size={28} />
        <p>Select an asset from the library to inspect it.</p>
      </aside>
    );
  }

  const blenderOk = system?.blender ?? false;
  const v = asset.updated_at;

  return (
    <aside className="right-panel">
      <NameEditor asset={asset} />

      <div className="meta-rows">
        <div className="meta-row">
          <span className="meta-row__key">Created</span>
          <span className="meta-row__val">{formatDate(asset.created_at)}</span>
        </div>
        <div className="meta-row">
          <span className="meta-row__key">Adapter</span>
          <span className="meta-row__val mono">{asset.adapter}</span>
        </div>
        <div className="meta-row">
          <span className="meta-row__key">Source</span>
          <span className="meta-row__val meta-row__val--source">
            {sourceTypeIcon(asset.source.type, 12)}
            {asset.source.type}
          </span>
        </div>
        {asset.source.prompt && (
          <blockquote className="meta-prompt" title={asset.source.prompt}>
            “{asset.source.prompt}”
          </blockquote>
        )}
        {asset.source.image_names && asset.source.image_names.length > 0 && (
          <div className="meta-images">
            {asset.source.image_names.map((n) => (
              <span key={n} className="meta-images__pill" title={n}>
                {n}
              </span>
            ))}
          </div>
        )}
      </div>

      <section className="panel-section">
        <header className="panel-subhead">
          <span>Mesh stats</span>
        </header>
        <table className="stats">
          <thead>
            <tr>
              <th />
              <th>meta</th>
              <th title="Computed from the GLB currently loaded in the viewport">live</th>
            </tr>
          </thead>
          <tbody>
            <StatRow
              label="Vertices"
              meta={formatCount(asset.stats.vertices)}
              live={liveStats ? formatCount(liveStats.vertices) : undefined}
            />
            <StatRow
              label="Triangles"
              meta={formatCount(asset.stats.triangles)}
              live={liveStats ? formatCount(liveStats.triangles) : undefined}
            />
            <StatRow
              label="Materials"
              meta={String(asset.stats.materials)}
              live={liveStats ? String(liveStats.materials) : undefined}
            />
            <StatRow
              label="Texture size"
              meta={asset.stats.texture_size ? `${asset.stats.texture_size} px` : '—'}
              live={liveStats ? `${liveStats.textures} map${liveStats.textures === 1 ? '' : 's'}` : undefined}
            />
            <StatRow
              label="UVs"
              meta={asset.stats.has_uv ? 'yes' : 'no'}
              live={liveStats ? (liveStats.hasUv ? 'yes' : 'no') : undefined}
            />
          </tbody>
        </table>
      </section>

      {asset.textures.length > 0 && (
        <section className="panel-section">
          <header className="panel-subhead">
            <span>Texture maps</span>
            <span className="panel-subhead__count">{asset.textures.length}</span>
          </header>
          <div className="map-grid">
            {asset.textures.map((map) => (
              <button
                key={map}
                className="map-tile"
                title={`${MAP_LABEL[map]} — click to enlarge`}
                onClick={() => setZoomMap(map)}
              >
                <img src={api.textureUrl(asset.id, map, v)} alt={MAP_LABEL[map]} loading="lazy" />
                <span className="map-tile__label">{MAP_LABEL[map]}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="panel-section">
        <header className="panel-subhead">
          <span>Export</span>
        </header>
        <div className="export-grid">
          {EXPORT_FORMATS.map((fmt) => {
            const isFbx = fmt === 'fbx';
            const disabled = isFbx && !blenderOk;
            return (
              <button
                key={fmt}
                className="btn btn--ghost export-btn"
                disabled={disabled}
                title={
                  isFbx
                    ? blenderOk
                      ? 'Export FBX (converted via Blender)'
                      : 'FBX export requires Blender'
                    : fmt === 'glb'
                      ? 'Export binary glTF'
                      : `Export ${fmt.toUpperCase()} (.zip)`
                }
                onClick={() => triggerDownload(api.exportUrl(asset.id, fmt))}
              >
                <DownloadIcon size={13} />
                {fmt.toUpperCase()}
              </button>
            );
          })}
        </div>
        {!blenderOk && <div className="export-note">FBX requires Blender on the backend machine.</div>}
      </section>

      {zoomMap && (
        <Modal title={`${MAP_LABEL[zoomMap]} — ${asset.name}`} onClose={() => setZoomMap(null)}>
          <img
            className="modal__texture"
            src={api.textureUrl(asset.id, zoomMap, v)}
            alt={MAP_LABEL[zoomMap]}
          />
        </Modal>
      )}
    </aside>
  );
}
