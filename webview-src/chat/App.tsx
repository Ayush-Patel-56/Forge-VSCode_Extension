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

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [contextFiles, setContextFiles] = useState<string[]>([]);
  const [ragChunkCount, setRagChunkCount] = useState(0);
  const [tokenCount, setTokenCount] = useState(0);
  const [costUsd, setCostUsd] = useState(0);
  const conversationId = useRef(crypto.randomUUID());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Request initial context
    vscode.postMessage({ type: 'REQUEST_CONTEXT' });

    const handler = (event: MessageEvent) => {
      const msg = event.data;
      switch (msg.type) {
        case 'STREAM_CHUNK':
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last?.role === 'assistant' && last.streaming) {
              return [...prev.slice(0, -1), { ...last, content: last.content + msg.chunk }];
            }
            return [...prev, { id: crypto.randomUUID(), role: 'assistant', content: msg.chunk, streaming: true }];
          });
          break;
        case 'STREAM_DONE':
          setIsStreaming(false);
          setMessages(prev => {
            const last = prev[prev.length - 1];
            if (last?.streaming) return [...prev.slice(0, -1), { ...last, streaming: false }];
            return prev;
          });
          break;
        case 'STREAM_ERROR':
          setIsStreaming(false);
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
    });
  }, [input, isStreaming]);

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
        {messages.map(msg => (
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
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ padding: '8px 12px', borderTop: '1px solid var(--vscode-panel-border)' }}>
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
