import { useState } from "react";
import { Check, Copy } from "lucide-react";

export function CopyButton({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  function onCopy() {
    const done = () => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    };
    try {
      void navigator.clipboard?.writeText(value).then(done, done);
    } catch {
      done();
    }
  }

  return (
    <button
      type="button"
      className="copy-btn"
      onClick={onCopy}
      aria-label={label ? `Copy ${label}` : "Copy to clipboard"}
      title="Copy"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

export function HashChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="hashchip">
      <span className="label">{label}</span>
      <span className="value" title={value}>
        {value}
      </span>
      <CopyButton value={value} label={label} />
    </div>
  );
}
