import { useRef, useState } from "react";
import { uploadCsv } from "../api.js";

export default function UploadForm({ onUploaded }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  function pick(selected) {
    setError(null);
    if (selected && !selected.name.toLowerCase().endsWith(".csv")) {
      setError("Please choose a .csv file.");
      setFile(null);
      return;
    }
    setFile(selected || null);
  }

  async function submit(e) {
    e.preventDefault();
    if (!file) {
      setError("Choose a CSV file first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await uploadCsv(file);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded(result.batch_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card upload" onSubmit={submit}>
      <h2>Upload hospitals CSV</h2>
      <p className="muted">
        Header: <code>name,address,phone</code> (phone optional). Max 20 rows.
      </p>

      <label
        className={`dropzone ${dragOver ? "dropzone--over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          pick(e.dataTransfer.files?.[0]);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => pick(e.target.files?.[0])}
          hidden
        />
        {file ? (
          <span className="dropzone__file">{file.name}</span>
        ) : (
          <span className="dropzone__hint">
            Drag &amp; drop a CSV here, or click to browse
          </span>
        )}
      </label>

      {error && <div className="alert alert--error">{error}</div>}

      <button className="btn btn--primary" type="submit" disabled={busy || !file}>
        {busy ? "Uploading…" : "Upload & process"}
      </button>
    </form>
  );
}
