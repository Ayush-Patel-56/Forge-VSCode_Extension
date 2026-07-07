// webview-src/chat/StatusLine.tsx
import React, { useEffect, useState } from 'react';

const SPINNER_FRAMES = ['✳', '✢', '✻', '✽'];
const TICK_MS = 200;

/**
 * Live "true agent" status line shown at the bottom of the conversation
 * while a turn is streaming: a cycling spinner glyph, the current activity
 * label, and an elapsed-seconds counter. Owns its own interval and cleans
 * it up on unmount (i.e. when the parent stops rendering it on
 * STREAM_DONE/STREAM_ERROR).
 */
export default function StatusLine({ label, startedAt }: { label: string; startedAt: number }) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setTick(t => t + 1), TICK_MS);
    return () => clearInterval(interval);
  }, []);

  const frame = SPINNER_FRAMES[tick % SPINNER_FRAMES.length];
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));

  return (
    <div
      style={{
        marginTop: 6,
        marginBottom: 12,
        fontSize: 12,
        fontFamily: 'var(--vscode-editor-font-family), monospace',
        color: 'var(--vscode-descriptionForeground)',
      }}
    >
      {frame} {label} · {elapsedSeconds}s
    </div>
  );
}
