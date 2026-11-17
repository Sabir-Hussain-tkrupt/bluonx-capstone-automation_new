import { useState } from 'react';
import { EditorContent, useEditor, useEditorState, type Editor } from '@tiptap/react';
import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  Bold,
  Code,
  Heading1,
  Heading2,
  Heading3,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  Minus,
  Quote,
  Redo2,
  RemoveFormatting,
  Strikethrough,
  Underline as UnderlineIcon,
  Undo2,
  Unlink,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import { richTextExtensions } from './extensions';

export interface RichTextEditorProps {
  /** HTML to start from. The editor is uncontrolled after mount. */
  initialContent?: string;
  onChange?: (html: string, text: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
  /** Accessible name for the writing area. */
  ariaLabel?: string;
  className?: string;
}

interface ToolbarButtonProps {
  label: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  children: React.ReactNode;
}

function ToolbarButton({ label, onClick, active, disabled, children }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      // Keep the selection in the editor while clicking the toolbar.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={cn(
        'inline-flex h-8 w-8 items-center justify-center rounded-md text-secondary-600 transition-colors',
        'hover:bg-secondary-100 hover:text-secondary-900',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
        'disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent',
        active && 'bg-primary-50 text-primary-700 hover:bg-primary-100 hover:text-primary-700',
      )}
    >
      {children}
    </button>
  );
}

function Divider() {
  return <span className="mx-1 h-5 w-px bg-secondary-200" aria-hidden="true" />;
}

const ICON = 'h-4 w-4';

function Toolbar({ editor }: { editor: Editor }) {
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');

  const s = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive('bold'),
      italic: e.isActive('italic'),
      underline: e.isActive('underline'),
      strike: e.isActive('strike'),
      h1: e.isActive('heading', { level: 1 }),
      h2: e.isActive('heading', { level: 2 }),
      h3: e.isActive('heading', { level: 3 }),
      bullet: e.isActive('bulletList'),
      ordered: e.isActive('orderedList'),
      quote: e.isActive('blockquote'),
      code: e.isActive('codeBlock'),
      link: e.isActive('link'),
      left: e.isActive({ textAlign: 'left' }),
      center: e.isActive({ textAlign: 'center' }),
      right: e.isActive({ textAlign: 'right' }),
      justify: e.isActive({ textAlign: 'justify' }),
      canUndo: e.can().undo(),
      canRedo: e.can().redo(),
    }),
  });

  const chain = () => editor.chain().focus();

  const openLink = () => {
    setLinkUrl((editor.getAttributes('link').href as string | undefined) ?? '');
    setLinkOpen(true);
  };

  const applyLink = () => {
    const url = linkUrl.trim();
    if (!url) {
      chain().extendMarkRange('link').unsetLink().run();
    } else {
      chain().extendMarkRange('link').setLink({ href: url }).run();
    }
    setLinkOpen(false);
  };

  return (
    <div className="sticky top-0 z-10 border-b border-secondary-200 bg-white/95 backdrop-blur">
      <div role="toolbar" aria-label="Formatting" className="flex flex-wrap items-center gap-0.5 px-2 py-1.5">
        <ToolbarButton label="Undo" onClick={() => chain().undo().run()} disabled={!s.canUndo}><Undo2 className={ICON} /></ToolbarButton>
        <ToolbarButton label="Redo" onClick={() => chain().redo().run()} disabled={!s.canRedo}><Redo2 className={ICON} /></ToolbarButton>
        <Divider />
        <ToolbarButton label="Heading 1" active={s.h1} onClick={() => chain().toggleHeading({ level: 1 }).run()}><Heading1 className={ICON} /></ToolbarButton>
        <ToolbarButton label="Heading 2" active={s.h2} onClick={() => chain().toggleHeading({ level: 2 }).run()}><Heading2 className={ICON} /></ToolbarButton>
        <ToolbarButton label="Heading 3" active={s.h3} onClick={() => chain().toggleHeading({ level: 3 }).run()}><Heading3 className={ICON} /></ToolbarButton>
        <Divider />
        <ToolbarButton label="Bold" active={s.bold} onClick={() => chain().toggleBold().run()}><Bold className={ICON} /></ToolbarButton>
        <ToolbarButton label="Italic" active={s.italic} onClick={() => chain().toggleItalic().run()}><Italic className={ICON} /></ToolbarButton>
        <ToolbarButton label="Underline" active={s.underline} onClick={() => chain().toggleUnderline().run()}><UnderlineIcon className={ICON} /></ToolbarButton>
        <ToolbarButton label="Strikethrough" active={s.strike} onClick={() => chain().toggleStrike().run()}><Strikethrough className={ICON} /></ToolbarButton>
        <Divider />
        <ToolbarButton label="Bulleted list" active={s.bullet} onClick={() => chain().toggleBulletList().run()}><List className={ICON} /></ToolbarButton>
        <ToolbarButton label="Numbered list" active={s.ordered} onClick={() => chain().toggleOrderedList().run()}><ListOrdered className={ICON} /></ToolbarButton>
        <ToolbarButton label="Quote" active={s.quote} onClick={() => chain().toggleBlockquote().run()}><Quote className={ICON} /></ToolbarButton>
        <ToolbarButton label="Code block" active={s.code} onClick={() => chain().toggleCodeBlock().run()}><Code className={ICON} /></ToolbarButton>
        <ToolbarButton label="Divider line" onClick={() => chain().setHorizontalRule().run()}><Minus className={ICON} /></ToolbarButton>
        <Divider />
        <ToolbarButton label="Align left" active={s.left} onClick={() => chain().setTextAlign('left').run()}><AlignLeft className={ICON} /></ToolbarButton>
        <ToolbarButton label="Align center" active={s.center} onClick={() => chain().setTextAlign('center').run()}><AlignCenter className={ICON} /></ToolbarButton>
        <ToolbarButton label="Align right" active={s.right} onClick={() => chain().setTextAlign('right').run()}><AlignRight className={ICON} /></ToolbarButton>
        <ToolbarButton label="Justify" active={s.justify} onClick={() => chain().setTextAlign('justify').run()}><AlignJustify className={ICON} /></ToolbarButton>
        <Divider />
        <ToolbarButton label="Link" active={s.link} onClick={openLink}><LinkIcon className={ICON} /></ToolbarButton>
        {s.link && (
          <ToolbarButton label="Remove link" onClick={() => chain().extendMarkRange('link').unsetLink().run()}><Unlink className={ICON} /></ToolbarButton>
        )}
        <ToolbarButton label="Clear formatting" onClick={() => chain().unsetAllMarks().clearNodes().run()}><RemoveFormatting className={ICON} /></ToolbarButton>
      </div>

      {linkOpen && (
        <div className="flex flex-wrap items-center gap-2 border-t border-secondary-100 px-3 py-2">
          <label htmlFor="rte-link-url" className="text-xs font-medium text-secondary-600">Link URL</label>
          <input
            id="rte-link-url"
            type="url"
            autoFocus
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); applyLink(); }
              if (e.key === 'Escape') { e.preventDefault(); setLinkOpen(false); }
            }}
            placeholder="https://example.com"
            className="h-8 min-w-0 flex-1 rounded-md border border-secondary-300 px-2 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
          />
          <button type="button" onClick={applyLink} className="h-8 rounded-md bg-primary-600 px-3 text-xs font-medium text-white hover:bg-primary-700">Apply</button>
          <button type="button" onClick={() => setLinkOpen(false)} className="h-8 rounded-md px-3 text-xs font-medium text-secondary-600 hover:bg-secondary-100">Cancel</button>
        </div>
      )}
    </div>
  );
}

/**
 * Document-style rich-text editor (bold, italic, underline, headings, lists,
 * quotes, code, links, alignment, undo / redo). It grows with its content, so
 * a note can be as long as a document; the toolbar stays pinned while
 * scrolling.
 */
export function RichTextEditor({
  initialContent = '',
  onChange,
  placeholder,
  autoFocus = false,
  ariaLabel = 'Note content',
  className,
}: RichTextEditorProps) {
  const editor = useEditor({
    extensions: richTextExtensions(placeholder),
    content: initialContent,
    autofocus: autoFocus ? 'end' : false,
    editorProps: {
      attributes: {
        class: 'rich-text min-h-[18rem] px-5 py-4',
        'aria-label': ariaLabel,
        'aria-multiline': 'true',
        role: 'textbox',
      },
    },
    onUpdate: ({ editor: e }) => onChange?.(e.isEmpty ? '' : e.getHTML(), e.getText()),
  });

  const words = useEditorState({
    editor,
    selector: ({ editor: e }) => (e ? e.storage.characterCount.words() : 0),
  });

  return (
    <div
      className={cn(
        'rounded-lg border border-secondary-300 bg-white transition-colors',
        'focus-within:border-primary-500 focus-within:ring-2 focus-within:ring-primary-500/20',
        className,
      )}
    >
      {editor && <Toolbar editor={editor} />}
      <EditorContent editor={editor} />
      <div className="flex justify-end border-t border-secondary-100 px-3 py-1.5 text-xs text-secondary-400">
        {words} {words === 1 ? 'word' : 'words'}
      </div>
    </div>
  );
}

/** Read-only rendering of editor HTML through the same schema. */
export function RichTextViewer({ content, className }: { content: string; className?: string }) {
  const editor = useEditor(
    {
      extensions: richTextExtensions(),
      content,
      editable: false,
      editorProps: { attributes: { class: cn('rich-text', className ?? '') } },
    },
    [content],
  );
  return <EditorContent editor={editor} />;
}
