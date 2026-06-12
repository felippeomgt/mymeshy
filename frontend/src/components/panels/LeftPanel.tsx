import { useState } from 'react';
import { BrushIcon, ImageIcon, TextIcon } from '../Icons';
import { TextTo3DForm } from './TextTo3DForm';
import { ImageTo3DForm } from './ImageTo3DForm';
import { TextureForm } from './TextureForm';
import { JobsList } from './JobsList';

type Tab = 'text' | 'image' | 'texture';

const TABS: { id: Tab; label: string; icon: JSX.Element }[] = [
  { id: 'text', label: 'Text to 3D', icon: <TextIcon size={14} /> },
  { id: 'image', label: 'Image to 3D', icon: <ImageIcon size={14} /> },
  { id: 'texture', label: 'Texture', icon: <BrushIcon size={14} /> },
];

export function LeftPanel() {
  const [tab, setTab] = useState<Tab>('text');

  return (
    <aside className="left-panel">
      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tabs__btn ${tab === t.id ? 'tabs__btn--active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </nav>

      <div className="left-panel__form">
        {tab === 'text' && <TextTo3DForm />}
        {tab === 'image' && <ImageTo3DForm />}
        {tab === 'texture' && <TextureForm />}
      </div>

      <div className="left-panel__jobs">
        <JobsList />
      </div>
    </aside>
  );
}
