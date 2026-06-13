const LABELS = {
  queued: "Queued",
  processing: "Processing",
  activating: "Activating",
  completed: "Completed",
  partially_failed: "Partially failed",
  failed: "Failed",
  created: "Created",
  created_and_activated: "Active",
  pending: "Pending",
};

export default function StatusBadge({ status }) {
  const key = (status || "").toLowerCase();
  const label = LABELS[key] || status || "unknown";
  return <span className={`badge badge--${key}`}>{label}</span>;
}
