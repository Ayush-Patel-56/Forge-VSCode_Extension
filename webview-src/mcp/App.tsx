// webview-src/mcp/App.tsx
import React, { useState, useEffect } from 'react';

declare const acquireVsCodeApi: () => { postMessage: (msg: unknown) => void };
const vscode = acquireVsCodeApi();

interface MCP {
  id: string;
  display_name: string;
  description: string;
  category: string;
  required_keys: string[];
  status: 'running' | 'installed' | 'not_installed';
}

export default function MCPApp() {
  const [mcps, setMcps] = useState<MCP[]>([]);
  const [installing, setInstalling] = useState<string | null>(null);
  const [wizardMcp, setWizardMcp] = useState<MCP | null>(null);
  const [keyValues, setKeyValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    vscode.postMessage({ type: 'REQUEST_MCP_LIST' });
    window.addEventListener('message', (e) => {
      if (e.data.type === 'MCP_LIST') setMcps(e.data.mcps);
      if (e.data.type === 'MCP_STATUS') {
        if (e.data.status === 'ready' || e.data.status === 'error') setInstalling(null);
        setErrors(prev => ({
          ...prev,
          [e.data.mcpId]: e.data.status === 'error' ? (e.data.error ?? 'Install failed') : '',
        }));
        vscode.postMessage({ type: 'REQUEST_MCP_LIST' });
      }
    });
  }, []);

  const startInstall = (mcp: MCP) => {
    if (mcp.required_keys.length === 0) {
      doInstall(mcp, {});
    } else {
      setWizardMcp(mcp);
      setKeyValues({});
    }
  };

  const doInstall = (mcp: MCP, config: Record<string, string>) => {
    setInstalling(mcp.id);
    setWizardMcp(null);
    vscode.postMessage({ type: 'INSTALL_MCP', mcpId: mcp.id, config });
  };

  const doUninstall = (mcp: MCP) => {
    vscode.postMessage({ type: 'UNINSTALL_MCP', mcpId: mcp.id });
  };

  const statusColor = (status: string) => ({
    running: '#4caf50', installed: '#ff9800', not_installed: 'var(--vscode-descriptionForeground)'
  }[status] ?? 'gray');

  return (
    <div style={{ padding: 16, fontFamily: 'var(--vscode-font-family)' }}>
      <h2 style={{ fontSize: 14, marginBottom: 16, color: 'var(--vscode-foreground)' }}>MCP Servers</h2>

      {mcps.map(mcp => (
        <div key={mcp.id} style={{ marginBottom: 12, padding: 12, background: 'var(--vscode-editor-background)', border: '1px solid var(--vscode-panel-border)', borderRadius: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{mcp.display_name}</div>
              <div style={{ fontSize: 11, color: 'var(--vscode-descriptionForeground)' }}>{mcp.description}</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 10, color: statusColor(mcp.status) }}>● {mcp.status}</span>
              {mcp.status === 'not_installed' && (
                <button
                  onClick={() => startInstall(mcp)}
                  disabled={installing === mcp.id}
                  style={{ padding: '4px 10px', background: 'var(--vscode-button-background)', color: 'var(--vscode-button-foreground)', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}
                >
                  {installing === mcp.id ? 'Installing...' : 'Install'}
                </button>
              )}
              {(mcp.status === 'running' || mcp.status === 'installed') && (
                <button
                  onClick={() => doUninstall(mcp)}
                  style={{ padding: '4px 10px', background: 'var(--vscode-button-secondaryBackground)', color: 'var(--vscode-button-secondaryForeground)', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}
                >
                  Uninstall
                </button>
              )}
            </div>
          </div>
          {errors[mcp.id] && (
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--vscode-errorForeground)' }}>
              {errors[mcp.id]}
            </div>
          )}
        </div>
      ))}

      {/* Key wizard modal */}
      {wizardMcp && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: 'var(--vscode-editor-background)', padding: 20, borderRadius: 8, width: 320 }}>
            <h3 style={{ marginBottom: 12 }}>Configure {wizardMcp.display_name}</h3>
            {wizardMcp.required_keys.map(k => (
              <div key={k} style={{ marginBottom: 10 }}>
                <label style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>{k}</label>
                <input
                  type="password"
                  value={keyValues[k] ?? ''}
                  onChange={e => setKeyValues(prev => ({ ...prev, [k]: e.target.value }))}
                  style={{ width: '100%', padding: '4px 8px', boxSizing: 'border-box', background: 'var(--vscode-input-background)', color: 'var(--vscode-input-foreground)', border: '1px solid var(--vscode-input-border)', borderRadius: 4 }}
                />
              </div>
            ))}
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button onClick={() => doInstall(wizardMcp, keyValues)} style={{ flex: 1, padding: '6px', background: 'var(--vscode-button-background)', color: 'var(--vscode-button-foreground)', border: 'none', borderRadius: 4, cursor: 'pointer' }}>Install</button>
              <button onClick={() => setWizardMcp(null)} style={{ flex: 1, padding: '6px', background: 'var(--vscode-button-secondaryBackground)', color: 'var(--vscode-button-secondaryForeground)', border: 'none', borderRadius: 4, cursor: 'pointer' }}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
