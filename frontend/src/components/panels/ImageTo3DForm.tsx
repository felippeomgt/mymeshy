import { useEffect, useRef, useState, type DragEvent } from 'react';
import { api } from '../../api';
import { useStore } from '../../store';
import { localId } from '../../utils';
import { CubeIcon, SpinnerIcon, UploadIcon, XIcon } from '../Icons';
import { DEFAULT_OPTIONS, OptionsFields, optionsToPayload, type OptionsState } from './OptionsFields';

interface PickedImage {
  id: string;
  file: File;
  url: string;
}

export function ImageTo3DForm() {
  const fetchJobs = useStore((s) => s.fetchJobs);
  const backendDown = useStore((s) => s.backendDown);
  const [images, setImages] = useState<PickedImage[]>([]);
  const [options, setOptions] = useState<OptionsState>(DEFAULT_OPTIONS);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const imagesRef = useRef<PickedImage[]>([]);
  imagesRef.current = images;

  // Revoke object URLs on unmount.
  useEffect(
    () => () => imagesRef.current.forEach((i) => URL.revokeObjectURL(i.url)),
    [],
  );

  const addFiles = (files: FileList | File[]) => {
    const picked: PickedImage[] = [];
    for (const file of Array.from(files)) {
      if (!file.type.startsWith('image/')) continue;
      picked.push({ id: localId(), file, url: URL.createObjectURL(file) });
    }
    if (picked.length) setImages((prev) => [...prev, ...picked]);
  };

  const removeImage = (id: string) => {
    setImages((prev) => {
      const target = prev.find((i) => i.id === id);
      if (target) URL.revokeObjectURL(target.url);
      return prev.filter((i) => i.id !== id);
    });
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  const canSubmit = images.length > 0 && !busy && !backendDown;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await api.createImageTo3d(
        images.map((i) => i.file),
        optionsToPayload(options),
      );
      await fetchJobs();
      images.forEach((i) => URL.revokeObjectURL(i.url));
      setImages([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit job');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gen-form">
      <div
        className={`dropzone ${dragOver ? 'dropzone--over' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
        }}
      >
        <UploadIcon size={20} />
        <div>
          <strong>Drop reference images</strong>
          <span> or click to browse</span>
        </div>
        <div className="dropzone__hint">PNG · JPG · WebP — one or more views</div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {images.length > 0 && (
        <div className="thumb-row">
          {images.map((img) => (
            <div key={img.id} className="thumb" title={img.file.name}>
              <img src={img.url} alt={img.file.name} />
              <button
                className="thumb__remove"
                title="Remove image"
                onClick={(e) => {
                  e.stopPropagation();
                  removeImage(img.id);
                }}
              >
                <XIcon size={10} />
              </button>
            </div>
          ))}
        </div>
      )}

      <OptionsFields value={options} onChange={setOptions} />

      {error && <div className="form-error">{error}</div>}

      <button className="btn btn--primary btn--block" disabled={!canSubmit} onClick={() => void submit()}>
        {busy ? <SpinnerIcon size={15} /> : <CubeIcon size={15} />}
        Generate from {images.length || ''} image{images.length === 1 ? '' : 's'}
      </button>
    </div>
  );
}
