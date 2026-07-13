// src/utils/attachments.ts
//
// Shared helpers for the chat webview's "Attach file…" / "Mention file…"
// features, used identically by ChatPanel and SidebarProvider.
import * as vscode from 'vscode';

const MAX_RESULTS = 100;
const MAX_ATTACHED_FILE_CHARS = 8000;

/** Find workspace files matching a substring query, as workspace-relative paths. */
export async function findWorkspaceFiles(query: string): Promise<string[]> {
  const pattern = query.trim() ? `**/*${query.trim()}*` : '**/*';
  try {
    const uris = await vscode.workspace.findFiles(pattern, '**/node_modules/**', MAX_RESULTS);
    return uris.map(u => vscode.workspace.asRelativePath(u, false));
  } catch {
    return [];
  }
}

/**
 * Read each attached workspace-relative file (capped at 8000 chars, skipping
 * unreadable ones) and render "Attached file <path>:" fenced sections to be
 * appended to the system prompt for the current turn.
 */
export async function readAttachedFileSections(relPaths: string[]): Promise<string[]> {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri;
  if (!root) return [];

  const sections: string[] = [];
  for (const relPath of relPaths) {
    try {
      const uri = vscode.Uri.joinPath(root, relPath);
      const bytes = await vscode.workspace.fs.readFile(uri);
      let text = new TextDecoder('utf-8').decode(bytes);
      if (text.length > MAX_ATTACHED_FILE_CHARS) {
        text = `${text.slice(0, MAX_ATTACHED_FILE_CHARS)}\n… (truncated)`;
      }
      sections.push(`\nAttached file ${relPath}:\n\`\`\`\n${text}\n\`\`\``);
    } catch {
      // Unreadable (binary, deleted, permissions) — skip silently.
    }
  }
  return sections;
}
