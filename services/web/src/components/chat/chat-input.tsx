"use client";

import { useRef, useState } from "react";
import { ArrowUp } from "lucide-react";

export function ChatInput({
  onSubmit,
  disabled,
  onFocus,
}: {
  onSubmit: (value: string) => void;
  disabled?: boolean;
  onFocus?: () => void;
}) {
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  function submit() {
    const v = text.trim();
    if (!v || disabled) return;
    onSubmit(v);
    setText("");
    if (ref.current) ref.current.style.height = "auto";
  }

  const canSend = !disabled && text.trim().length > 0;

  return (
    <div
      className="relative flex items-end rounded-2xl px-4 py-3 transition-all duration-200"
      style={{
        background: "var(--bg-panel)",
        border: focused ? "2px solid var(--brand)" : "2px solid var(--border)",
        boxShadow: focused ? "var(--shadow-md)" : "var(--shadow-sm)",
      }}
    >
      <textarea
        ref={ref}
        value={text}
        disabled={disabled}
        placeholder="Ask about a scrip, sector flow, broker behaviour, or news impact…"
        rows={1}
        onFocus={() => { setFocused(true); onFocus?.(); }}
        onBlur={() => setFocused(false)}
        onInput={(e) => {
          const el = e.currentTarget;
          el.style.height = "auto";
          el.style.height = Math.min(el.scrollHeight, 180) + "px";
        }}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        className="max-h-[180px] w-full resize-none bg-transparent pr-12 text-[15px] leading-relaxed text-fg outline-none placeholder:text-fg-muted disabled:opacity-40"
      />
      <button
        onClick={submit}
        disabled={!canSend}
        className="absolute bottom-3 right-3 flex h-8 w-8 items-center justify-center rounded-xl transition-all duration-150 disabled:opacity-25 hover:opacity-80"
        style={{ background: "var(--brand)" }}
        aria-label="Send"
      >
        <ArrowUp className="h-4 w-4 text-white" strokeWidth={2.5} />
      </button>
    </div>
  );
}
