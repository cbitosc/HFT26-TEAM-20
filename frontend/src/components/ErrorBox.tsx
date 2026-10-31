import { ApiError } from "../api/client";

export function ErrorBox({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const code = error instanceof ApiError ? error.code : "ERROR";
  const message =
    error instanceof Error ? error.message : "Something went wrong.";
  const details = error instanceof ApiError ? error.details : null;

  return (
    <div className="errorbox" role="alert">
      <div className="errorbox-head">
        <strong>Error</strong>
        <code className="errorbox-code">{code}</code>
      </div>
      <p>{message}</p>
      {details && details.length > 0 && (
        <ul className="errorbox-details">
          {details.map((d, i) => (
            <li key={`${d.field}-${i}`}>
              <code>{d.field}</code>: {d.message}
            </li>
          ))}
        </ul>
      )}
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
