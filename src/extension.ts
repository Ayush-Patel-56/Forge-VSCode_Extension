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
    if (wsPath) {
      backend.indexWorkspace(wsPath);
      pollIndexStatus();
    }
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

const INDEX_POLL_INTERVAL_MS = 1000;
const INDEX_POLL_HARD_CAP_MS = 10 * 60 * 1000;
const INDEX_POLL_MAX_CONSECUTIVE_FAILURES = 5;

function pollIndexStatus(): void {
  const startedAt = Date.now();
  let consecutiveFailures = 0;

  const interval = setInterval(() => {
    void (async () => {
      const elapsed = Date.now() - startedAt;
      if (elapsed >= INDEX_POLL_HARD_CAP_MS) {
        clearInterval(interval);
        statusBar.setReady(backend.getActiveModel());
        return;
      }

      const result = await backend.getIndexStatus();

      if (result.status === 'unknown') {
        consecutiveFailures++;
        if (consecutiveFailures >= INDEX_POLL_MAX_CONSECUTIVE_FAILURES) {
          clearInterval(interval);
          statusBar.setReady(backend.getActiveModel());
        }
        return;
      }
      consecutiveFailures = 0;

      if (result.status === 'indexing') {
        statusBar.setIndexing(result.files_indexed, result.total_files);
      } else if (result.status === 'ready') {
        clearInterval(interval);
        statusBar.setReady(backend.getActiveModel());
      }
    })();
  }, INDEX_POLL_INTERVAL_MS);
}

export function deactivate() {
  backend?.stop();
}
