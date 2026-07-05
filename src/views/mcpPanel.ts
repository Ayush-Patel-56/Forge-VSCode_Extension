// src/views/mcpPanel.ts
//
// NOT specified in forge_spec.md (no code block provided for this file).
// Minimal implementation modeled on ChatPanel's pattern (spec Section 10.1):
// same CSP/html scaffold, loads out/webview/mcp.js, and bridges the two
// MCP-related IPC messages defined in src/types.ts (REQUEST_MCP_LIST / INSTALL_MCP).
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { WebviewToExtension, ExtensionToWebview } from '../types';
import * as path from 'path';

export class MCPPanel {
  static currentPanel: MCPPanel | undefined;
  private readonly panel: vscode.WebviewPanel;

  static createOrShow(ctx: vscode.ExtensionContext, backend: BackendService) {
    const column = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;
    if (MCPPanel.currentPanel) {
      MCPPanel.currentPanel.panel.reveal(column);
      return;
    }
    const panel = vscode.window.createWebviewPanel('forge.mcp', 'Forge MCPs', column, {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.file(path.join(ctx.extensionPath, 'out'))],
      retainContextWhenHidden: true,
    });
    MCPPanel.currentPanel = new MCPPanel(panel, ctx, backend);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    private ctx: vscode.ExtensionContext,
    private backend: BackendService
  ) {
    this.panel = panel;
    this.panel.webview.html = this.getHtml();

    this.panel.webview.onDidReceiveMessage(async (msg: WebviewToExtension) => {
      await this.handleMessage(msg);
    });

    this.panel.onDidDispose(() => {
      MCPPanel.currentPanel = undefined;
    });
  }

  private async handleMessage(msg: WebviewToExtension) {
    switch (msg.type) {
      case 'REQUEST_MCP_LIST': {
        try {
          const mcps = await this.backend.getMCPList();
          this.post<ExtensionToWebview>({ type: 'MCP_LIST', mcps });
        } catch {
          this.post<ExtensionToWebview>({ type: 'MCP_LIST', mcps: [] });
          vscode.window.showErrorMessage(
            'Forge: backend is not responding — MCP list unavailable. Restart the window or check the Debug Console for [forge-backend] errors.'
          );
        }
        break;
      }

      case 'INSTALL_MCP': {
        this.post<ExtensionToWebview>({ type: 'MCP_STATUS', mcpId: msg.mcpId, status: 'installing' });
        try {
          const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
          const config = {
            ...(workspacePath ? { WORKSPACE_PATH: workspacePath } : {}),
            ...msg.config,
          };
          const result = await this.backend.installMCP(msg.mcpId, config);
          this.post<ExtensionToWebview>({
            type: 'MCP_STATUS',
            mcpId: msg.mcpId,
            status: result.status === 'ready' ? 'ready' : 'error',
            error: result.error,
          });
        } catch (err: any) {
          this.post<ExtensionToWebview>({
            type: 'MCP_STATUS',
            mcpId: msg.mcpId,
            status: 'error',
            error: err.message,
          });
        }
        break;
      }

      case 'UNINSTALL_MCP': {
        try {
          await this.backend.uninstallMCP(msg.mcpId);
        } catch (err: any) {
          this.post<ExtensionToWebview>({
            type: 'MCP_STATUS',
            mcpId: msg.mcpId,
            status: 'error',
            error: err.message,
          });
        }
        const mcps = await this.backend.getMCPList();
        this.post<ExtensionToWebview>({ type: 'MCP_LIST', mcps });
        break;
      }

      case 'START_MCP': {
        try {
          const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
          const result = await this.backend.startMCP(msg.mcpId, workspacePath);
          this.post<ExtensionToWebview>({
            type: 'MCP_STATUS',
            mcpId: msg.mcpId,
            status: result.status === 'ready' ? 'ready' : 'error',
            error: result.error,
          });
        } catch (err: any) {
          this.post<ExtensionToWebview>({
            type: 'MCP_STATUS',
            mcpId: msg.mcpId,
            status: 'error',
            error: err.message,
          });
        }
        break;
      }
    }
  }

  private post<T>(msg: T) {
    this.panel.webview.postMessage(msg);
  }

  private getHtml(): string {
    const scriptUri = this.panel.webview.asWebviewUri(
      vscode.Uri.file(path.join(this.ctx.extensionPath, 'out', 'webview', 'mcp.js'))
    );
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${this.panel.webview.cspSource}; style-src ${this.panel.webview.cspSource} 'unsafe-inline';">
  <title>Forge MCPs</title>
</head>
<body>
  <div id="root"></div>
  <script src="${scriptUri}"></script>
</body>
</html>`;
  }
}
