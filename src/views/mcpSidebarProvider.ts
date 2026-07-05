// src/views/mcpSidebarProvider.ts
//
// NOT specified in forge_spec.md (no code block provided for this file).
// Registers the ActivityBar view 'forge.mcpList' (contributed in package.json
// but previously unimplemented). Modeled on SidebarProvider's pattern (spec
// Section 10.1): serves out/webview/mcp.js and bridges the same MCP-related
// IPC messages that MCPPanel handles (REQUEST_MCP_LIST / INSTALL_MCP /
// UNINSTALL_MCP), since WebviewView and WebviewPanel are distinct VSCode API
// surfaces that cannot share a webview instance.
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { WebviewToExtension, ExtensionToWebview } from '../types';
import * as path from 'path';

export class MCPSidebarProvider implements vscode.WebviewViewProvider {
  private view: vscode.WebviewView | undefined;

  constructor(
    private ctx: vscode.ExtensionContext,
    private backend: BackendService
  ) {}

  resolveWebviewView(webviewView: vscode.WebviewView) {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.file(path.join(this.ctx.extensionPath, 'out'))],
    };
    webviewView.webview.html = this.getHtml(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (msg: WebviewToExtension) => {
      await this.handleMessage(msg);
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
    this.view?.webview.postMessage(msg);
  }

  private getHtml(webview: vscode.Webview): string {
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.file(path.join(this.ctx.extensionPath, 'out', 'webview', 'mcp.js'))
    );
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${webview.cspSource}; style-src ${webview.cspSource} 'unsafe-inline';">
  <title>Forge MCPs</title>
</head>
<body>
  <div id="root"></div>
  <script src="${scriptUri}"></script>
</body>
</html>`;
  }
}
