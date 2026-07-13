// webview-src/chat/ModelSelect.tsx
import React, { useEffect, useRef, useState } from 'react';
import { ModelInfo } from './types';

function ModelList({
  models,
  activeModelId,
  onSelect,
}: {
  models: ModelInfo[];
  activeModelId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <>
      {models.length === 0 && (
        <div style={{ padding: '8px 10px', fontSize: 12, color: 'var(--vscode-descriptionForeground)' }}>
          No models available
        </div>
      )}
      {models.map(m => (
        <div
          key={m.id}
          onClick={() => onSelect(m.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            padding: '6px 10px',
            fontSize: 12,
            cursor: 'pointer',
            background: m.id === activeModelId ? 'var(--vscode-list-activeSelectionBackground)' : 'transparent',
            color: m.id === activeModelId ? 'var(--vscode-list-activeSelectionForeground)' : 'var(--vscode-foreground)',
          }}
        >
          <span>{m.display_name}</span>
          {m.is_free && (
            <span
              style={{
                fontSize: 10,
                padding: '1px 6px',
                borderRadius: 8,
                background: 'var(--vscode-badge-background)',
                color: 'var(--vscode-badge-foreground)',
              }}
            >
              free
            </span>
          )}
        </div>
      ))}
    </>
  );
}

export default function ModelSelect({
  models,
  activeModelId,
  onSelect,
  inline,
}: {
  models: ModelInfo[];
  activeModelId: string | null;
  onSelect: (id: string) => void;
  /**
   * Render just the selectable list, with no trigger button and no absolute
   * positioning — used to embed this same picker inside the actions palette's
   * "Switch model…" sub-view instead of duplicating the list markup.
   */
  inline?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close the popup on outside click.
  useEffect(() => {
    if (!open || inline) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocMouseDown);
    return () => document.removeEventListener('mousedown', onDocMouseDown);
  }, [open, inline]);

  if (inline) {
    return (
      <div style={{ maxHeight: 260, overflowY: 'auto' }}>
        <ModelList models={models} activeModelId={activeModelId} onSelect={onSelect} />
      </div>
    );
  }

  const active = models.find(m => m.id === activeModelId);
  const shortName = active?.display_name ?? activeModelId ?? 'model';

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
        {shortName}
        <span style={{ fontSize: 8 }}>▲</span>
      </button>
      {open && (
        <div
          style={{
            position: 'absolute',
            bottom: '100%',
            left: 0,
            marginBottom: 4,
            minWidth: 220,
            maxHeight: 260,
            overflowY: 'auto',
            background: 'var(--vscode-editorWidget-background)',
            border: '1px solid var(--vscode-widget-border, var(--vscode-panel-border))',
            borderRadius: 6,
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
            zIndex: 10,
          }}
        >
          <ModelList
            models={models}
            activeModelId={activeModelId}
            onSelect={id => {
              onSelect(id);
              setOpen(false);
            }}
          />
        </div>
      )}
    </div>
  );
}
