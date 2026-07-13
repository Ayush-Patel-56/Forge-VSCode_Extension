// webview-src/chat/ApprovalCard.tsx
import React, { useState } from 'react';
import { ApprovalItem } from './types';

const MONO_FONT = 'var(--vscode-editor-font-family), monospace';

export default function ApprovalCard({
  item,
  onRespond,
}: {
  item: ApprovalItem;
  onRespond: (id: string, decision: 'allow' | 'deny' | 'other', detail?: string) => void;
}) {
  const [draft, setDraft] = useState('');

  // Collapsed record once decided: dim single line styled like the status
  // milestone rows ("● approved · $ git pull").
  if (item.decision) {
    const label =
      item.decision === 'allow'
        ? `approved · $ ${item.command}`
        : item.decision === 'deny'
          ? `skipped · $ ${item.command}`
          : `redirected: ${item.detail ?? ''}`;
    return (
      <div
        style={{
          marginTop: 4,
          marginBottom: 4,
          fontSize: 11,
          fontFamily: MONO_FONT,
          color: 'var(--vscode-descriptionForeground)',
          opacity: 0.8,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
        }}
      >
        <span style={{ fontSize: 8, marginRight: 6 }}>●</span>
        {label}
      </div>
    );
  }

  const send = () => onRespond(item.id, 'other', draft);

  return (
    <div
      style={{
        marginTop: 8,
        marginBottom: 8,
        padding: 10,
        border: '1px solid var(--vscode-inputValidation-warningBorder, var(--vscode-focusBorder))',
        borderRadius: 6,
        fontFamily: MONO_FONT,
        fontSize: 12,
      }}
    >
      <div style={{ fontWeight: 600, whiteSpace: 'pre-wrap', wordBreak: 'break-all', marginBottom: 4 }}>
        $ {item.command}
      </div>
      <div style={{ fontSize: 11, color: 'var(--vscode-descriptionForeground)', marginBottom: 8 }}>
        {item.cwd}
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <button
          onClick={() => onRespond(item.id, 'allow')}
          style={{
            background: 'var(--vscode-button-background)',
            color: 'var(--vscode-button-foreground)',
            border: 'none',
            borderRadius: 4,
            padding: '4px 12px',
            fontSize: 12,
            fontFamily: 'inherit',
            cursor: 'pointer',
          }}
        >
          Run
        </button>
        <button
          onClick={() => onRespond(item.id, 'deny')}
          style={{
            background: 'var(--vscode-button-secondaryBackground)',
            color: 'var(--vscode-button-secondaryForeground)',
            border: 'none',
            borderRadius: 4,
            padding: '4px 12px',
            fontSize: 12,
            fontFamily: 'inherit',
            cursor: 'pointer',
          }}
        >
          Skip
        </button>
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <input
          type="text"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.preventDefault();
              send();
            }
          }}
          placeholder="tell Forge what to do instead..."
          style={{
            flex: 1,
            background: 'var(--vscode-input-background)',
            color: 'var(--vscode-input-foreground)',
            border: '1px solid var(--vscode-input-border)',
            borderRadius: 4,
            padding: '4px 6px',
            fontSize: 12,
            fontFamily: 'inherit',
            outline: 'none',
          }}
        />
        <button
          onClick={send}
          style={{
            background: 'var(--vscode-button-secondaryBackground)',
            color: 'var(--vscode-button-secondaryForeground)',
            border: 'none',
            borderRadius: 4,
            padding: '4px 12px',
            fontSize: 12,
            fontFamily: 'inherit',
            cursor: 'pointer',
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
