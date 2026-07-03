// webview-src/mcp/index.tsx
//
// NOT specified in forge_spec.md (no code block provided for this file).
// Trivial mirror of webview-src/chat/index.tsx that mounts MCPApp instead of
// the chat App. No CSS import — Tailwind directives are already emitted once
// via the chat bundle's styles.css and this webview reuses the same
// VSCode CSS variables without needing its own stylesheet.
import React from 'react';
import { createRoot } from 'react-dom/client';
import MCPApp from './App';

const root = createRoot(document.getElementById('root')!);
root.render(<MCPApp />);
