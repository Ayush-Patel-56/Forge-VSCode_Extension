// src/views/sidebarProvider.ts
//
// NOT specified in forge_spec.md (no code block provided for this file).
// Minimal implementation modeled on ChatPanel's pattern (spec Section 10.1):
// serves the same chat webview bundle (out/webview/chat.js) inside the
// ActivityBar view registered as 'forge.chat' in extension.ts, and duplicates
// ChatPanel's message-handling logic since WebviewView and WebviewPanel are
// distinct VSCode API surfaces that cannot share a webview instance.
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { ContextService, ContextSnapshot } from '../services/contextService';
import { WebviewToExtension, ExtensionToWebview } from '../types';
import * as path from 'path';

export class SidebarProvider implements vscode.WebviewViewProvider {
  private view: vscode.WebviewView | undefined;
  private conversationHistory: { role: string; content: string }[] = [];

  constructor(
    private ctx: vscode.ExtensionContext,
    private backend: BackendService,
    private contextService: ContextService
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
      case 'SEND_MESSAGE': {
        const snapshot = await this.contextService.gatherContext(msg.content);

        this.conversationHistory.push({ role: 'user', content: msg.content });

        const systemContent = this.buildSystemPrompt(snapshot);
        const messages = [
          { role: 'system', content: systemContent },
          ...this.conversationHistory.slice(-20),
        ];

        let assistantContent = '';

        try {
          for await (const chunk of this.backend.streamChat({
            messages,
            model_id: msg.modelId,
            conversation_id: msg.conversationId,
          })) {
            assistantContent += chunk;
            this.post<ExtensionToWebview>({
              type: 'STREAM_CHUNK',
              chunk,
              conversationId: msg.conversationId,
            });
          }
        } catch (err: any) {
          this.post<ExtensionToWebview>({
            type: 'STREAM_ERROR',
            error: err.message,
            conversationId: msg.conversationId,
          });
          return;
        }

        this.conversationHistory.push({ role: 'assistant', content: assistantContent });

        this.post<ExtensionToWebview>({
          type: 'STREAM_DONE',
          conversationId: msg.conversationId,
        });

        const usage = await this.backend.getUsage();
        this.post<ExtensionToWebview>({
          type: 'USAGE_UPDATE',
          tokensUsed: usage.today_tokens,
          costUsd: usage.today_usd,
        });
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
    this.view?.webview.postMessage(msg);
  }

  private getHtml(webview: vscode.Webview): string {
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.file(path.join(this.ctx.extensionPath, 'out', 'webview', 'chat.js'))
    );
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${webview.cspSource}; style-src ${webview.cspSource} 'unsafe-inline';">
  <title>Forge Chat</title>
</head>
<body>
  <div id="root"></div>
  <script src="${scriptUri}"></script>
</body>
</html>`;
  }
}
