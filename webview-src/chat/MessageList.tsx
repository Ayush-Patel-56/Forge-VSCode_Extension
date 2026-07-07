// webview-src/chat/MessageList.tsx
import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { ConversationItem, LiveStatus, TextItem } from './types';
import ToolBlock from './ToolBlock';
import ApprovalCard from './ApprovalCard';
import StatusLine from './StatusLine';

const MONO_FONT = 'var(--vscode-editor-font-family), monospace';

function TextBlock({ item }: { item: TextItem }) {
  if (item.role === 'user') {
    return (
      <div
        style={{
          background: 'var(--vscode-editor-inactiveSelectionBackground)',
          borderLeft: '3px solid var(--vscode-focusBorder)',
          borderRadius: 6,
          padding: '10px 12px',
          marginTop: 12,
          marginBottom: 12,
          whiteSpace: 'pre-wrap',
          fontFamily: MONO_FONT,
          fontSize: 13,
        }}
      >
        {item.content}
      </div>
    );
  }

  // Assistant text: plain flowing markdown, no card. Nothing to render yet
  // if the segment hasn't received its first chunk.
  if (!item.content) return null;

  return (
    <div style={{ marginTop: 12, marginBottom: 12, color: 'var(--vscode-foreground)' }}>
      <ReactMarkdown
        components={{
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
          },
        }}
      >
        {item.content}
      </ReactMarkdown>
    </div>
  );
}

export default function MessageList({
  items,
  liveStatus,
  onRespondApproval,
  bottomRef,
}: {
  items: ConversationItem[];
  liveStatus: LiveStatus | null;
  onRespondApproval: (id: string, decision: 'allow' | 'deny' | 'other', detail?: string) => void;
  bottomRef: React.RefObject<HTMLDivElement>;
}) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '4px 12px 12px' }}>
      {items.map(item => {
        if (item.kind === 'text') return <TextBlock key={item.id} item={item} />;
        if (item.kind === 'tool') return <ToolBlock key={item.id} item={item} />;
        return <ApprovalCard key={item.id} item={item} onRespond={onRespondApproval} />;
      })}
      {liveStatus && <StatusLine label={liveStatus.label} startedAt={liveStatus.startedAt} />}
      <div ref={bottomRef} />
    </div>
  );
}
