// webview-src/chat/InputBar.tsx
import React, { useCallback, useRef, useState } from 'react';
import { Effort, ImageAttachment, Mode, ModelInfo, UsageDetails } from './types';
import ModelSelect from './ModelSelect';
import ModePopup from './ModePopup';
import ActionsPalette from './ActionsPalette';
import UsageModal from './UsageModal';

const EFFORTS: Effort[] = ['low', 'medium', 'high', 'max'];
const MONO_FONT = 'var(--vscode-editor-font-family), monospace';
const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024; // ~5MB

/** Read a File as an ImageAttachment (base64 payload + dimensions). */
function readImageFile(file: File): Promise<ImageAttachment> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      const dataUrl = String(reader.result);
      const dataBase64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
      const attachment: ImageAttachment = { name: file.name || 'pasted-image.png', mime: file.type, dataBase64 };
      // Dimensions are cheap here: the browser decodes from the data URL we
      // already have. Resolve regardless of decode success.
      const img = new Image();
      img.onload = () => resolve({ ...attachment, width: img.naturalWidth, height: img.naturalHeight });
      img.onerror = () => resolve(attachment);
      img.src = dataUrl;
    };
    reader.readAsDataURL(file);
  });
}

export default function InputBar({
  disabled,
  thinking,
  onThinkingChange,
  effort,
  onEffortChange,
  mode,
  onModeChange,
  autoFallback,
  onAutoFallbackChange,
  models,
  activeModelId,
  onModelChange,
  tokenCount,
  costUsd,
  onSend,
  onClearConversation,
  onRewind,
  usage,
  onRequestUsage,
  workspaceFiles,
  onRequestWorkspaceFiles,
  onRequestModels,
}: {
  disabled: boolean;
  thinking: boolean;
  onThinkingChange: (v: boolean) => void;
  effort: Effort;
  onEffortChange: (e: Effort) => void;
  mode: Mode;
  onModeChange: (m: Mode) => void;
  autoFallback: boolean;
  onAutoFallbackChange: (v: boolean) => void;
  models: ModelInfo[];
  activeModelId: string | null;
  onModelChange: (id: string) => void;
  tokenCount: number;
  costUsd: number;
  onSend: (content: string, images: ImageAttachment[], attachedFiles: string[]) => void;
  onClearConversation: () => void;
  onRewind: () => void;
  usage: UsageDetails | null;
  onRequestUsage: () => void;
  workspaceFiles: string[];
  onRequestWorkspaceFiles: (query: string) => void;
  onRequestModels: () => void;
}) {
  const [input, setInput] = useState('');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [usageOpen, setUsageOpen] = useState(false);
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const [attachedFiles, setAttachedFiles] = useState<string[]>([]);
  const [attachWarning, setAttachWarning] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const addImageFiles = useCallback(async (files: File[]) => {
    const warnings: string[] = [];
    const accepted: File[] = [];
    for (const f of files) {
      if (!f.type.startsWith('image/')) continue;
      if (f.size > MAX_IMAGE_BYTES) {
        warnings.push(`${f.name || 'image'} exceeds 5MB and was skipped`);
        continue;
      }
      accepted.push(f);
    }

    const loaded: ImageAttachment[] = [];
    for (const f of accepted) {
      try {
        loaded.push(await readImageFile(f));
      } catch {
        warnings.push(`${f.name || 'image'} could not be read`);
      }
    }

    setImages(prev => {
      const room = MAX_IMAGES - prev.length;
      if (loaded.length > room) warnings.push(`image limit is ${MAX_IMAGES} per message`);
      return [...prev, ...loaded.slice(0, Math.max(0, room))];
    });
    setAttachWarning(warnings.length > 0 ? warnings.join(' · ') : null);
  }, []);

  const send = () => {
    if (!input.trim() || disabled) return;
    onSend(input.trim(), images, attachedFiles);
    setInput('');
    setImages([]);
    setAttachedFiles([]);
    setAttachWarning(null);
  };

  const insertMention = (relPath: string) => {
    const ta = textareaRef.current;
    const mention = `@${relPath} `;
    if (!ta) {
      setInput(prev => prev + mention);
      return;
    }
    const start = ta.selectionStart ?? input.length;
    const end = ta.selectionEnd ?? start;
    setInput(prev => prev.slice(0, start) + mention + prev.slice(end));
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + mention.length;
      ta.setSelectionRange(pos, pos);
    });
  };

  const isVisionModel = (activeModelId ?? '').toLowerCase().includes('gemini');

  return (
    <div style={{ padding: '8px 12px', borderTop: '1px solid var(--vscode-panel-border)' }}>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        style={{ display: 'none' }}
        onChange={e => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = '';
          void addImageFiles(files);
        }}
      />

      {(images.length > 0 || attachedFiles.length > 0) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6, fontFamily: MONO_FONT }}>
          {images.map((img, i) => (
            <span
              key={`${img.name}-${i}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '2px 6px 2px 2px',
                borderRadius: 4,
                border: '1px solid var(--vscode-panel-border)',
                background: 'var(--vscode-editorWidget-background)',
                fontSize: 11,
              }}
            >
              <img
                src={`data:${img.mime};base64,${img.dataBase64}`}
                alt={img.name}
                style={{ width: 22, height: 22, objectFit: 'cover', borderRadius: 3 }}
              />
              <span style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{img.name}</span>
              {img.width && img.height && (
                <span style={{ color: 'var(--vscode-descriptionForeground)', fontSize: 10 }}>
                  {img.width}×{img.height}
                </span>
              )}
              <span
                onClick={() => setImages(prev => prev.filter((_, j) => j !== i))}
                style={{ cursor: 'pointer', color: 'var(--vscode-descriptionForeground)' }}
              >
                ×
              </span>
            </span>
          ))}
          {attachedFiles.map(f => (
            <span
              key={f}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '2px 8px',
                borderRadius: 4,
                border: '1px solid var(--vscode-panel-border)',
                background: 'var(--vscode-editorWidget-background)',
                fontSize: 11,
              }}
              title={f}
            >
              <span>🗎</span>
              <span style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f}</span>
              <span
                onClick={() => setAttachedFiles(prev => prev.filter(p => p !== f))}
                style={{ cursor: 'pointer', color: 'var(--vscode-descriptionForeground)' }}
              >
                ×
              </span>
            </span>
          ))}
        </div>
      )}

      {images.length > 0 && !isVisionModel && (
        <div style={{ fontSize: 10.5, color: 'var(--vscode-descriptionForeground)', marginBottom: 6, fontFamily: MONO_FONT }}>
          images route to a vision-capable model
        </div>
      )}
      {attachWarning && (
        <div style={{ fontSize: 10.5, color: 'var(--vscode-inputValidation-warningForeground, var(--vscode-editorWarning-foreground))', marginBottom: 6, fontFamily: MONO_FONT }}>
          ⚠ {attachWarning}
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setPaletteOpen(o => !o)}
            title="Actions"
            style={{
              width: 26,
              height: 26,
              lineHeight: '24px',
              borderRadius: 6,
              background: 'var(--vscode-button-secondaryBackground)',
              color: 'var(--vscode-button-secondaryForeground)',
              border: 'none',
              fontSize: 15,
              fontFamily: 'inherit',
              cursor: 'pointer',
              flexShrink: 0,
            }}
          >
            +
          </button>
          {paletteOpen && (
            <ActionsPalette
              onClose={() => setPaletteOpen(false)}
              onClearConversation={onClearConversation}
              onRewind={onRewind}
              models={models}
              activeModelId={activeModelId}
              onModelChange={onModelChange}
              effort={effort}
              onEffortChange={onEffortChange}
              thinking={thinking}
              onThinkingChange={onThinkingChange}
              autoFallback={autoFallback}
              onAutoFallbackChange={onAutoFallbackChange}
              onOpenUsage={() => setUsageOpen(true)}
              onAttachImage={() => fileInputRef.current?.click()}
              workspaceFiles={workspaceFiles}
              onRequestWorkspaceFiles={onRequestWorkspaceFiles}
              onAttachFile={relPath => setAttachedFiles(prev => (prev.includes(relPath) ? prev : [...prev, relPath]))}
              onMentionFile={insertMention}
              onRequestModels={onRequestModels}
            />
          )}
        </div>

        <textarea
          ref={textareaRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            } else if (e.key === '/' && input === '') {
              e.preventDefault();
              setPaletteOpen(true);
            }
          }}
          onPaste={e => {
            const files = Array.from(e.clipboardData?.items ?? [])
              .filter(it => it.kind === 'file' && it.type.startsWith('image/'))
              .map(it => it.getAsFile())
              .filter((f): f is File => f !== null);
            if (files.length > 0) {
              e.preventDefault();
              void addImageFiles(files);
            }
          }}
          placeholder="Ask Forge anything... (Enter to send, Shift+Enter for newline, / for actions)"
          disabled={disabled}
          rows={3}
          style={{
            flex: 1,
            resize: 'none',
            boxSizing: 'border-box',
            background: 'var(--vscode-input-background)',
            color: 'var(--vscode-input-foreground)',
            border: '1px solid var(--vscode-input-border)',
            borderRadius: 4,
            padding: '6px 8px',
            fontSize: 13,
            fontFamily: MONO_FONT,
            outline: 'none',
          }}
        />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, fontFamily: MONO_FONT }}>
        <ModePopup mode={mode} onModeChange={onModeChange} effort={effort} onEffortChange={onEffortChange} />
        <ModelSelect models={models} activeModelId={activeModelId} onSelect={onModelChange} onOpen={onRequestModels} />

        <button
          onClick={() => fileInputRef.current?.click()}
          title="Attach images"
          style={{
            background: 'var(--vscode-button-secondaryBackground)',
            color: 'var(--vscode-button-secondaryForeground)',
            border: 'none',
            borderRadius: 12,
            padding: '3px 8px',
            fontSize: 11,
            fontFamily: 'inherit',
            cursor: 'pointer',
          }}
        >
          📎
        </button>

        <button
          onClick={() => onThinkingChange(!thinking)}
          style={{
            background: thinking ? 'var(--vscode-button-background)' : 'var(--vscode-button-secondaryBackground)',
            color: thinking ? 'var(--vscode-button-foreground)' : 'var(--vscode-button-secondaryForeground)',
            border: 'none',
            borderRadius: 12,
            padding: '3px 10px',
            fontSize: 11,
            fontFamily: 'inherit',
            cursor: 'pointer',
          }}
        >
          ✦ think
        </button>

        <div style={{ display: 'flex', border: '1px solid var(--vscode-panel-border)', borderRadius: 4, overflow: 'hidden' }}>
          {EFFORTS.map(e => (
            <button
              key={e}
              onClick={() => onEffortChange(e)}
              style={{
                background: effort === e ? 'var(--vscode-button-background)' : 'transparent',
                color: effort === e ? 'var(--vscode-button-foreground)' : 'var(--vscode-foreground)',
                border: 'none',
                padding: '3px 8px',
                fontSize: 11,
                fontFamily: 'inherit',
                cursor: 'pointer',
              }}
            >
              {e}
            </button>
          ))}
        </div>

        <div style={{ flex: 1 }} />

        <div style={{ fontSize: 11, color: 'var(--vscode-descriptionForeground)' }}>
          {tokenCount.toLocaleString()}t{costUsd > 0 ? ` · $${costUsd.toFixed(4)}` : ''}
        </div>
      </div>

      {usageOpen && <UsageModal usage={usage} onRequestUsage={onRequestUsage} onClose={() => setUsageOpen(false)} />}
    </div>
  );
}
