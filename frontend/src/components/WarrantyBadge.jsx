import { warrantyText } from "../lib/warranty";

export default function WarrantyBadge({ job }) {
  const text = warrantyText(job);
  if (!text) return null;
  const free = Boolean(job.warranty_eligible);
  return (
    <span
      className={"badge " + (free ? "badge-complete" : "badge-draft")}
      style={{ fontSize: 12, letterSpacing: "0.02em", textTransform: "none" }}
      data-testid={job.id ? `warranty-badge-${job.id}` : "warranty-badge"}
    >
      {text}
    </span>
  );
}
