// src/providers/inlineCompleter.ts
import * as vscode from 'vscode';
import { BackendService } from '../services/backendService';
import { ContextService } from '../services/contextService';

export class InlineCompleter implements vscode.InlineCompletionItemProvider {
  private debounceTimer: NodeJS.Timeout | undefined;

  constructor(
    private backend: BackendService,
    private context: ContextService
  ) {}

  async provideInlineCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    _context: vscode.InlineCompletionContext
  ): Promise<vscode.InlineCompletionList> {
    if (!vscode.workspace.getConfiguration('forge').get<boolean>('completions.enabled', true)) {
      return { items: [] };
    }

    if (this.debounceTimer) clearTimeout(this.debounceTimer);

    return new Promise((resolve) => {
      this.debounceTimer = setTimeout(async () => {
        try {
          // Get ~2000 chars of prefix (before cursor)
          const prefixStart = new vscode.Position(Math.max(0, position.line - 60), 0);
          const prefix = document.getText(new vscode.Range(prefixStart, position));

          // Get ~500 chars of suffix (after cursor)
          const suffixEnd = new vscode.Position(position.line + 15, 0);
          const suffix = document.getText(new vscode.Range(position, suffixEnd));

          const completion = await this.backend.complete({
            prefix,
            suffix,
            language: document.languageId,
            filepath: document.fileName,
          });

          if (!completion || completion.trim() === '') {
            return resolve({ items: [] });
          }

          resolve({
            items: [
              new vscode.InlineCompletionItem(
                completion,
                new vscode.Range(position, position)
              )
            ]
          });
        } catch {
          resolve({ items: [] });
        }
      }, 300);
    });
  }
}
