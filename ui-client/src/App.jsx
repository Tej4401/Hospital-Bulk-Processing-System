import { useCallback, useEffect, useState } from "react";
import { listBatches } from "./api.js";
import UploadForm from "./components/UploadForm.jsx";
import BatchDetail from "./components/BatchDetail.jsx";
import BatchList from "./components/BatchList.jsx";

export default function App() {
  const [activeId, setActiveId] = useState(null);
  const [batches, setBatches] = useState([]);
  const [listError, setListError] = useState(null);

  const refreshList = useCallback(async () => {
    try {
      const data = await listBatches();
      setBatches(data.batches || []);
      setListError(null);
    } catch (err) {
      setListError(err.message);
    }
  }, []);

  useEffect(() => {
    refreshList();
  }, [refreshList]);

  function handleUploaded(batchId) {
    setActiveId(batchId);
    refreshList();
  }

  return (
    <div className="app">
      <header className="app__header">
        <h1>Bulk Hospital Processor</h1>
        <p className="muted">
          Upload a CSV to create and activate hospitals in a single batch.
        </p>
      </header>

      <main className="app__grid">
        <section className="app__left">
          <UploadForm onUploaded={handleUploaded} />
          {listError && <div className="alert alert--error">{listError}</div>}
          <BatchList
            batches={batches}
            activeId={activeId}
            onSelect={setActiveId}
            onRefresh={refreshList}
          />
        </section>

        <section className="app__right">
          {activeId ? (
            <BatchDetail batchId={activeId} onChanged={refreshList} />
          ) : (
            <div className="card empty">
              <p className="muted">
                Select a batch or upload a CSV to see processing details.
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
