// src/extension.ts
import * as vscode from 'vscode';
import { BackendService } from './services/backendService';
import { ContextService } from './services/contextService';
import { StatusBarService } from './services/statusBarService';
import { ChatPanel } from './views/chatPanel';
import { MCPPanel } from './views/mcpPanel';
import { SidebarProvider } from './views/sidebarProvider';
import { InlineCompleter } from './providers/inlineCompleter';
import { registerCommands } from './commands';

let backend: BackendService;
let statusBar: StatusBarService;

export async function activate(ctx: vscode.ExtensionContext) {
  // 1. Start Python backend (async — don't block UI)
  backend = new BackendService(ctx);
  const contextService = new ContextService(backend);
  statusBar = new StatusBarService(ctx);

  statusBar.setStarting();

  // Fire-and-forget startup — UI shows immediately
  backend.start().then(() => {
    statusBar.setReady(backend.getActiveModel());
    // Index workspace after backend is ready
    const wsPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (wsPath) backend.indexWorkspace(wsPath);
  }).catch((err) => {
    statusBar.setError();
    vscode.window.showErrorMessage(`Forge backend failed to start: ${err.message}`);
  });

  // 2. Register inline completion (ghost text)
  ctx.subscriptions.push(
    vscode.languages.registerInlineCompletionItemProvider(
      { pattern: '**' },
      new InlineCompleter(backend, contextService)
    )
  );

  // 3. Register sidebar webview provider
  ctx.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      'forge.chat',
      new SidebarProvider(ctx, backend, contextService)
    )
  );

  // 4. Register all forge.* commands
  registerCommands(ctx, backend, contextService, statusBar);
}

export function deactivate() {
  backend?.stop();
}
