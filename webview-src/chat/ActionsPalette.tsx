// webview-src/chat/ActionsPalette.tsx
//
// Filterable actions menu opened via the "+" button (or typing "/" at the
// start of an empty textarea). Renders a flat, keyboard-navigable list of
// actions grouped into sections; some rows are simple nav/button actions,
// others (Effort, Thinking, Auto-fallback) carry their own inline control
// and are kept in sync with the same state InputBar/ModePopup use.
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Effort, ModelInfo } from './types';
import ModelSelect from './ModelSelect';

const MONO_FONT = 'var(--vscode-editor-font-family), monospace';
const EFFORTS: Effort[] = ['low', 'medium', 'high', 'max'];

function Switch({ on }: { on: boolean }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 26,
        height: 14,
        borderRadius: 7,
        background: on ? 'var(--vscode-button-background)' : 'var(--vscode-panel-border)',
        position: 'relative',
        flexShrink: 0,
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 2,
          left: on ? 14 : 2,
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: 'var(--vscode-button-foreground, #fff)',
          transition: 'left 0.1s',
        }}
      />
    </span>
  );
}

interface PaletteAction {
  id: string;
  section: 'Context' | 'Model';
  label: string;
  render: (highlighted: boolean) => React.ReactNode;
  activate: () => void;
  /** Row owns its own click targets (e.g. segmented control); skip the row-level onClick wrapper. */
  selfManagedClick?: boolean;
}

export interface ActionsPaletteProps {
  onClose: () => void;
  onClearConversation: () => void;
  onRewind: () => void;
  models: ModelInfo[];
  activeModelId: string | null;
  onModelChange: (id: string) => void;
  effort: Effort;
  onEffortChange: (e: Effort) => void;
  thinking: boolean;
  onThinkingChange: (v: boolean) => void;
  autoFallback: boolean;
  onAutoFallbackChange: (v: boolean) => void;
  onOpenUsage: () => void;
  onAttachImage: () => void;
  workspaceFiles: string[];
  onRequestWorkspaceFiles: (query: string) => void;
  onAttachFile: (relPath: string) => void;
  onMentionFile: (relPath: string) => void;
}

export default function ActionsPalette({
  onClose,
  onClearConversation,
  onRewind,
  models,
  activeModelId,
  onModelChange,
  effort,
  onEffortChange,
  thinking,
  onThinkingChange,
  autoFallback,
  onAutoFallbackChange,
  onOpenUsage,
  onAttachImage,
  workspaceFiles,
  onRequestWorkspaceFiles,
  onAttachFile,
  onMentionFile,
}: ActionsPaletteProps) {
  const [filter, setFilter] = useState('');
  const [highlighted, setHighlighted] = useState(0);
  const [subview, setSubview] = useState<'root' | 'model' | 'attach' | 'mention'>('root');
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onDocMouseDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', onDocMouseDown);
    return () => document.removeEventListener('mousedown', onDocMouseDown);
  }, [onClose]);

  const activeModelName = models.find(m => m.id === activeModelId)?.display_name ?? activeModelId ?? 'model';

  const actions: PaletteAction[] = useMemo(
    () => [
      {
        id: 'attach-image',
        section: 'Context',
        label: 'Attach image…',
        activate: () => {
          onAttachImage();
          onClose();
        },
        render: highlighted => <Row highlighted={highlighted} icon="🖼" label="Attach image…" />,
      },
      {
        id: 'attach-file',
        section: 'Context',
        label: 'Attach file…',
        activate: () => setSubview('attach'),
        render: highlighted => <Row highlighted={highlighted} icon="📎" label="Attach file…" />,
      },
      {
        id: 'mention-file',
        section: 'Context',
        label: 'Mention file from this project…',
        activate: () => setSubview('mention'),
        render: highlighted => <Row highlighted={highlighted} icon="@" label="Mention file from this project…" />,
      },
      {
        id: 'clear-conversation',
        section: 'Context',
        label: 'Clear conversation',
        activate: () => {
          onClearConversation();
          onClose();
        },
        render: highlighted => <Row highlighted={highlighted} icon="⌫" label="Clear conversation" />,
      },
      {
        id: 'rewind',
        section: 'Context',
        label: 'Rewind',
        activate: () => {
          onRewind();
          onClose();
        },
        render: highlighted => <Row highlighted={highlighted} icon="↺" label="Rewind" />,
      },
      {
        id: 'switch-model',
        section: 'Model',
        label: 'Switch model…',
        activate: () => setSubview('model'),
        render: highlighted => <Row highlighted={highlighted} icon="◆" label="Switch model…" right={activeModelName} />,
      },
      {
        id: 'effort',
        section: 'Model',
        label: 'Effort',
        activate: () => {},
        selfManagedClick: true,
        render: highlighted => (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '6px 10px',
              background: highlighted ? 'var(--vscode-list-hoverBackground)' : 'transparent',
            }}
          >
            <span style={{ fontSize: 12 }}>Effort</span>
            <div style={{ display: 'flex', border: '1px solid var(--vscode-panel-border)', borderRadius: 4, overflow: 'hidden' }}>
              {EFFORTS.map(e => (
                <span
                  key={e}
                  onClick={() => onEffortChange(e)}
                  style={{
                    background: effort === e ? 'var(--vscode-button-background)' : 'transparent',
                    color: effort === e ? 'var(--vscode-button-foreground)' : 'var(--vscode-foreground)',
                    padding: '2px 6px',
                    fontSize: 10.5,
                    cursor: 'pointer',
                  }}
                >
                  {e}
                </span>
              ))}
            </div>
          </div>
        ),
      },
      {
        id: 'thinking',
        section: 'Model',
        label: 'Thinking',
        activate: () => onThinkingChange(!thinking),
        render: highlighted => <Row highlighted={highlighted} icon="✦" label="Thinking" rightNode={<Switch on={thinking} />} />,
      },
      {
        id: 'auto-fallback',
        section: 'Model',
        label: 'Auto-switch models on failure',
        activate: () => onAutoFallbackChange(!autoFallback),
        render: highlighted => (
          <Row highlighted={highlighted} icon="⇄" label="Auto-switch models on failure" rightNode={<Switch on={autoFallback} />} />
        ),
      },
      {
        id: 'usage',
        section: 'Model',
        label: 'Account & usage…',
        activate: () => {
          onOpenUsage();
          onClose();
        },
        render: highlighted => <Row highlighted={highlighted} icon="▤" label="Account & usage…" />,
      },
    ],
    [
      activeModelName, effort, thinking, autoFallback,
      onAttachImage, onClearConversation, onRewind, onClose,
      onEffortChange, onThinkingChange, onAutoFallbackChange, onOpenUsage,
    ]
  );

  const filtered = useMemo(
    () => actions.filter(a => a.label.toLowerCase().includes(filter.toLowerCase())),
    [actions, filter]
  );

  useEffect(() => {
    setHighlighted(0);
  }, [filter]);

  if (subview === 'attach' || subview === 'mention') {
    return (
      <div ref={rootRef} style={paletteContainerStyle}>
        <div
          onClick={() => setSubview('root')}
          style={{ padding: '8px 10px', fontSize: 11, color: 'var(--vscode-descriptionForeground)', cursor: 'pointer', borderBottom: '1px solid var(--vscode-panel-border)' }}
        >
          ← Back · {subview === 'attach' ? 'Attach file' : 'Mention file'}
        </div>
        <FilePicker
          files={workspaceFiles}
          onQueryChange={onRequestWorkspaceFiles}
          onEscape={onClose}
          onPick={relPath => {
            if (subview === 'attach') onAttachFile(relPath);
            else onMentionFile(relPath);
            onClose();
          }}
        />
      </div>
    );
  }

  if (subview === 'model') {
    return (
      <div ref={rootRef} style={paletteContainerStyle}>
        <div
          onClick={() => setSubview('root')}
          style={{ padding: '8px 10px', fontSize: 11, color: 'var(--vscode-descriptionForeground)', cursor: 'pointer', borderBottom: '1px solid var(--vscode-panel-border)' }}
        >
          ← Back
        </div>
        <ModelSelect
          inline
          models={models}
          activeModelId={activeModelId}
          onSelect={id => {
            onModelChange(id);
            onClose();
          }}
        />
      </div>
    );
  }

  let sectionCursor = -1;
  const sections: { name: string; items: { action: PaletteAction; index: number }[] }[] = [];
  for (const action of filtered) {
    sectionCursor++;
    let bucket = sections.find(s => s.name === action.section);
    if (!bucket) {
      bucket = { name: action.section, items: [] };
      sections.push(bucket);
    }
    bucket.items.push({ action, index: sectionCursor });
  }

  return (
    <div ref={rootRef} style={paletteContainerStyle}>
      <input
        ref={inputRef}
        value={filter}
        onChange={e => setFilter(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Escape') {
            e.preventDefault();
            onClose();
          } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            setHighlighted(h => Math.min(h + 1, filtered.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setHighlighted(h => Math.max(h - 1, 0));
          } else if (e.key === 'Enter') {
            e.preventDefault();
            filtered[highlighted]?.activate();
          }
        }}
        placeholder="Filter actions..."
        style={{
          width: '100%',
          boxSizing: 'border-box',
          background: 'var(--vscode-input-background)',
          color: 'var(--vscode-input-foreground)',
          border: 'none',
          borderBottom: '1px solid var(--vscode-panel-border)',
          padding: '8px 10px',
          fontSize: 12,
          fontFamily: 'inherit',
          outline: 'none',
        }}
      />
      <div style={{ maxHeight: 320, overflowY: 'auto' }}>
        {filtered.length === 0 && (
          <div style={{ padding: '10px', fontSize: 12, color: 'var(--vscode-descriptionForeground)' }}>No matching actions</div>
        )}
        {sections.map(sec => (
          <div key={sec.name}>
            <div style={{ padding: '6px 10px 2px', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--vscode-descriptionForeground)' }}>
              {sec.name}
            </div>
            {sec.items.map(({ action, index }) => (
              <div
                key={action.id}
                onClick={action.selfManagedClick ? undefined : action.activate}
                onMouseEnter={() => setHighlighted(index)}
                style={{ cursor: action.selfManagedClick ? 'default' : 'pointer' }}
              >
                {action.render(index === highlighted)}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function Row({
  icon,
  label,
  right,
  rightNode,
  highlighted,
}: {
  icon: string;
  label: string;
  right?: string;
  rightNode?: React.ReactNode;
  highlighted: boolean;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 10px',
        fontSize: 12,
        background: highlighted ? 'var(--vscode-list-hoverBackground)' : 'transparent',
      }}
    >
      <span style={{ width: 14, textAlign: 'center', flexShrink: 0 }}>{icon}</span>
      <span style={{ flex: 1 }}>{label}</span>
      {right && <span style={{ fontSize: 10.5, color: 'var(--vscode-descriptionForeground)' }}>{right}</span>}
      {rightNode}
    </div>
  );
}

/**
 * Workspace file sub-list shared by "Attach file…" and "Mention file…":
 * a filter input debounced ~200ms into REQUEST_WORKSPACE_FILES, with
 * keyboard navigation over the returned relative paths. The debounce timer
 * is cancelled on unmount.
 */
function FilePicker({
  files,
  onQueryChange,
  onPick,
  onEscape,
}: {
  files: string[];
  onQueryChange: (query: string) => void;
  onPick: (relPath: string) => void;
  onEscape: () => void;
}) {
  const [query, setQuery] = useState('');
  const [highlighted, setHighlighted] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Initial (unfiltered) listing on open; debounced re-query as the user
  // types. One effect owns the timer so it is always cancelled on unmount.
  useEffect(() => {
    debounceRef.current = setTimeout(() => onQueryChange(query), 200);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  useEffect(() => {
    setHighlighted(0);
  }, [files]);

  return (
    <>
      <input
        ref={inputRef}
        value={query}
        onChange={e => setQuery(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Escape') {
            e.preventDefault();
            onEscape();
          } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            setHighlighted(h => Math.min(h + 1, files.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setHighlighted(h => Math.max(h - 1, 0));
          } else if (e.key === 'Enter') {
            e.preventDefault();
            const picked = files[highlighted];
            if (picked) onPick(picked);
          }
        }}
        placeholder="Filter files..."
        style={{
          width: '100%',
          boxSizing: 'border-box',
          background: 'var(--vscode-input-background)',
          color: 'var(--vscode-input-foreground)',
          border: 'none',
          borderBottom: '1px solid var(--vscode-panel-border)',
          padding: '8px 10px',
          fontSize: 12,
          fontFamily: 'inherit',
          outline: 'none',
        }}
      />
      <div style={{ maxHeight: 260, overflowY: 'auto' }}>
        {files.length === 0 && (
          <div style={{ padding: 10, fontSize: 12, color: 'var(--vscode-descriptionForeground)' }}>No matching files</div>
        )}
        {files.map((f, i) => (
          <div
            key={f}
            onClick={() => onPick(f)}
            onMouseEnter={() => setHighlighted(i)}
            style={{
              padding: '5px 10px',
              fontSize: 11.5,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              background: i === highlighted ? 'var(--vscode-list-hoverBackground)' : 'transparent',
            }}
            title={f}
          >
            {f}
          </div>
        ))}
      </div>
    </>
  );
}

const paletteContainerStyle: React.CSSProperties = {
  position: 'absolute',
  bottom: '100%',
  left: 0,
  marginBottom: 4,
  width: 320,
  background: 'var(--vscode-editorWidget-background)',
  border: '1px solid var(--vscode-widget-border, var(--vscode-panel-border))',
  borderRadius: 6,
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
  zIndex: 20,
  fontFamily: MONO_FONT,
  overflow: 'hidden',
};
