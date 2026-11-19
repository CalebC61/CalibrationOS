export default function SectionSwitch({ label, options, value, onChange, testIdPrefix = "section" }) {
  return (
    <div role="tablist" aria-label={label} className="section-switch">
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          role="tab"
          aria-selected={value === opt.id}
          className={"tab-btn" + (value === opt.id ? " active" : "")}
          data-testid={`${testIdPrefix}-${opt.id}`}
          onClick={() => onChange(opt.id)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
