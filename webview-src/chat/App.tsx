// webview-src/chat/App.tsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ConversationItem, Effort, ImageAttachment, LiveStatus, Mode, ModelInfo, TextItem, ToolItem, UsageDetails } from './types';
import MessageList from './MessageList';
import InputBar from './InputBar';

declare const acquireVsCodeApi: () => {
  postMessage: (msg: unknown) => void;
  getState: () => unknown;
  setState: (state: unknown) => void;
};

const vscode = acquireVsCodeApi();

const MONO_FONT = 'var(--vscode-editor-font-family), monospace';

export default function App() {
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [contextFiles, setContextFiles] = useState<string[]>([]);
  const [ragChunkCount, setRagChunkCount] = useState(0);
  const [tokenCount, setTokenCount] = useState(0);
  const [costUsd, setCostUsd] = useState(0);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [activeModelId, setActiveModelId] = useState<string | null>(null);
  const [thinking, setThinking] = useState(false);
  const [effort, setEffort] = useState<Effort>('medium');
  const [mode, setMode] = useState<Mode>('manual');
  const [autoFallback, setAutoFallback] = useState(true);
  const [usage, setUsage] = useState<UsageDetails | null>(null);
  const [workspaceFiles, setWorkspaceFiles] = useState<string[]>([]);

  // Live activity, used to derive the StatusLine label. `statusLabel` tracks
  // the latest 'status' event; `activeTool` tracks a tool_call that hasn't
  // received its matching tool_result yet (matched by id, not index) and
  // takes precedence over statusLabel while set.
  const [statusLabel, setStatusLabel] = useState<'thinking' | 'responding' | null>(null);
  const [activeTool, setActiveTool] = useState<{ id: string; name: string; args: unknown } | null>(null);
  const [turnStartedAt, setTurnStartedAt] = useState<number | null>(null);

  const conversationId = useRef(crypto.randomUUID());
  const bottomRef = useRef<HTMLDivElement>(null);

  const appendChunk = useCallback((chunk: string) => {
    setItems(prev => {
      const last = prev[prev.length - 1];
      if (last && last.kind === 'text' && last.role === 'assistant' && last.streaming) {
        const updated: TextItem = { ...last, content: last.content + chunk };
        return [...prev.slice(0, -1), updated];
      }
      const fresh: TextItem = { kind: 'text', id: crypto.randomUUID(), role: 'assistant', content: chunk, streaming: true };
      return [...prev, fresh];
    });
  }, []);

  useEffect(() => {
    vscode.postMessage({ type: 'REQUEST_CONTEXT' });
    vscode.postMessage({ type: 'REQUEST_MODELS' });

    const handler = (event: MessageEvent) => {
      const msg = event.data;
      switch (msg.type) {
        case 'USER_MESSAGE':
          setIsStreaming(true);
          setTurnStartedAt(Date.now());
          setItems(prev => [...prev, { kind: 'text', id: crypto.randomUUID(), role: 'user', content: msg.content }]);
          break;

        case 'STREAM_CHUNK':
          appendChunk(msg.chunk);
          break;

        case 'STREAM_EVENT': {
          const ev = msg.ev;
          if (ev.event === 'status') {
            setStatusLabel(ev.label);
            // Record a dim milestone row in the transcript, skipping
            // duplicates when the same status repeats back-to-back.
            const label = ev.label === 'thinking' ? 'Thinking' : 'Responding';
            setItems(prev => {
              const last = prev[prev.length - 1];
              if (last && last.kind === 'milestone' && last.label === label) return prev;
              return [...prev, { kind: 'milestone', id: crypto.randomUUID(), label }];
            });
          } else if (ev.event === 'tool_call') {
            const toolItem: ToolItem = { kind: 'tool', id: ev.id, name: ev.name, args: ev.args };
            setItems(prev => [...prev, toolItem]);
            setActiveTool({ id: ev.id, name: ev.name, args: ev.args });
          } else if (ev.event === 'tool_result') {
            setItems(prev =>
              prev.map(it => (it.kind === 'tool' && it.id === ev.id ? { ...it, result: { ok: ev.ok, text: ev.text } } : it))
            );
            setActiveTool(prev => (prev && prev.id === ev.id ? null : prev));
          } else if (ev.event === 'approval_request') {
            setItems(prev => [...prev, { kind: 'approval', id: ev.id, command: ev.command, cwd: ev.cwd }]);
          }
          break;
        }

        case 'STREAM_DONE':
          setIsStreaming(false);
          setStatusLabel(null);
          setActiveTool(null);
          setTurnStartedAt(null);
          setItems(prev => {
            const last = prev[prev.length - 1];
            if (last && last.kind === 'text' && last.streaming) {
              return [...prev.slice(0, -1), { ...last, streaming: false }];
            }
            return prev;
          });
          break;

        case 'STREAM_ERROR':
          setIsStreaming(false);
          setStatusLabel(null);
          setActiveTool(null);
          setTurnStartedAt(null);
          setItems(prev => [
            ...prev,
            { kind: 'text', id: crypto.randomUUID(), role: 'assistant', content: `Error: ${msg.error}` },
          ]);
          break;

        case 'CONTEXT_UPDATE':
          setContextFiles(msg.files);
          setTokenCount(msg.tokenCount);
          setRagChunkCount(msg.ragChunkCount ?? 0);
          break;

        case 'USAGE_UPDATE':
          setTokenCount(msg.tokensUsed);
          setCostUsd(msg.costUsd);
          break;

        case 'MODELS_LIST':
          setModels(msg.models);
          setActiveModelId(prev => prev ?? msg.models[0]?.id ?? null);
          break;

        case 'USAGE_DETAILS':
          setUsage({ todayTokens: msg.todayTokens, todayUsd: msg.todayUsd, byModel: msg.byModel });
          break;

        case 'WORKSPACE_FILES':
          setWorkspaceFiles(msg.files);
          break;
      }
    };

    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [appendChunk]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [items]);

  const sendMessage = useCallback(
    (content: string, images: ImageAttachment[], attachedFiles: string[]) => {
      setIsStreaming(true);
      setTurnStartedAt(Date.now());
      setItems(prev => [
        ...prev,
        {
          kind: 'text',
          id: crypto.randomUUID(),
          role: 'user',
          content,
          imageNames: images.length > 0 ? images.map(i => i.name) : undefined,
          attachedFiles: attachedFiles.length > 0 ? attachedFiles : undefined,
        },
      ]);
      vscode.postMessage({
        type: 'SEND_MESSAGE',
        content,
        conversationId: conversationId.current,
        modelId: activeModelId ?? undefined,
        thinking,
        effort,
        mode,
        autoFallback,
        images: images.length > 0
          ? images.map(i => ({ name: i.name, mime: i.mime, dataBase64: i.dataBase64 }))
          : undefined,
        attachedFiles: attachedFiles.length > 0 ? attachedFiles : undefined,
      });
    },
    [activeModelId, thinking, effort, mode, autoFallback]
  );

  const handleModelChange = useCallback((id: string) => {
    setActiveModelId(id);
    vscode.postMessage({ type: 'SET_MODEL', modelId: id });
  }, []);

  const clearConversation = useCallback(() => {
    setItems([]);
    vscode.postMessage({ type: 'CLEAR_CONVERSATION' });
  }, []);

  const rewind = useCallback(() => {
    vscode.postMessage({ type: 'REWIND' });
    setItems(prev => {
      let cutoff = -1;
      for (let i = prev.length - 1; i >= 0; i--) {
        const it = prev[i];
        if (it.kind === 'text' && it.role === 'user') {
          cutoff = i;
          break;
        }
      }
      return cutoff === -1 ? prev : prev.slice(0, cutoff);
    });
  }, []);

  const requestUsage = useCallback(() => {
    vscode.postMessage({ type: 'REQUEST_USAGE' });
  }, []);

  const requestWorkspaceFiles = useCallback((query: string) => {
    vscode.postMessage({ type: 'REQUEST_WORKSPACE_FILES', query });
  }, []);

  const respondToApproval = useCallback((id: string, decision: 'allow' | 'deny' | 'other', detail?: string) => {
    vscode.postMessage({ type: 'APPROVAL_RESPONSE', approvalId: id, decision, detail });
    setItems(prev => prev.map(it => (it.kind === 'approval' && it.id === id ? { ...it, decision, detail } : it)));
  }, []);

  const liveStatus: LiveStatus | null = isStreaming
    ? {
        label: activeTool
          ? activeTool.name === 'terminal.run_command'
            ? `running $ ${(activeTool.args as { command?: string } | undefined)?.command ?? ''}…`
            : `calling ${activeTool.name}…`
          : statusLabel === 'thinking'
            ? 'thinking…'
            : statusLabel === 'responding'
              ? 'responding…'
              : 'working…',
        startedAt: turnStartedAt ?? Date.now(),
      }
    : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: MONO_FONT }}>
      {(contextFiles.length > 0 || ragChunkCount > 0) && (
        <div
          style={{
            padding: '4px 12px',
            fontSize: 11,
            fontFamily: MONO_FONT,
            color: 'var(--vscode-descriptionForeground)',
            borderBottom: '1px solid var(--vscode-panel-border)',
          }}
        >
          {contextFiles.map(f => f.split('/').pop()).join(', ')} · ~{tokenCount.toLocaleString()} tokens
          {ragChunkCount > 0 && ` · ${ragChunkCount} codebase chunks`}
        </div>
      )}

      <MessageList items={items} liveStatus={liveStatus} onRespondApproval={respondToApproval} bottomRef={bottomRef} />

      <InputBar
        disabled={isStreaming}
        thinking={thinking}
        onThinkingChange={setThinking}
        effort={effort}
        onEffortChange={setEffort}
        mode={mode}
        onModeChange={setMode}
        autoFallback={autoFallback}
        onAutoFallbackChange={setAutoFallback}
        models={models}
        activeModelId={activeModelId}
        onModelChange={handleModelChange}
        tokenCount={tokenCount}
        costUsd={costUsd}
        onSend={sendMessage}
        onClearConversation={clearConversation}
        onRewind={rewind}
        usage={usage}
        onRequestUsage={requestUsage}
        workspaceFiles={workspaceFiles}
        onRequestWorkspaceFiles={requestWorkspaceFiles}
      />
    </div>
  );
}
