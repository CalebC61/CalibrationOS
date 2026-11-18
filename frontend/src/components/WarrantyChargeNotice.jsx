import { useEffect, useRef } from "react";

/** Shop confirmation before a redo outside the 30-day window is booked or moved. */
export default function WarrantyChargeNotice({ open, onContinue, onCancel }) {
  const cancelRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    cancelRef.current?.focus();
    function onKey(event) {
      if (event.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      onClick={(event) => { event.stopPropagation(); onCancel(); }}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.72)", zIndex: 80,
        display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="warranty-charge-title"
        onClick={(event) => event.stopPropagation()}
        className="surface page-fade"
        style={{ maxWidth: 440, width: "100%", padding: 24 }}
        data-testid="warranty-charge-notice"
      >
        <h2 id="warranty-charge-title" className="h2" style={{ marginBottom: 12 }}>
          30-day warranty has passed
        </h2>
        <p style={{ lineHeight: 1.5, margin: 0 }}>
          The 30-day warranty has passed. This job will be charged at full price.
        </p>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 20 }}>
          <button type="button" className="btn btn-ghost" ref={cancelRef} onClick={onCancel}
            data-testid="warranty-charge-cancel">
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={onContinue}
            data-testid="warranty-charge-continue">
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
