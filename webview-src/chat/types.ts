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
  /** Names of images the user attached to this message (chips in transcript). */
  imageNames?: string[];
  /** Workspace-relative paths of files the user attached to this message. */
  attachedFiles?: string[];
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

/**
 * A dim, single-line milestone marker retained in transcript history for a
 * status transition (e.g. "Thinking" / "Responding"). Distinct from the live
 * StatusLine, which is transient and disappears once the turn settles.
 */
export interface MilestoneItem {
  kind: 'milestone';
  id: string;
  label: string;
}

export type ConversationItem = TextItem | ToolItem | ApprovalItem | MilestoneItem;

export interface ModelInfo {
  id: string;
  display_name: string;
  is_free: boolean;
}

export type Effort = 'low' | 'medium' | 'high' | 'max';

export type Mode = 'manual' | 'auto' | 'edit' | 'plan';

export interface LiveStatus {
  label: string;
  startedAt: number;
}

export interface ImageAttachment {
  name: string;
  mime: string;
  /** Raw base64 payload (data: URL prefix stripped). */
  dataBase64: string;
  width?: number;
  height?: number;
}

export interface UsageByModel {
  model_id: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

export interface UsageDetails {
  todayTokens: number;
  todayUsd: number;
  byModel: UsageByModel[];
}
