// webview-src/chat/App.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';

declare const acquireVsCodeApi: () => {
  postMessage: (msg: unknown) => void;
  getState: () => unknown;
  setState: (state: unknown) => void;
};

const vscode = acquireVsCodeApi();

interface ToolLine {
  id: string;
  kind: 'call' | 'result';
  text: string;
  ok?: boolean;
}

interface ApprovalRequest {
  id: string;
  command: string;
  cwd: string;
  resolved?: boolean;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  toolLines?: ToolLine[];
  approvals?: ApprovalRequest[];
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [contextFiles, setContextFiles] = useState<string[]>([]);
  const [ragChunkCount, setRagChunkCount] = useState(0);
  const [tokenCount, setTokenCount] = useState(0);
  const [costUsd, setCostUsd] = useState(0);
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [thinking, setThinking] = useState(false);
  const [effort, setEffort] = useState('medium');
  const [otherDrafts, setOtherDrafts] = useState<Record<string, string>>({});
  const conversationId = useRef(crypto.randomUUID());
  const bottomRef = useRef<HTMLDivElement>(null);

  // Ensures a streaming assistant message exists (creating one if the last
  // message isn't already an in-progress assistant turn), then applies
  // `updater` to it. Used by tool_call/tool_result/approval_request events,
  // which can arrive interleaved with or before any text content.
  const updateStreamingAssistant = useCallback((updater: (m: Message) => Message) => {
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last?.role === 'assistant' && last.streaming) {
        return [...prev.slice(0, -1), updater(last)];
      }
      const fresh: Message = { id: crypto.randomUUID(), role: 'assistant', content: '', streaming: true };
      return [...prev, updater(fresh)];
    });
  }, []);

  useEffect(() => {
    // Request initial context
    vscode.postMessage({ type: 'REQUEST_CONTEXT' });

    const handler = (event: MessageEvent) => {
      const msg = event.data;
      switch (msg.type) {
        case 'USER_MESSAGE':
          setIsStreaming(true);
          setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', content: msg.content }]);
          break;
        case 'STREAM_CHUNK':
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last?.role === 'assistant' && last.streaming) {
              return [...prev.slice(0, -1), { ...last, content: last.content + msg.chunk }];
            }
            return [...prev, { id: crypto.randomUUID(), role: 'assistant', content: msg.chunk, streaming: true }];
          });
          break;
        case 'STREAM_EVENT': {
          const ev = msg.ev;
          if (ev.event === 'status') {
            setStatusLabel(ev.label);
          } else if (ev.event === 'tool_call') {
            const argsPreview = JSON.stringify(ev.args ?? {});
            updateStreamingAssistant(m => ({
              ...m,
              toolLines: [...(m.toolLines ?? []), { id: ev.id, kind: 'call', text: `$ ${ev.name} ${argsPreview}` }],
            }));
          } else if (ev.event === 'tool_result') {
            updateStreamingAssistant(m => ({
              ...m,
              toolLines: [...(m.toolLines ?? []), { id: ev.id, kind: 'result', text: ev.text, ok: ev.ok }],
            }));
          } else if (ev.event === 'approval_request') {
            updateStreamingAssistant(m => ({
              ...m,
              approvals: [...(m.approvals ?? []), { id: ev.id, command: ev.command, cwd: ev.cwd }],
            }));
          }
          break;
        }
        case 'STREAM_DONE':
          setIsStreaming(false);
          setStatusLabel(null);
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last?.streaming) return [...prev.slice(0, -1), { ...last, streaming: false }];
            return prev;
          });
          break;
        case 'STREAM_ERROR':
          setIsStreaming(false);
          setStatusLabel(null);
          setMessages(prev => [...prev, {
            id: crypto.randomUUID(), role: 'assistant',
            content: `Error: ${msg.error}`
          }]);
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
      }
    };

    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(() => {
    if (!input.trim() || isStreaming) return;
    const content = input.trim();
    setInput('');
    setIsStreaming(true);
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', content }]);
    vscode.postMessage({
      type: 'SEND_MESSAGE',
      content,
      conversationId: conversationId.current,
      thinking,
      effort,
    });
  }, [input, isStreaming, thinking, effort]);

  const respondToApproval = useCallback((approvalId: string, decision: 'allow' | 'deny' | 'other', detail?: string) => {
    vscode.postMessage({ type: 'APPROVAL_RESPONSE', approvalId, decision, detail });
    setMessages(prev => prev.map(m => {
      if (!m.approvals?.some(a => a.id === approvalId)) return m;
      return { ...m, approvals: m.approvals.map(a => a.id === approvalId ? { ...a, resolved: true } : a) };
    }));
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'var(--vscode-font-family)' }}>
      {/* Context badge */}
      {(contextFiles.length > 0 || ragChunkCount > 0) && (
        <div style={{ padding: '4px 12px', fontSize: 11, color: 'var(--vscode-descriptionForeground)', borderBottom: '1px solid var(--vscode-panel-border)' }}>
          {contextFiles.map(f => f.split('/').pop()).join(', ')} · ~{tokenCount.toLocaleString()} tokens
          {ragChunkCount > 0 && ` · ${ragChunkCount} codebase chunks`}
          {costUsd > 0 && ` · $${costUsd.toFixed(4)} today`}
        </div>
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
        {messages.map((msg, i) => {
          const isLast = i === messages.length - 1;
          return (
            <div key={msg.id} style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, color: 'var(--vscode-descriptionForeground)', textTransform: 'uppercase' }}>
                {msg.role === 'user' ? 'You' : 'Forge'}
              </div>
              <div style={{ color: 'var(--vscode-foreground)' }}>
                <ReactMarkdown components={{
                  code({ className, children }) {
                    const match = /language-(\w+)/.exec(className || '');
                    return match ? (
                      <SyntaxHighlighter language={match[1]} PreTag="div">
                        {String(children)}
                      </SyntaxHighlighter>
                    ) : (
                      <code style={{ background: 'var(--vscode-textBlockQuote-background)', padding: '2px 4px', borderRadius: 3 }}>
                        {children}
                      </code>
                    );
                  }
                }}>
                  {msg.content}
                </ReactMarkdown>
              </div>

              {/* Tool call / result trace */}
              {msg.toolLines && msg.toolLines.length > 0 && (
                <div style={{ marginTop: 6, fontFamily: 'var(--vscode-editor-font-family, monospace)', fontSize: 12 }}>
                  {msg.toolLines.map((line, idx) => (
                    <div
                      key={`${line.id}-${line.kind}-${idx}`}
                      style={{
                        color: line.kind === 'call' ? 'var(--vscode-foreground)' : 'var(--vscode-descriptionForeground)',
                        opacity: line.kind === 'result' ? 0.8 : 1,
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {line.kind === 'call' ? line.text : `  ${line.ok === false ? '✗' : '→'} ${line.text}`}
                    </div>
                  ))}
                </div>
              )}

              {/* Approval requests */}
              {msg.approvals && msg.approvals.map(ap => (
                <div
                  key={ap.id}
                  style={{
                    marginTop: 8, padding: 8, border: '1px solid var(--vscode-panel-border)',
                    borderRadius: 4, background: 'var(--vscode-textBlockQuote-background)',
                  }}
                >
                  <div style={{ fontSize: 11, color: 'var(--vscode-descriptionForeground)', marginBottom: 4 }}>
                    Forge wants to run a command in {ap.cwd}
                  </div>
                  <code style={{ display: 'block', marginBottom: 8, fontSize: 12, whiteSpace: 'pre-wrap' }}>{ap.command}</code>
                  {!ap.resolved ? (
                    <>
                      <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                        <button onClick={() => respondToApproval(ap.id, 'allow')}>Continue</button>
                        <button onClick={() => respondToApproval(ap.id, 'deny')}>No</button>
                      </div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <input
                          type="text"
                          placeholder="Or tell Forge what to do instead..."
                          value={otherDrafts[ap.id] ?? ''}
                          onChange={e => setOtherDrafts(prev => ({ ...prev, [ap.id]: e.target.value }))}
                          style={{
                            flex: 1, background: 'var(--vscode-input-background)', color: 'var(--vscode-input-foreground)',
                            border: '1px solid var(--vscode-input-border)', borderRadius: 4, padding: '4px 6px', fontSize: 12,
                          }}
                        />
                        <button onClick={() => respondToApproval(ap.id, 'other', otherDrafts[ap.id] ?? '')}>Send</button>
                      </div>
                    </>
                  ) : (
                    <div style={{ fontSize: 11, color: 'var(--vscode-descriptionForeground)' }}>Resolved</div>
                  )}
                </div>
              ))}

              {/* Status line under the last message */}
              {isLast && statusLabel && (
                <div style={{ marginTop: 4, fontSize: 11, fontStyle: 'italic', color: 'var(--vscode-descriptionForeground)' }}>
                  {statusLabel === 'thinking' ? 'thinking…' : 'responding…'}
                </div>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: '8px 12px', borderTop: '1px solid var(--vscode-panel-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6, fontSize: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input type="checkbox" checked={thinking} onChange={e => setThinking(e.target.checked)} />
            think
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            effort
            <select value={effort} onChange={e => setEffort(e.target.value)}>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
              <option value="max">max</option>
            </select>
          </label>
        </div>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
          placeholder="Ask Forge anything... (Enter to send, Shift+Enter for newline)"
          disabled={isStreaming}
          rows={3}
          style={{
            width: '100%', resize: 'none', boxSizing: 'border-box',
            background: 'var(--vscode-input-background)',
            color: 'var(--vscode-input-foreground)',
            border: '1px solid var(--vscode-input-border)',
            borderRadius: 4, padding: '6px 8px', fontSize: 13,
            fontFamily: 'inherit', outline: 'none',
          }}
        />
      </div>
    </div>
  );
}
