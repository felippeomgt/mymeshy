import { useState } from 'react';
import { api } from '../../api';
import { useStore } from '../../store';
import { CubeIcon, SpinnerIcon } from '../Icons';
import { DEFAULT_OPTIONS, OptionsFields, optionsToPayload, type OptionsState } from './OptionsFields';

export function TextTo3DForm() {
  const fetchJobs = useStore((s) => s.fetchJobs);
  const backendDown = useStore((s) => s.backendDown);
  const [prompt, setPrompt] = useState('');
  const [options, setOptions] = useState<OptionsState>(DEFAULT_OPTIONS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = prompt.trim().length > 0 && !busy && !backendDown;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await api.createTextTo3d(prompt.trim(), optionsToPayload(options));
      await fetchJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit job');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gen-form">
      <label className="opt-field">
        <span className="opt-field__label">Prompt</span>
        <textarea
          className="input gen-form__prompt"
          rows={4}
          placeholder="A weathered bronze astrolabe with engraved zodiac rings…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void submit();
          }}
        />
      </label>

      <OptionsFields value={options} onChange={setOptions} />

      {error && <div className="form-error">{error}</div>}

      <button className="btn btn--primary btn--block" disabled={!canSubmit} onClick={() => void submit()}>
        {busy ? <SpinnerIcon size={15} /> : <CubeIcon size={15} />}
        Generate 3D model
      </button>
      <div className="gen-form__hint">Ctrl+Enter to generate</div>
    </div>
  );
}
