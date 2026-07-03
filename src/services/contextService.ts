// src/services/contextService.ts
import * as vscode from 'vscode';
import { BackendService } from './backendService';

export interface ContextSnapshot {
  activeFile: string | null;
  language: string | null;
  selection: string | null;
  ragChunks: { content: string; file: string; line: number }[];
  tokenEstimate: number;
}

export class ContextService {
  constructor(private backend: BackendService) {}

  async gatherContext(userQuery: string): Promise<ContextSnapshot> {
    const editor = vscode.window.activeTextEditor;
    let activeFile: string | null = null;
    let language: string | null = null;
    let selection: string | null = null;

    if (editor) {
      activeFile = editor.document.getText();
      language = editor.document.languageId;
      const sel = editor.document.getText(editor.selection);
      if (sel.trim()) selection = sel;
    }

    // RAG: get relevant chunks from indexed codebase
    let ragChunks: { content: string; file: string; line: number }[] = [];
    try {
      ragChunks = await this.backend.queryContext(userQuery, 8);
    } catch {
      // RAG unavailable (indexing not complete yet) — proceed without
    }

    // Estimate tokens (rough: 1 token ~ 4 chars)
    const totalChars = (activeFile?.length ?? 0) + (selection?.length ?? 0) +
      ragChunks.reduce((s, c) => s + c.content.length, 0);

    return {
      activeFile: activeFile ? activeFile.slice(0, 6000) : null, // cap at ~1500 tokens
      language,
      selection,
      ragChunks,
      tokenEstimate: Math.ceil(totalChars / 4),
    };
  }

  getActiveFilePath(): string | null {
    return vscode.window.activeTextEditor?.document.fileName ?? null;
  }
}
