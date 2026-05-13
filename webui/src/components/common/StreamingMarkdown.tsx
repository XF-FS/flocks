import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import 'highlight.js/styles/github-dark.css';

const sanitizeSchema = {
  ...defaultSchema,
  strip: [...(defaultSchema.strip || []), 'style'],
};

export interface StreamingMarkdownProps {
  content: string;
  isStreaming: boolean;
}

export function StreamingMarkdown({ content, isStreaming }: StreamingMarkdownProps) {
  const [finalContent, setFinalContent] = useState('');

  useEffect(() => {
    if (!isStreaming) {
      setFinalContent(content);
    }
  }, [content, isStreaming]);

  if (isStreaming) {
    return (
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkBreaks]}
          rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
          components={{
            code({ className, children, ...props }) {
              const isBlock = String(children ?? '').endsWith('\n');
              if (!isBlock) {
                return (
                  <code
                    className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-[0.85em] font-mono"
                    {...props}
                  >
                    {children}
                  </code>
                );
              }
              return (
                <code className={className} {...props}>
                  {children}
                </code>
              );
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="prose prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema], [rehypeHighlight, { detect: false, ignoreMissing: true }]]}
        components={{
          code({ className, children, ...props }) {
            const isBlock =
              /language-/.test(className || '') ||
              /\bhljs\b/.test(className || '') ||
              String(children ?? '').endsWith('\n');
            if (!isBlock) {
              return (
                <code
                  className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-[0.85em] font-mono"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {finalContent || content}
      </ReactMarkdown>
    </div>
  );
}
