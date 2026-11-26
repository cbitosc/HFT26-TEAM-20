// Named Spinner for compatibility, but renders a skeleton shimmer. The label
// stays in the DOM (screen-reader status) so loading states remain announced.
export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="skeleton" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <span className="skel-line w-40" aria-hidden="true" />
      <span className="skel-line w-80" aria-hidden="true" />
      <span className="skel-line w-60" aria-hidden="true" />
    </div>
  );
}
