import Shell from "./Shell";

export default function OwnerPage({ bare = false, children }) {
  if (bare) return children;
  return <Shell>{children}</Shell>;
}

export function OwnerTitle({ bare = false, children, style }) {
  if (bare) return <h2 className="h2" style={style}>{children}</h2>;
  return <h1 className="h1" style={style}>{children}</h1>;
}
