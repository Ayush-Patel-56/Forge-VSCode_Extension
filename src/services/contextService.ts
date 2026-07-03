// src/services/contextService.ts
import * as vscode from 'vscode';
import { BackendService } from './backendService';

export interface ContextSnapshot {
  activeFile: string | null;
  filePath: string | null;
  language: string | null;
  selection: string | null;
  ragChunks: { content: string; file: string; line: number }[];
  tokenEstimate: number;
}

export class ContextService {
  // Focusing a webview clears activeTextEditor, so remember the last real editor
  private lastEditor: vscode.TextEditor | undefined = vscode.window.activeTextEditor;

  constructor(private backend: BackendService) {
    vscode.window.onDidChangeActiveTextEditor((e) => {
      if (e) this.lastEditor = e;
    });
  }

  private getEditor(): vscode.TextEditor | undefined {
    const editor = vscode.window.activeTextEditor ?? this.lastEditor;
    return editor && !editor.document.isClosed ? editor : undefined;
  }

  async gatherContext(userQuery: string): Promise<ContextSnapshot> {
    const editor = this.getEditor();
    let activeFile: string | null = null;
    let filePath: string | null = null;
    let language: string | null = null;
    let selection: string | null = null;

    if (editor) {
      activeFile = editor.document.getText();
      filePath = editor.document.fileName;
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
      filePath,
      language,
      selection,
      ragChunks,
      tokenEstimate: Math.ceil(totalChars / 4),
    };
  }

  getActiveFilePath(): string | null {
    return this.getEditor()?.document.fileName ?? null;
  }
}
