import { Inbox } from "lucide-react";

export function Empty({ message }: { message: string }) {
  return (
    <div className="empty" role="status">
      <Inbox size={28} aria-hidden="true" />
      <p style={{ margin: 0 }}>{message}</p>
    </div>
  );
}
