import { useEffect, useState } from 'react';
import { api } from '../../api';
import { useStore } from '../../store';
import type { AssetMeta } from '../../types';
import { relativeTime } from '../../utils';
import { sourceTypeIcon, TrashIcon } from '../Icons';

function AssetCard({ asset, selected }: { asset: AssetMeta; selected: boolean }) {
  const selectAsset = useStore((s) => s.selectAsset);
  const deleteAsset = useStore((s) => s.deleteAsset);
  const [confirming, setConfirming] = useState(false);
  const [thumbOk, setThumbOk] = useState(true);

  // Auto-dismiss the delete confirmation.
  useEffect(() => {
    if (!confirming) return;
    const id = window.setTimeout(() => setConfirming(false), 2500);
    return () => window.clearTimeout(id);
  }, [confirming]);

  const hasAlbedo = asset.textures.includes('albedo') && thumbOk;

  return (
    <div
      className={`asset-card ${selected ? 'asset-card--selected' : ''}`}
      onClick={() => selectAsset(asset.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter') selectAsset(asset.id);
      }}
      title={asset.name}
    >
      <div className="asset-card__thumb">
        {hasAlbedo ? (
          <img
            src={api.textureUrl(asset.id, 'albedo', asset.updated_at)}
            alt=""
            loading="lazy"
            onError={() => setThumbOk(false)}
          />
        ) : (
          <span className="asset-card__placeholder">{sourceTypeIcon(asset.source.type, 22)}</span>
        )}
      </div>
      <div className="asset-card__info">
        <span className="asset-card__name">{asset.name}</span>
        <span className="asset-card__date">{relativeTime(asset.created_at)}</span>
      </div>
      <button
        className={`asset-card__delete ${confirming ? 'asset-card__delete--confirm' : ''}`}
        title={confirming ? 'Click again to delete permanently' : 'Delete asset'}
        onClick={(e) => {
          e.stopPropagation();
          if (confirming) void deleteAsset(asset.id);
          else setConfirming(true);
        }}
      >
        {confirming ? 'sure?' : <TrashIcon size={12} />}
      </button>
    </div>
  );
}

export function AssetLibrary() {
  const assets = useStore((s) => s.assets);
  const selectedAssetId = useStore((s) => s.selectedAssetId);

  return (
    <section className="library">
      <header className="library__head">
        <span className="panel-subhead__title">Asset library</span>
        <span className="panel-subhead__count">{assets.length}</span>
      </header>
      {assets.length === 0 ? (
        <div className="library__empty">
          Nothing here yet — your generated assets will appear in this strip.
        </div>
      ) : (
        <div className="library__row">
          {assets.map((a) => (
            <AssetCard key={a.id} asset={a} selected={a.id === selectedAssetId} />
          ))}
        </div>
      )}
    </section>
  );
}
