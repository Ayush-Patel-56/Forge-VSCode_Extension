// src/types.ts

// --- Renderer -> Extension Host ---------------------------------------------

export type WebviewToExtension =
  | {
      type: 'SEND_MESSAGE';
      content: string;
      conversationId: string;
      modelId?: string;
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
    };

// --- Extension Host -> Renderer ---------------------------------------------

export type ExtensionToWebview =
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
    };
