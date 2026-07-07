// webview-src/chat/InputBar.tsx
import React, { useState } from 'react';
import { Effort, ModelInfo } from './types';
import ModelSelect from './ModelSelect';

const EFFORTS: Effort[] = ['low', 'medium', 'high', 'max'];
const MONO_FONT = 'var(--vscode-editor-font-family), monospace';

export default function InputBar({
  disabled,
  thinking,
  onThinkingChange,
  effort,
  onEffortChange,
  models,
  activeModelId,
  onModelChange,
  tokenCount,
  costUsd,
  onSend,
}: {
  disabled: boolean;
  thinking: boolean;
  onThinkingChange: (v: boolean) => void;
  effort: Effort;
  onEffortChange: (e: Effort) => void;
  models: ModelInfo[];
  activeModelId: string | null;
  onModelChange: (id: string) => void;
  tokenCount: number;
  costUsd: number;
  onSend: (content: string) => void;
}) {
  const [input, setInput] = useState('');

  const send = () => {
    if (!input.trim() || disabled) return;
    onSend(input.trim());
    setInput('');
  };

  return (
    <div style={{ padding: '8px 12px', borderTop: '1px solid var(--vscode-panel-border)' }}>
      <textarea
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
          }
        }}
        placeholder="Ask Forge anything... (Enter to send, Shift+Enter for newline)"
        disabled={disabled}
        rows={3}
        style={{
          width: '100%',
          resize: 'none',
          boxSizing: 'border-box',
          background: 'var(--vscode-input-background)',
          color: 'var(--vscode-input-foreground)',
          border: '1px solid var(--vscode-input-border)',
          borderRadius: 4,
          padding: '6px 8px',
          fontSize: 13,
          fontFamily: MONO_FONT,
          outline: 'none',
        }}
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, fontFamily: MONO_FONT }}>
        <ModelSelect models={models} activeModelId={activeModelId} onSelect={onModelChange} />

        <button
          onClick={() => onThinkingChange(!thinking)}
          style={{
            background: thinking ? 'var(--vscode-button-background)' : 'var(--vscode-button-secondaryBackground)',
            color: thinking ? 'var(--vscode-button-foreground)' : 'var(--vscode-button-secondaryForeground)',
            border: 'none',
            borderRadius: 12,
            padding: '3px 10px',
            fontSize: 11,
            fontFamily: 'inherit',
            cursor: 'pointer',
          }}
        >
          ✦ think
        </button>

        <div style={{ display: 'flex', border: '1px solid var(--vscode-panel-border)', borderRadius: 4, overflow: 'hidden' }}>
          {EFFORTS.map(e => (
            <button
              key={e}
              onClick={() => onEffortChange(e)}
              style={{
                background: effort === e ? 'var(--vscode-button-background)' : 'transparent',
                color: effort === e ? 'var(--vscode-button-foreground)' : 'var(--vscode-foreground)',
                border: 'none',
                padding: '3px 8px',
                fontSize: 11,
                fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              {e}
            </button>
          ))}
        </div>

        <div style={{ flex: 1 }} />

        <div style={{ fontSize: 11, color: 'var(--vscode-descriptionForeground)' }}>
          {tokenCount.toLocaleString()}t{costUsd > 0 ? ` · $${costUsd.toFixed(4)}` : ''}
        </div>
      </div>
    </div>
  );
}
