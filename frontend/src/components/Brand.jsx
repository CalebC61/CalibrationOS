/**
 * Brand wordmark — mirrors The Calibration Crew logo treatment.
 * "CALIBRATION" in orange stencil + "OS" in solid orange block.
 * Sizes via inline fontSize on the outer span.
 */
export default function Brand({ size = 22, subtle, tag }) {
  return (
    <span className="brand-mark" style={{ fontSize: size }} aria-label="CalibrationOS">
      <span className="brand-word">CALIBRATION</span>
      <span className="brand-suffix">OS</span>
      {tag && (
        <span style={{
          marginLeft: 12,
          fontFamily: "'DM Sans', sans-serif",
          fontSize: Math.max(10, size * 0.45),
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
          fontWeight: 600,
        }}>{tag}</span>
      )}
      {subtle && (
        <span style={{
          marginLeft: 10,
          fontFamily: "'DM Sans', sans-serif",
          fontSize: Math.max(9, size * 0.42),
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--text-subtle)",
          fontWeight: 500,
        }}>by The Calibration Crew</span>
      )}
    </span>
  );
}
