// src/services/statusBarService.ts
import * as vscode from 'vscode';

export class StatusBarService {
  private item: vscode.StatusBarItem;

  constructor(ctx: vscode.ExtensionContext) {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.item.command = 'forge.chat.open';
    this.item.show();
    ctx.subscriptions.push(this.item);
  }

  setStarting() {
    this.item.text = '$(loading~spin) Forge starting...';
    this.item.tooltip = 'Forge is initializing...';
  }

  setReady(modelId: string) {
    const shortModel = modelId.split('/').pop() ?? modelId;
    this.item.text = `$(sparkle) Forge | ${shortModel}`;
    this.item.tooltip = `Active model: ${modelId}\nClick to open chat`;
  }

  setError() {
    this.item.text = '$(error) Forge error';
    this.item.tooltip = 'Forge failed to start. Check output panel.';
  }

  updateUsage(tokens: number, costUsd: number) {
    const costStr = costUsd > 0 ? ` | $${costUsd.toFixed(4)}` : '';
    const modelPart = this.item.text.split('|')[1]?.trim() ?? '';
    this.item.text = `$(sparkle) Forge | ${modelPart}${costStr} | ${tokens.toLocaleString()}t`;
  }
}
