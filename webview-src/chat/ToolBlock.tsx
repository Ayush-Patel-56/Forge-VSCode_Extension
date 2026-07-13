// webview-src/chat/ToolBlock.tsx
import React from 'react';
import { ToolItem } from './types';

const MONO_FONT = 'var(--vscode-editor-font-family), monospace';
const LONG_ARGS_THRESHOLD = 60;

/** The command / args string rendered for the tool invocation. */
function formatInput(item: ToolItem): string {
  if (item.name === 'terminal.run_command') {
    const command = (item.args as { command?: string } | undefined)?.command ?? '';
    return `$ ${command}`;
  }
  if (item.args == null) return '';
  try {
    const s = JSON.stringify(item.args);
    return !s || s === '{}' ? '' : s;
  } catch {
    return '';
  }
}

/** Dim corner tag ("IN" / "OUT") used inside the tool block. */
function Tag({ label }: { label: string }) {
  return (
    <span
      style={{
        fontSize: 9,
        letterSpacing: 1,
        color: 'var(--vscode-descriptionForeground)',
        border: '1px solid var(--vscode-panel-border)',
        borderRadius: 3,
        padding: '0 4px',
        flexShrink: 0,
        alignSelf: 'flex-start',
        marginTop: 2,
      }}
    >
      {label}
    </span>
  );
}

export default function ToolBlock({ item }: { item: ToolItem }) {
  const failed = item.result?.ok === false;
  const input = formatInput(item);
  const isCommand = item.name === 'terminal.run_command';
  const longInput = input.length > LONG_ARGS_THRESHOLD;

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
      {/* Header: bullet + bold tool name, with short inputs inline. */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '6px 10px' }}>
        <span style={{ color: 'var(--vscode-descriptionForeground)', fontSize: 9 }}>●</span>
        <span style={{ fontWeight: 700, flexShrink: 0 }}>{isCommand ? 'Terminal' : `⚙ ${item.name}`}</span>
        {!longInput && input && (
          <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{input}</span>
        )}
      </div>

      {/* Long inputs get their own bordered inner box with a dim IN tag. */}
      {longInput && (
        <div style={{ display: 'flex', gap: 8, margin: '0 10px 6px', padding: '4px 8px', border: '1px solid var(--vscode-panel-border)', borderRadius: 4 }}>
          <Tag label="IN" />
          <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', flex: 1 }}>{input}</span>
        </div>
      )}

      {item.result && (
        <div
          style={{
            display: 'flex',
            gap: 8,
            padding: '6px 10px',
            borderTop: '1px solid var(--vscode-panel-border)',
            color: 'var(--vscode-descriptionForeground)',
          }}
        >
          <Tag label="OUT" />
          <div
            style={{
              flex: 1,
              maxHeight: 200,
              overflowY: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {item.result.text.trim() ? item.result.text : '(no output)'}
          </div>
        </div>
      )}
    </div>
  );
}
