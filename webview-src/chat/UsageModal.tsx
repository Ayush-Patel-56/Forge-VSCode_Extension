// webview-src/chat/UsageModal.tsx
import React, { useEffect } from 'react';
import { UsageDetails } from './types';

const MONO_FONT = 'var(--vscode-editor-font-family), monospace';

export default function UsageModal({
  usage,
  onRequestUsage,
  onClose,
}: {
  usage: UsageDetails | null;
  onRequestUsage: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    onRequestUsage();
    // Refresh once on open only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
        fontFamily: MONO_FONT,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 340,
          maxWidth: '90vw',
          maxHeight: '80vh',
          overflowY: 'auto',
          background: 'var(--vscode-editorWidget-background)',
          border: '1px solid var(--vscode-widget-border, var(--vscode-panel-border))',
          borderRadius: 8,
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.4)',
          padding: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Account &amp; usage</span>
          <span onClick={onClose} style={{ cursor: 'pointer', color: 'var(--vscode-descriptionForeground)', fontSize: 14 }}>
            ×
          </span>
        </div>

        {!usage ? (
          <div style={{ fontSize: 12, color: 'var(--vscode-descriptionForeground)' }}>Loading…</div>
        ) : (
          <>
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 11, color: 'var(--vscode-descriptionForeground)', marginBottom: 2 }}>Today</div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{usage.todayTokens.toLocaleString()} tokens</div>
              <div style={{ fontSize: 13, color: 'var(--vscode-descriptionForeground)' }}>${usage.todayUsd.toFixed(4)}</div>
            </div>

            <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 6 }}>By model</div>
            {usage.byModel.length === 0 ? (
              <div style={{ fontSize: 11, color: 'var(--vscode-descriptionForeground)' }}>No usage recorded today.</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                <thead>
                  <tr style={{ color: 'var(--vscode-descriptionForeground)', textAlign: 'left' }}>
                    <th style={{ fontWeight: 500, padding: '2px 4px 6px 0' }}>Model</th>
                    <th style={{ fontWeight: 500, padding: '2px 4px 6px 0', textAlign: 'right' }}>In</th>
                    <th style={{ fontWeight: 500, padding: '2px 4px 6px 0', textAlign: 'right' }}>Out</th>
                    <th style={{ fontWeight: 500, padding: '2px 0 6px 4px', textAlign: 'right' }}>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.byModel.map(m => (
                    <tr key={m.model_id} style={{ borderTop: '1px solid var(--vscode-panel-border)' }}>
                      <td style={{ padding: '4px 4px 4px 0', wordBreak: 'break-all' }}>{m.model_id}</td>
                      <td style={{ padding: '4px 4px 4px 0', textAlign: 'right' }}>{m.tokens_in.toLocaleString()}</td>
                      <td style={{ padding: '4px 4px 4px 0', textAlign: 'right' }}>{m.tokens_out.toLocaleString()}</td>
                      <td style={{ padding: '4px 0 4px 4px', textAlign: 'right' }}>${m.cost_usd.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  );
}
