/** Short sections of the shop service agreement. Headings come from the server. */
export default function AgreementView({ sections, paragraphs }) {
  const items = (sections && sections.length)
    ? sections
    : (paragraphs || []).map((body) => ({ heading: "", body }));
  return (
    <div data-testid="terms-text">
      {items.map((section) => (
        <section key={section.heading || section.body} style={{ marginBottom: 16 }}>
          {section.heading && (
            <h3 className="h3" style={{ fontSize: "1rem", marginBottom: 6 }}>{section.heading}</h3>
          )}
          <p style={{ margin: 0, lineHeight: 1.55 }}>{section.body}</p>
        </section>
      ))}
    </div>
  );
}
