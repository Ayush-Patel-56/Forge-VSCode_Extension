// webview-src/chat/ToolBlock.tsx
import React from 'react';
import { ToolItem } from './types';

const MONO_FONT = 'var(--vscode-editor-font-family), monospace';

function compactArgsPreview(args: unknown): string {
  if (args == null) return '';
  try {
    const s = JSON.stringify(args);
    if (!s || s === '{}') return '';
    return s.length > 80 ? `${s.slice(0, 80)}…` : s;
  } catch {
    return '';
  }
}

function formatHeader(item: ToolItem): string {
  if (item.name === 'terminal.run_command') {
    const command = (item.args as { command?: string } | undefined)?.command ?? '';
    return `$ ${command}`;
  }
  const preview = compactArgsPreview(item.args);
  return `⚙ ${item.name}${preview ? ` ${preview}` : ''}`;
}

export default function ToolBlock({ item }: { item: ToolItem }) {
  const failed = item.result?.ok === false;

  return (
    <div
      style={{
        marginTop: 8,
        marginBottom: 8,
        border: '1px solid var(--vscode-panel-border)',
        borderLeft: failed
          ? '3px solid var(--vscode-inputValidation-errorBorder, #f14c4c)'
          : '1px solid var(--vscode-panel-border)',
        borderRadius: 6,
        overflow: 'hidden',
        fontFamily: MONO_FONT,
        fontSize: 12,
      }}
    >
      <div style={{ padding: '6px 10px', fontWeight: 600, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
        {formatHeader(item)}
      </div>
      {item.result && (
        <div
          style={{
            padding: '6px 10px',
            borderTop: '1px solid var(--vscode-panel-border)',
            color: 'var(--vscode-descriptionForeground)',
            maxHeight: 200,
            overflowY: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {item.result.text.trim() ? item.result.text : '(no output)'}
        </div>
      )}
    </div>
  );
}
