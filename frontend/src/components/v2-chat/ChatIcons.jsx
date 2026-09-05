function IconFrame({ children, className = "" }) {
  return (
    <svg className={`v2-icon ${className}`.trim()} viewBox="0 0 24 24" aria-hidden="true">
      {children}
    </svg>
  );
}

export function AddIcon() {
  return <IconFrame><path d="M12 5v14M5 12h14" /></IconFrame>;
}

export function HistoryIcon() {
  return <IconFrame><path d="M8 7h11M8 12h11M8 17h11" /><circle cx="4.5" cy="7" r=".75" /><circle cx="4.5" cy="12" r=".75" /><circle cx="4.5" cy="17" r=".75" /></IconFrame>;
}

export function MaximizeIcon() {
  return <IconFrame><path d="M8 4H4v4M16 4h4v4M20 16v4h-4M8 20H4v-4" /></IconFrame>;
}

export function RestoreIcon() {
  return <IconFrame><rect x="7" y="7" width="12" height="12" rx="1.5" /><path d="M16 7V5H5v11h2" /></IconFrame>;
}

export function MinimizeIcon() {
  return <IconFrame><path d="M5 12h14" /></IconFrame>;
}

export function ArrowUpIcon() {
  return <IconFrame><path d="M12 18V6M7.5 10.5 12 6l4.5 4.5" /></IconFrame>;
}

export function ArrowDownIcon() {
  return <IconFrame><path d="M12 6v12M7.5 13.5 12 18l4.5-4.5" /></IconFrame>;
}

export function StopIcon() {
  return <IconFrame><rect x="7" y="7" width="10" height="10" rx="1.5" /></IconFrame>;
}

export function CheckIcon() {
  return <IconFrame><path d="m6 12.5 3.5 3.5L18 7.5" /></IconFrame>;
}

export function CloseIcon() {
  return <IconFrame><path d="m7 7 10 10M17 7 7 17" /></IconFrame>;
}

export function SpinnerIcon() {
  return <IconFrame className="v2-icon-spinner"><circle cx="12" cy="12" r="7.5" /></IconFrame>;
}
