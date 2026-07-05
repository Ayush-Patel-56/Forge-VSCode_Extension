// src/commands/index.ts
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { ContextService } from '../services/contextService';
import { StatusBarService } from '../services/statusBarService';
import { ChatPanel } from '../views/chatPanel';
import { MCPPanel } from '../views/mcpPanel';

export function registerCommands(
  ctx: vscode.ExtensionContext,
  backend: BackendService,
  contextService: ContextService,
  statusBar: StatusBarService
) {
  const cmds: [string, (...args: unknown[]) => unknown][] = [
    ['forge.chat.open', () => ChatPanel.createOrShow(ctx, backend, contextService, statusBar)],
    ['forge.mcp.open', () => MCPPanel.createOrShow(ctx, backend)],
    ['forge.index.workspace', async () => {
      const wsPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!wsPath) return;
      vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Forge: indexing workspace...' },
        async () => { await backend.indexWorkspace(wsPath); }
      );
    }],
    ['forge.explain.repo', async () => {
      const wsPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!wsPath) return;
      ChatPanel.createOrShow(ctx, backend, contextService, statusBar);
      // Send special command to the panel
      await backend.sendExplainRepo(wsPath);
    }],
    ['forge.add.provider', async () => {
      const provider = await vscode.window.showQuickPick(
        ['groq', 'gemini', 'openrouter', 'nvidia', 'cerebras', 'anthropic', 'ollama'],
        { placeHolder: 'Select provider' }
      );
      if (!provider) return;
      const key = await vscode.window.showInputBox({
        prompt: `Enter ${provider} API key`,
        password: true,
        ignoreFocusOut: true
      });
      if (!key) return;
      await ctx.secrets.store(`forge.${provider}.apiKey`, key);
      await backend.registerProvider(provider, key);
      vscode.window.showInformationMessage(`Forge: ${provider} configured ✓`);
    }],
    ['forge.set.model', async () => {
      const models = await backend.getAvailableModels();
      const picked = await vscode.window.showQuickPick(
        models.map(m => ({ label: m.display_name, description: m.is_free ? '● free' : `$${m.cost_per_1k_output}/1k`, detail: m.id })),
        { placeHolder: 'Select model' }
      );
      if (!picked) return;
      await backend.setModel(picked.detail);
      statusBar.setReady(picked.detail);
    }],
  ];

  for (const [cmd, handler] of cmds) {
    ctx.subscriptions.push(vscode.commands.registerCommand(cmd, handler));
  }
}
