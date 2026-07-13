// webview-src/chat/InputBar.tsx
import React, { useState } from 'react';
import { Effort, Mode, ModelInfo, UsageDetails } from './types';
import ModelSelect from './ModelSelect';
import ModePopup from './ModePopup';
import ActionsPalette from './ActionsPalette';
import UsageModal from './UsageModal';

const EFFORTS: Effort[] = ['low', 'medium', 'high', 'max'];
const MONO_FONT = 'var(--vscode-editor-font-family), monospace';

export default function InputBar({
  disabled,
  thinking,
  onThinkingChange,
  effort,
  onEffortChange,
  mode,
  onModeChange,
  autoFallback,
  onAutoFallbackChange,
  models,
  activeModelId,
  onModelChange,
  tokenCount,
  costUsd,
  onSend,
  onClearConversation,
  onRewind,
  usage,
  onRequestUsage,
  onOpenAttach,
  onOpenMention,
}: {
  disabled: boolean;
  thinking: boolean;
  onThinkingChange: (v: boolean) => void;
  effort: Effort;
  onEffortChange: (e: Effort) => void;
  mode: Mode;
  onModeChange: (m: Mode) => void;
  autoFallback: boolean;
  onAutoFallbackChange: (v: boolean) => void;
  models: ModelInfo[];
  activeModelId: string | null;
  onModelChange: (id: string) => void;
  tokenCount: number;
  costUsd: number;
  onSend: (content: string) => void;
  onClearConversation: () => void;
  onRewind: () => void;
  usage: UsageDetails | null;
  onRequestUsage: () => void;
  onOpenAttach: () => void;
  onOpenMention: () => void;
}) {
  const [input, setInput] = useState('');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [usageOpen, setUsageOpen] = useState(false);

  const send = () => {
    if (!input.trim() || disabled) return;
    onSend(input.trim());
    setInput('');
  };

  return (
    <div style={{ padding: '8px 12px', borderTop: '1px solid var(--vscode-panel-border)' }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setPaletteOpen(o => !o)}
            title="Actions"
            style={{
              width: 26,
              height: 26,
              lineHeight: '24px',
              borderRadius: 6,
              background: 'var(--vscode-button-secondaryBackground)',
              color: 'var(--vscode-button-secondaryForeground)',
              border: 'none',
              fontSize: 15,
              fontFamily: 'inherit',
              cursor: 'pointer',
              flexShrink: 0,
            }}
          >
            +
          </button>
          {paletteOpen && (
            <ActionsPalette
              onClose={() => setPaletteOpen(false)}
              onClearConversation={onClearConversation}
              onRewind={onRewind}
              models={models}
              activeModelId={activeModelId}
              onModelChange={onModelChange}
              effort={effort}
              onEffortChange={onEffortChange}
              thinking={thinking}
              onThinkingChange={onThinkingChange}
              autoFallback={autoFallback}
              onAutoFallbackChange={onAutoFallbackChange}
              onOpenUsage={() => setUsageOpen(true)}
              onOpenAttach={onOpenAttach}
              onOpenMention={onOpenMention}
            />
          )}
        </div>

        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            } else if (e.key === '/' && input === '') {
              e.preventDefault();
              setPaletteOpen(true);
            }
          }}
          placeholder="Ask Forge anything... (Enter to send, Shift+Enter for newline, / for actions)"
          disabled={disabled}
          rows={3}
          style={{
            flex: 1,
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
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, fontFamily: MONO_FONT }}>
        <ModePopup mode={mode} onModeChange={onModeChange} effort={effort} onEffortChange={onEffortChange} />
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

      {usageOpen && <UsageModal usage={usage} onRequestUsage={onRequestUsage} onClose={() => setUsageOpen(false)} />}
    </div>
  );
}
