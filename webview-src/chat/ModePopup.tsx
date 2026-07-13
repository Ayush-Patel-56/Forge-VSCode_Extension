// webview-src/chat/ModePopup.tsx
import React, { useEffect, useRef, useState } from 'react';
import { Effort, Mode } from './types';

const MONO_FONT = 'var(--vscode-editor-font-family), monospace';

const MODES: { id: Mode; icon: string; name: string; desc: string }[] = [
  { id: 'manual', icon: '✋', name: 'Manual', desc: 'Forge asks for approval before every command and edit' },
  { id: 'auto', icon: '⚡', name: 'Auto', desc: 'Safe read-only actions run automatically; risky ones pause for approval' },
  { id: 'edit', icon: '✎', name: 'Edit automatically', desc: 'File edits also run without asking' },
  { id: 'plan', icon: '☰', name: 'Plan', desc: 'Explore read-only and present a plan before changing anything' },
];

const EFFORTS: Effort[] = ['low', 'medium', 'high', 'max'];

export default function ModePopup({
  mode,
  onModeChange,
  effort,
  onEffortChange,
}: {
  mode: Mode;
  onModeChange: (m: Mode) => void;
  effort: Effort;
  onEffortChange: (e: Effort) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocMouseDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const active = MODES.find(m => m.id === mode) ?? MODES[0];
  const effortIdx = EFFORTS.indexOf(effort);

  return (
    <div ref={rootRef} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          background: 'var(--vscode-dropdown-background, var(--vscode-editorWidget-background))',
          color: 'var(--vscode-foreground)',
          border: '1px solid var(--vscode-dropdown-border, var(--vscode-panel-border))',
          borderRadius: 4,
          padding: '3px 8px',
          fontSize: 11,
          fontFamily: 'inherit',
          cursor: 'pointer',
        }}
      >
        <span>{active.icon}</span>
        <span>{active.name}</span>
        <span style={{ fontSize: 8 }}>▲</span>
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            bottom: '100%',
            left: 0,
            marginBottom: 4,
            width: 300,
            background: 'var(--vscode-editorWidget-background)',
            border: '1px solid var(--vscode-widget-border, var(--vscode-panel-border))',
            borderRadius: 6,
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
            zIndex: 10,
            fontFamily: MONO_FONT,
            overflow: 'hidden',
          }}
        >
          {MODES.map(m => (
            <div
              key={m.id}
              onClick={() => {
                onModeChange(m.id);
                setOpen(false);
              }}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                padding: '8px 10px',
                cursor: 'pointer',
                background: m.id === mode ? 'var(--vscode-list-activeSelectionBackground)' : 'transparent',
                color: m.id === mode ? 'var(--vscode-list-activeSelectionForeground)' : 'var(--vscode-foreground)',
              }}
            >
              <span style={{ fontSize: 14, lineHeight: '16px' }}>{m.icon}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 12 }}>{m.name}</div>
                <div style={{ fontSize: 10.5, color: 'var(--vscode-descriptionForeground)', marginTop: 2, whiteSpace: 'normal' }}>
                  {m.desc}
                </div>
              </div>
              <span style={{ fontSize: 12, width: 12, textAlign: 'center' }}>{m.id === mode ? '✓' : ''}</span>
            </div>
          ))}

          <div style={{ borderTop: '1px solid var(--vscode-panel-border)', padding: '8px 10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 600 }}>Effort</span>
              <span style={{ fontSize: 10.5, color: 'var(--vscode-descriptionForeground)', textTransform: 'capitalize' }}>{effort}</span>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {EFFORTS.map((e, i) => (
                <div
                  key={e}
                  onClick={() => onEffortChange(e)}
                  title={e}
                  style={{
                    flex: 1,
                    height: 6,
                    borderRadius: 3,
                    cursor: 'pointer',
                    background: i <= effortIdx ? 'var(--vscode-button-background)' : 'var(--vscode-panel-border)',
                  }}
                />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
