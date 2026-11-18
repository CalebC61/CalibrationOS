import { isFreeWarranty, warrantyText } from "../lib/warranty";

export default function WarrantyBadge({ job }) {
  const text = warrantyText(job);
  if (!text) return null;
  const testId = job.id ? `warranty-badge-${job.id}` : "warranty-badge";
  if (isFreeWarranty(job)) {
    return (
      <div className="warranty-banner" role="status" data-testid={testId}>
        <strong>Warranty</strong>
        <span>{text}. This job is not charged.</span>
      </div>
    );
  }
  return (
    <span
      className="badge badge-draft"
      style={{ fontSize: 12, letterSpacing: "0.02em", textTransform: "none" }}
      data-testid={testId}
    >
      {text}
    </span>
  );
}
