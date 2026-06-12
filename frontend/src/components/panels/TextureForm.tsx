import { useEffect, useRef, useState } from 'react';
import { api } from '../../api';
import { useStore } from '../../store';
import { BrushIcon, SpinnerIcon, XIcon } from '../Icons';
import { DEFAULT_OPTIONS, OptionsFields, optionsToPayload, type OptionsState } from './OptionsFields';

type MeshSource = 'library' | 'upload';

export function TextureForm() {
  const fetchJobs = useStore((s) => s.fetchJobs);
  const backendDown = useStore((s) => s.backendDown);
  const assets = useStore((s) => s.assets);
  const selectedAssetId = useStore((s) => s.selectedAssetId);

  const [source, setSource] = useState<MeshSource>('library');
  const [assetId, setAssetId] = useState('');
  const [meshFile, setMeshFile] = useState<File | null>(null);
  const [prompt, setPrompt] = useState('');
  const [refImage, setRefImage] = useState<File | null>(null);
  const [refUrl, setRefUrl] = useState<string | null>(null);
  const [options, setOptions] = useState<OptionsState>(DEFAULT_OPTIONS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const meshInputRef = useRef<HTMLInputElement>(null);
  const imgInputRef = useRef<HTMLInputElement>(null);

  // Default the dropdown to the asset selected in the viewport.
  useEffect(() => {
    if (selectedAssetId) setAssetId(selectedAssetId);
  }, [selectedAssetId]);

  useEffect(() => () => {
    if (refUrl) URL.revokeObjectURL(refUrl);
  }, [refUrl]);

  const setReference = (file: File | null) => {
    if (refUrl) URL.revokeObjectURL(refUrl);
    setRefImage(file);
    setRefUrl(file ? URL.createObjectURL(file) : null);
  };

  const hasMesh = source === 'library' ? assetId !== '' : meshFile !== null;
  const hasGuide = prompt.trim().length > 0 || refImage !== null;
  const canSubmit = hasMesh && hasGuide && !busy && !backendDown;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await api.createTexture({
        assetId: source === 'library' ? assetId : undefined,
        mesh: source === 'upload' ? meshFile ?? undefined : undefined,
        prompt: prompt.trim() || undefined,
        image: refImage ?? undefined,
        options: optionsToPayload(options),
      });
      await fetchJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit job');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gen-form">
      <div className="seg">
        <button
          className={`seg__btn ${source === 'library' ? 'seg__btn--active' : ''}`}
          onClick={() => setSource('library')}
        >
          From library
        </button>
        <button
          className={`seg__btn ${source === 'upload' ? 'seg__btn--active' : ''}`}
          onClick={() => setSource('upload')}
        >
          Upload mesh
        </button>
      </div>

      {source === 'library' ? (
        <label className="opt-field">
          <span className="opt-field__label">Asset</span>
          <select className="input" value={assetId} onChange={(e) => setAssetId(e.target.value)}>
            <option value="">— select an asset —</option>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <div className="opt-field">
          <span className="opt-field__label">Mesh file (.glb / .obj)</span>
          {meshFile ? (
            <div className="file-pill">
              <span className="file-pill__name" title={meshFile.name}>
                {meshFile.name}
              </span>
              <button className="icon-btn" title="Remove mesh" onClick={() => setMeshFile(null)}>
                <XIcon size={11} />
              </button>
            </div>
          ) : (
            <button className="btn btn--ghost" onClick={() => meshInputRef.current?.click()}>
              Choose mesh file…
            </button>
          )}
          <input
            ref={meshInputRef}
            type="file"
            accept=".glb,.obj"
            hidden
            onChange={(e) => {
              setMeshFile(e.target.files?.[0] ?? null);
              e.target.value = '';
            }}
          />
        </div>
      )}

      <label className="opt-field">
        <span className="opt-field__label">
          Texture prompt <span className="opt-field__hint">(and/or reference image)</span>
        </span>
        <textarea
          className="input gen-form__prompt"
          rows={3}
          placeholder="Rusted sci-fi armor plating, chipped orange paint…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
      </label>

      <div className="opt-field">
        <span className="opt-field__label">Reference image</span>
        {refImage && refUrl ? (
          <div className="thumb-row">
            <div className="thumb" title={refImage.name}>
              <img src={refUrl} alt={refImage.name} />
              <button className="thumb__remove" title="Remove image" onClick={() => setReference(null)}>
                <XIcon size={10} />
              </button>
            </div>
          </div>
        ) : (
          <button className="btn btn--ghost" onClick={() => imgInputRef.current?.click()}>
            Choose image…
          </button>
        )}
        <input
          ref={imgInputRef}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            setReference(e.target.files?.[0] ?? null);
            e.target.value = '';
          }}
        />
      </div>

      <OptionsFields value={options} onChange={setOptions} meshOptions={false} adapterKind="texturing" />

      {error && <div className="form-error">{error}</div>}

      <button className="btn btn--primary btn--block" disabled={!canSubmit} onClick={() => void submit()}>
        {busy ? <SpinnerIcon size={15} /> : <BrushIcon size={15} />}
        Generate textures
      </button>
      {!hasGuide && <div className="gen-form__hint">Provide a prompt or a reference image</div>}
    </div>
  );
}
