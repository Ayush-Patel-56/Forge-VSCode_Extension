// webview-src/chat/types.ts
//
// Conversation is modeled as a flat, arrival-ordered list of discriminated
// "items" rather than one blob of content per turn, so tool calls, tool
// results, and approval requests can interleave with streamed assistant text
// exactly in the order the engine emits them.

export interface TextItem {
  kind: 'text';
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}

export interface ToolItem {
  kind: 'tool';
  id: string;
  name: string;
  args: unknown;
  result?: { ok: boolean; text: string };
}

export interface ApprovalItem {
  kind: 'approval';
  id: string;
  command: string;
  cwd: string;
  decision?: 'allow' | 'deny' | 'other';
  detail?: string;
}

export type ConversationItem = TextItem | ToolItem | ApprovalItem;

export interface ModelInfo {
  id: string;
  display_name: string;
  is_free: boolean;
}

export type Effort = 'low' | 'medium' | 'high' | 'max';

export interface LiveStatus {
  label: string;
  startedAt: number;
}
