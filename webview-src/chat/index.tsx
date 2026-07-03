// webview-src/chat/index.tsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';  // Tailwind base

const root = createRoot(document.getElementById('root')!);
root.render(<App />);
