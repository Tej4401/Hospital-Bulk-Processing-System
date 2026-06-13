import { useCallback, useEffect, useRef, useState } from "react";
import {
  eventsUrl,
  getStatus,
  resumeBatch,
  TERMINAL_STATUSES,
} from "../api.js";
import StatusBadge from "./StatusBadge.jsx";

const POLL_INTERVAL_MS = 2000;

function isTerminal(status) {
  return TERMINAL_STATUSES.includes(status);
}

export default function BatchDetail({ batchId, onChanged }) {
  const [batch, setBatch] = useState(null);
  const [error, setError] = useState(null);
  const [resuming, setResuming] = useState(false);
  // "live" = receiving SSE; "polling" = fallback; "idle" = finished/unknown.
  const [mode, setMode] = useState("idle");
  // Bumped to restart the realtime connection (e.g. after a resume).
  const [reloadKey, setReloadKey] = useState(0);

  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;

  const refresh = useCallback(async () => {
    try {
      const data = await getStatus(batchId);
      setBatch(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }, [batchId]);

  // Establish a realtime connection (SSE) with an automatic polling fallback.
  useEffect(() => {
    let cancelled = false;
    let es = null;
    let pollTimer = null;
    let finished = false;

    setBatch(null);
    setError(null);

    const notifyChanged = () => onChangedRef.current && onChangedRef.current();

    function startPolling() {
      if (cancelled || finished) return;
      setMode("polling");
      const loop = async () => {
        const data = await refresh();
        if (cancelled) return;
        if (data && !isTerminal(data.status)) {
          pollTimer = setTimeout(loop, POLL_INTERVAL_MS);
        } else {
          finished = true;
          setMode("idle");
          notifyChanged();
        }
      };
      loop();
    }

    // Seed initial state immediately, then prefer SSE for live updates.
    refresh();

    if (typeof EventSource !== "undefined") {
      try {
        es = new EventSource(eventsUrl(batchId));
        es.onopen = () => !cancelled && setMode("live");
        es.onmessage = (e) => {
          if (cancelled) return;
          try {
            const payload = JSON.parse(e.data);
            if (payload.batch) setBatch(payload.batch);
            if (payload.type === "done") {
              finished = true;
              setMode("idle");
              es.close();
              notifyChanged();
            }
          } catch {
            /* ignore keep-alive / malformed frames */
          }
        };
        es.onerror = () => {
          // Server closed after "done", or the connection failed. Only fall
          // back to polling if we're not already finished.
          if (es) es.close();
          es = null;
          if (!finished && !cancelled) startPolling();
        };
      } catch {
        startPolling();
      }
    } else {
      startPolling();
    }

    return () => {
      cancelled = true;
      if (es) es.close();
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [batchId, reloadKey, refresh]);

  async function doResume() {
    setResuming(true);
    try {
      await resumeBatch(batchId);
      await refresh();
      // Re-open the realtime stream to follow the resumed run.
      setReloadKey((k) => k + 1);
    } catch (err) {
      setError(err.message);
    } finally {
      setResuming(false);
    }
  }

  if (error && !batch) {
    return (
      <div className="card">
        <div className="alert alert--error">{error}</div>
      </div>
    );
  }

  if (!batch) {
    return (
      <div className="card">
        <p className="muted">Loading batch…</p>
      </div>
    );
  }

  const total = batch.total_hospitals || 0;
  const processed = batch.processed_hospitals || 0;
  const failed = batch.failed_hospitals || 0;
  const pct = total ? Math.round(((processed + failed) / total) * 100) : 0;
  const terminal = isTerminal(batch.status);
  const canResume = batch.status !== "completed";

  return (
    <div className="card">
      <div className="batch__header">
        <div>
          <h2>Batch status</h2>
          <code className="batch__id">{batch.batch_id}</code>
        </div>
        <StatusBadge status={batch.status} />
      </div>

      <div className="progress">
        <div className="progress__bar" style={{ width: `${pct}%` }} />
      </div>
      <div className="stats">
        <Stat label="Total" value={total} />
        <Stat label="Processed" value={processed} tone="ok" />
        <Stat label="Failed" value={failed} tone={failed ? "err" : undefined} />
        <Stat
          label="Activated"
          value={batch.batch_activated ? "Yes" : "No"}
          tone={batch.batch_activated ? "ok" : undefined}
        />
        <Stat
          label="Time (s)"
          value={
            batch.processing_time_seconds != null
              ? batch.processing_time_seconds
              : "—"
          }
        />
      </div>

      {batch.error && <div className="alert alert--error">{batch.error}</div>}

      <div className="batch__actions">
        <span className="live">
          {!terminal && (
            <>
              <span
                className={`live__dot ${
                  mode === "live" ? "live__dot--live" : "live__dot--poll"
                }`}
              />
              {mode === "live"
                ? "Live (SSE)"
                : mode === "polling"
                ? "Live (polling)"
                : "Connecting…"}
            </>
          )}
        </span>
        {canResume && (
          <button
            className="btn"
            onClick={doResume}
            disabled={resuming || !terminal}
            title={
              terminal
                ? "Retry failed rows and re-attempt activation"
                : "Wait for processing to finish before resuming"
            }
          >
            {resuming ? "Resuming…" : "Resume"}
          </button>
        )}
      </div>

      <table className="rows">
        <thead>
          <tr>
            <th>#</th>
            <th>Name</th>
            <th>Hospital ID</th>
            <th>Status</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {(batch.hospitals || []).map((h) => (
            <tr key={h.row}>
              <td>{h.row}</td>
              <td>{h.name}</td>
              <td>{h.hospital_id ?? "—"}</td>
              <td>
                <StatusBadge status={h.status} />
              </td>
              <td className="rows__error">{h.error || ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <span className={`stat__value ${tone ? `stat__value--${tone}` : ""}`}>
        {value}
      </span>
    </div>
  );
}
