// src/commands/index.ts
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { ContextService } from '../services/contextService';
import { StatusBarService } from '../services/statusBarService';
import { ChatPanel } from '../views/chatPanel';
import { MCPPanel } from '../views/mcpPanel';

/**
 * Derives a provider id from a base URL's hostname: take the label just
 * before the TLD (the "second-level domain" of the registrable domain),
 * which pragmatically strips off common subdomain prefixes like www/api/
 * integrate/generativelanguage without needing an explicit denylist --
 * 'integrate.api.nvidia.com' -> 'nvidia', 'api.cerebras.ai' -> 'cerebras'.
 * Falls back to the first label for bare/single-label hosts. Sanitized to
 * [a-z0-9_] since it's used as both a URL-safe id and a secret-key segment.
 */
function deriveProviderId(rawUrl: string): string {
  let hostname: string;
  try {
    hostname = new URL(rawUrl).hostname;
  } catch {
    hostname = rawUrl.replace(/^[a-z]+:\/\//i, '').split(/[/?#]/)[0];
  }
  const labels = hostname.split('.').filter(Boolean);
  const label = labels.length >= 2 ? labels[labels.length - 2] : (labels[0] || 'custom');
  const sanitized = label.toLowerCase().replace(/[^a-z0-9_]/g, '_');
  return sanitized || 'custom';
}

/** Parses a pasted provider snippet (or bare URL) for base_url + model, without
 * relying on line anchors -- input boxes collapse multi-line pastes to one line. */
function parseProviderSnippet(text: string): { baseUrl: string | null; modelId: string | null } {
  const baseUrlMatch = text.match(/base_url\s*[=:]\s*["']([^"']+)["']/i);
  const bareUrlMatch = text.match(/https?:\/\/[^\s"'<>]+/i);
  const modelMatch = text.match(/model\s*[=:]\s*["']([^"']+)["']/i);
  return {
    baseUrl: baseUrlMatch?.[1] || bareUrlMatch?.[0] || null,
    modelId: modelMatch?.[1] || null,
  };
}

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
      if (!wsPath) {
        vscode.window.showWarningMessage('Forge: open a folder/workspace first to explain a repo.');
        return;
      }
      ChatPanel.createOrShow(ctx, backend, contextService, statusBar);
      try {
        const summary = await backend.sendExplainRepo(wsPath);
        await ChatPanel.currentPanel?.sendProgrammaticMessage(
          `Explain this repository: describe its purpose, architecture, and key modules, and suggest a README outline. Key files:\n\n${summary}`
        );
      } catch (err: any) {
        vscode.window.showErrorMessage(`Forge: failed to explain repo — ${err.message}`);
      }
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

      // If this provider has zero models in the catalog, nudge the user
      // toward "Forge: Add custom model" rather than leaving a configured
      // provider that never shows up in the model picker.
      try {
        const models = await backend.getAvailableModels();
        const hasModels = models.some(m => m.id.startsWith(`${provider}/`));
        if (!hasModels) {
          const choice = await vscode.window.showInformationMessage(
            `Forge: ${provider} has no models in the catalog yet. Add one?`,
            'Add custom model'
          );
          if (choice === 'Add custom model') {
            await vscode.commands.executeCommand('forge.add.custom.model');
          }
        }
      } catch {
        // Non-fatal: backend may not be reachable yet
      }
    }],
    ['forge.add.custom.model', async () => {
      const snippet = await vscode.window.showInputBox({
        prompt: "Paste the provider's sample code, or just the base URL",
        placeHolder: 'Paste the provider\'s sample code, or just the base URL',
        ignoreFocusOut: true,
      });
      if (!snippet) return;

      const { baseUrl, modelId: parsedModelId } = parseProviderSnippet(snippet);

      if (!baseUrl) {
        vscode.window.showErrorMessage('Forge: could not find a base URL in the pasted text.');
        return;
      }

      let modelId = parsedModelId;
      if (!modelId) {
        modelId = await vscode.window.showInputBox({
          prompt: 'Enter the model id (e.g. z-ai/glm-5.2)',
          placeHolder: 'z-ai/glm-5.2',
          ignoreFocusOut: true,
        }) ?? null;
        if (!modelId) return;
      }

      const provider = deriveProviderId(baseUrl);

      const existingKey = await ctx.secrets.get(`forge.${provider}.apiKey`);
      const keyInput = await vscode.window.showInputBox({
        prompt: existingKey
          ? `Enter ${provider} API key (leave empty to reuse the stored key)`
          : `Enter ${provider} API key`,
        password: true,
        ignoreFocusOut: true,
      });
      if (keyInput === undefined) return; // user cancelled

      const apiKey = keyInput || existingKey;
      if (!apiKey) {
        vscode.window.showErrorMessage(`Forge: an API key is required for ${provider} (none stored yet).`);
        return;
      }

      await ctx.secrets.store(`forge.${provider}.apiKey`, apiKey);
      await backend.registerProvider(provider, apiKey, baseUrl);

      const lastSegment = modelId.split('/').filter(Boolean).pop() || modelId;
      const displayName = `${lastSegment} (${provider})`;
      const added = await backend.addModel({
        provider_id: provider,
        model_id: modelId,
        display_name: displayName,
      });

      const fullId = added.id ?? `${provider}/${modelId}`;
      const setActive = await vscode.window.showQuickPick(['Yes', 'No'], {
        placeHolder: `Set ${fullId} as the active model?`,
      });
      if (setActive === 'Yes') {
        await backend.setModel(fullId);
        statusBar.setReady(fullId);
      }

      vscode.window.showInformationMessage(`Forge: added ${fullId} ✓`);
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
