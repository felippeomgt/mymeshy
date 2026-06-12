import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 16, ...rest }: IconProps): SVGProps<SVGSVGElement> {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.7,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
    ...rest,
  };
}

export function CubeIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 2.5 21 7.5v9L12 21.5 3 16.5v-9z" />
      <path d="M3 7.5l9 5 9-5M12 12.5v9" />
    </svg>
  );
}

export function TextIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 6V4h16v2M12 4v16M8 20h8" />
    </svg>
  );
}

export function ImageIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="9" cy="10" r="1.8" />
      <path d="M3.5 17.5 9 13l4 3.5 4-3 3.5 3" />
    </svg>
  );
}

export function BrushIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M14.5 3.5 20.5 9.5 9 21H3v-6z" />
      <path d="M12 6l6 6" />
    </svg>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
    </svg>
  );
}

export function XIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 3v11M7 10l5 5 5-5M4 19h16" />
    </svg>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 16V5M7 9l5-5 5 5M4 19h16" />
    </svg>
  );
}

export function PencilIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19z" />
      <path d="M14 6.5 17.5 10" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 12.5 9.5 18 20 6.5" />
    </svg>
  );
}

export function StopIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="6" y="6" width="12" height="12" rx="1.5" />
    </svg>
  );
}

export function GridIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
    </svg>
  );
}

export function ContrastIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3v18A9 9 0 0 0 12 3z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function FrameIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  );
}

export function WarnIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 3 2.5 20h19z" />
      <path d="M12 9.5v5M12 17.5v.5" />
    </svg>
  );
}

export function SpinnerIcon(props: IconProps) {
  return (
    <svg {...base(props)} className={`spin ${props.className ?? ''}`}>
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  );
}

export function jobTypeIcon(type: string, size = 14) {
  switch (type) {
    case 'text_to_3d':
      return <TextIcon size={size} />;
    case 'image_to_3d':
      return <ImageIcon size={size} />;
    case 'texture':
      return <BrushIcon size={size} />;
    default:
      return <CubeIcon size={size} />;
  }
}

export function sourceTypeIcon(type: string, size = 14) {
  switch (type) {
    case 'text':
      return <TextIcon size={size} />;
    case 'image':
      return <ImageIcon size={size} />;
    case 'texture':
      return <BrushIcon size={size} />;
    default:
      return <CubeIcon size={size} />;
  }
}
