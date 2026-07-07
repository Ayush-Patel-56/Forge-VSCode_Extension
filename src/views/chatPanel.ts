// src/views/chatPanel.ts
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { ContextService, ContextSnapshot } from '../services/contextService';
import { StatusBarService } from '../services/statusBarService';
import { WebviewToExtension, ExtensionToWebview } from '../types';
import * as path from 'path';

export class ChatPanel {
  static currentPanel: ChatPanel | undefined;
  private readonly panel: vscode.WebviewPanel;
  private conversationHistory: { role: string; content: string }[] = [];

  static createOrShow(
    ctx: vscode.ExtensionContext,
    backend: BackendService,
    context: ContextService,
    statusBar?: StatusBarService
  ) {
    const column = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;
    if (ChatPanel.currentPanel) {
      ChatPanel.currentPanel.panel.reveal(column);
      return;
    }
    const panel = vscode.window.createWebviewPanel('forge.chat', 'Forge Chat', column, {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.file(path.join(ctx.extensionPath, 'out'))],
      retainContextWhenHidden: true, // keep React state alive when hidden
    });
    ChatPanel.currentPanel = new ChatPanel(panel, ctx, backend, context, statusBar);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    private ctx: vscode.ExtensionContext,
    private backend: BackendService,
    private contextService: ContextService,
    private statusBar?: StatusBarService
  ) {
    this.panel = panel;
    this.panel.webview.html = this.getHtml();

    this.panel.webview.onDidReceiveMessage(async (msg: WebviewToExtension) => {
      await this.handleMessage(msg);
    });

    this.panel.onDidDispose(() => {
      ChatPanel.currentPanel = undefined;
    });
  }

  private async handleMessage(msg: WebviewToExtension) {
    switch (msg.type) {
      case 'SEND_MESSAGE': {
        await this.runChatTurn(msg.content, msg.conversationId, msg.modelId, msg.thinking, msg.effort);
        break;
      }

      case 'APPROVAL_RESPONSE': {
        await this.backend.sendApproval(msg.approvalId, msg.decision, msg.detail);
        break;
      }

      case 'REQUEST_CONTEXT': {
        const snapshot = await this.contextService.gatherContext('');
        this.post<ExtensionToWebview>({
          type: 'CONTEXT_UPDATE',
          files: snapshot.activeFile ? [this.contextService.getActiveFilePath() ?? ''] : [],
          tokenCount: snapshot.tokenEstimate,
          ragChunkCount: snapshot.ragChunks.length,
        });
        break;
      }

      case 'CLEAR_CONVERSATION': {
        this.conversationHistory = [];
        break;
      }
    }
  }

  /**
   * Send a message into the chat programmatically (e.g. from a command like
   * "Explain this repo"), reusing the exact SEND_MESSAGE handling path so the
   * user message renders in the webview and the assistant reply streams in.
   */
  async sendProgrammaticMessage(content: string): Promise<void> {
    const conversationId = `programmatic-${Date.now()}`;
    this.post<ExtensionToWebview>({
      type: 'USER_MESSAGE',
      content,
      conversationId,
    });
    await this.runChatTurn(content, conversationId);
  }

  private async runChatTurn(
    content: string,
    conversationId: string,
    modelId?: string,
    thinking?: boolean,
    effort?: string
  ): Promise<void> {
    // Gather context
    const snapshot = await this.contextService.gatherContext(content);

    // Add to conversation history
    this.conversationHistory.push({ role: 'user', content });

    // Build messages with context injection
    const systemContent = this.buildSystemPrompt(snapshot);
    const messages = [
      { role: 'system', content: systemContent },
      ...this.conversationHistory.slice(-20), // keep last 20 turns
    ];

    const workspacePath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

    let assistantContent = '';

    // Stream response
    try {
      for await (const chunk of this.backend.streamChat({
        messages,
        model_id: modelId,
        conversation_id: conversationId,
        workspace_path: workspacePath,
        thinking,
        effort,
      })) {
        if (typeof chunk === 'string') {
          assistantContent += chunk;
          this.post<ExtensionToWebview>({
            type: 'STREAM_CHUNK',
            chunk,
            conversationId,
          });
        } else {
          this.post<ExtensionToWebview>({
            type: 'STREAM_EVENT',
            ev: chunk,
            conversationId,
          });
        }
      }
    } catch (err: any) {
      this.post<ExtensionToWebview>({
        type: 'STREAM_ERROR',
        error: err.message,
        conversationId,
      });
      return;
    }

    this.conversationHistory.push({ role: 'assistant', content: assistantContent });

    this.post<ExtensionToWebview>({
      type: 'STREAM_DONE',
      conversationId,
    });

    // Update usage in status bar
    const usage = await this.backend.getUsage();
    this.statusBar?.updateUsage(usage.today_tokens, usage.today_usd);
    this.post<ExtensionToWebview>({
      type: 'USAGE_UPDATE',
      tokensUsed: usage.today_tokens,
      costUsd: usage.today_usd,
    });
  }

  private buildSystemPrompt(snapshot: ContextSnapshot): string {
    const parts = ['You are Forge, an expert AI coding assistant.'];

    if (snapshot.activeFile) {
      parts.push(`\nActive file: ${snapshot.filePath ?? 'untitled'} (${snapshot.language})\n\`\`\`${snapshot.language}\n${snapshot.activeFile}\n\`\`\``);
    }

    if (snapshot.selection) {
      parts.push(`\nSelected code:\n\`\`\`\n${snapshot.selection}\n\`\`\``);
    }

    if (snapshot.ragChunks.length > 0) {
      parts.push('\nRelevant codebase context:');
      for (const chunk of snapshot.ragChunks) {
        parts.push(`\n// ${chunk.file}:${chunk.line}\n\`\`\`\n${chunk.content}\n\`\`\``);
      }
    }

    return parts.join('\n');
  }

  private post<T>(msg: T) {
    this.panel.webview.postMessage(msg);
  }

  private getHtml(): string {
    const scriptUri = this.panel.webview.asWebviewUri(
      vscode.Uri.file(path.join(this.ctx.extensionPath, 'out', 'webview', 'chat.js'))
    );
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${this.panel.webview.cspSource}; style-src ${this.panel.webview.cspSource} 'unsafe-inline';">
  <title>Forge Chat</title>
</head>
<body>
  <div id="root"></div>
  <script src="${scriptUri}"></script>
</body>
</html>`;
  }
}
