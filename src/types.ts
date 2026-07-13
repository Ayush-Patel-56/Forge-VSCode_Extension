// src/types.ts

// --- Typed SSE stream events (backend/router/model_router.py) --------------

export type ForgeStreamEvent =
  | { event: 'status'; label: 'thinking' | 'responding' }
  | { event: 'tool_call'; id: string; name: string; args: unknown }
  | { event: 'tool_result'; id: string; ok: boolean; text: string }
  | { event: 'approval_request'; id: string; command: string; cwd: string };

// --- Renderer -> Extension Host ---------------------------------------------

export type WebviewToExtension =
  | {
      type: 'SEND_MESSAGE';
      content: string;
      conversationId: string;
      modelId?: string;
      thinking?: boolean;
      effort?: string;
      images?: { name: string; mime: string; dataBase64: string }[];
      mode?: 'manual' | 'auto' | 'edit' | 'plan';
      autoFallback?: boolean;
    }
  | {
      type: 'REWIND';
    }
  | {
      type: 'APPROVAL_RESPONSE';
      approvalId: string;
      decision: 'allow' | 'deny' | 'other';
      detail?: string;
    }
  | {
      type: 'INSTALL_MCP';
      mcpId: string;
      config: Record<string, string>;
    }
  | {
      type: 'UNINSTALL_MCP';
      mcpId: string;
    }
  | {
      type: 'START_MCP';
      mcpId: string;
    }
  | {
      type: 'SET_MODEL';
      modelId: string;
    }
  | {
      type: 'REQUEST_CONTEXT';
    }
  | {
      type: 'CLEAR_CONVERSATION';
    }
  | {
      type: 'OPEN_FILE';
      path: string;
    }
  | {
      type: 'REQUEST_MODELS';
    }
  | {
      type: 'REQUEST_MCP_LIST';
    }
  | {
      type: 'REQUEST_USAGE';
    };

// --- Extension Host -> Renderer ---------------------------------------------

export type ExtensionToWebview =
  | {
      type: 'USER_MESSAGE';
      content: string;
      conversationId: string;
    }
  | {
      type: 'STREAM_CHUNK';
      chunk: string;
      conversationId: string;
    }
  | {
      type: 'STREAM_DONE';
      conversationId: string;
    }
  | {
      type: 'STREAM_ERROR';
      error: string;
      conversationId: string;
    }
  | {
      type: 'STREAM_EVENT';
      ev: ForgeStreamEvent;
      conversationId: string;
    }
  | {
      type: 'CONTEXT_UPDATE';
      files: string[];
      tokenCount: number;
      ragChunkCount: number;
    }
  | {
      type: 'USAGE_UPDATE';
      tokensUsed: number;
      costUsd: number;
    }
  | {
      type: 'MCP_STATUS';
      mcpId: string;
      status: 'installing' | 'ready' | 'error';
      error?: string;
    }
  | {
      type: 'MODELS_LIST';
      models: { id: string; display_name: string; is_free: boolean }[];
    }
  | {
      type: 'MCP_LIST';
      mcps: { id: string; display_name: string; status: string }[];
    }
  | {
      type: 'USAGE_DETAILS';
      todayTokens: number;
      todayUsd: number;
      byModel: { model_id: string; tokens_in: number; tokens_out: number; cost_usd: number }[];
    };
