// Thin client for the Bulk Hospital Processor API.
//
// The frontend prefers a runtime-configured backend URL if available.
// This avoids client requests going to the frontend host first.
const runtimeApiBase = window.__APP_CONFIG__?.API_BASE || "";
const API_BASE = runtimeApiBase || import.meta.env.VITE_API_BASE_URL || "";

async function handle(res) {
  let body = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { message: text };
    }
  }
  if (!res.ok) {
    const message = (body && body.message) || `Request failed (${res.status})`;
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  return body;
}

export async function uploadCsv(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/hospitals/bulk`, {
    method: "POST",
    body: form,
  });
  return handle(res);
}

export async function getStatus(batchId) {
  const res = await fetch(
    `${API_BASE}/hospitals/bulk/${encodeURIComponent(batchId)}`
  );
  return handle(res);
}

export async function resumeBatch(batchId) {
  const res = await fetch(
    `${API_BASE}/hospitals/bulk/${encodeURIComponent(batchId)}/resume`,
    { method: "POST" }
  );
  return handle(res);
}

export async function listBatches() {
  const res = await fetch(`${API_BASE}/hospitals/batches`);
  return handle(res);
}

// URL of the Server-Sent Events stream for a batch (used with EventSource).
export function eventsUrl(batchId) {
  return `${API_BASE}/hospitals/bulk/${encodeURIComponent(batchId)}/events`;
}

// Status values considered final (stream closes / polling stops).
export const TERMINAL_STATUSES = ["completed", "partially_failed", "failed"];
