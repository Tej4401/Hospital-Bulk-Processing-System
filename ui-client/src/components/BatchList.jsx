import StatusBadge from "./StatusBadge.jsx";

export default function BatchList({ batches, activeId, onSelect, onRefresh }) {
  return (
    <div className="card">
      <div className="list__header">
        <h2>Recent batches</h2>
        <button className="btn btn--ghost" onClick={onRefresh}>
          Refresh
        </button>
      </div>
      {batches.length === 0 ? (
        <p className="muted">No batches yet. Upload a CSV to get started.</p>
      ) : (
        <ul className="list">
          {batches.map((b) => (
            <li
              key={b.batch_id}
              className={`list__item ${
                b.batch_id === activeId ? "list__item--active" : ""
              }`}
              onClick={() => onSelect(b.batch_id)}
            >
              <div className="list__main">
                <code className="list__id">{b.batch_id.slice(0, 8)}…</code>
                <StatusBadge status={b.status} />
              </div>
              <div className="list__meta muted">
                {b.processed_hospitals}/{b.total_hospitals} processed
                {b.failed_hospitals ? ` · ${b.failed_hospitals} failed` : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
