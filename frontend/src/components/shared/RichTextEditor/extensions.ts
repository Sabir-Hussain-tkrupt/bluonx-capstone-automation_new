import StarterKit from '@tiptap/starter-kit';
import TextAlign from '@tiptap/extension-text-align';
import { CharacterCount, Placeholder } from '@tiptap/extensions';

/**
 * One schema for editing AND viewing. Rendering stored HTML through the same
 * schema (never `dangerouslySetInnerHTML`) drops anything outside it, so a note
 * can only ever contain these formats.
 */
export function richTextExtensions(placeholder?: string) {
  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3] },
      link: {
        openOnClick: false,
        autolink: true,
        defaultProtocol: 'https',
        protocols: ['http', 'https', 'mailto', 'tel'],
        HTMLAttributes: { rel: 'noopener noreferrer nofollow', target: '_blank' },
      },
    }),
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
    CharacterCount,
    Placeholder.configure({ placeholder: placeholder ?? 'Start writing…' }),
  ];
}
