let freshRead = 0;

/** A new query value on every GET so the browser cannot reuse a cached response. */
export function freshParams(params) {
  freshRead += 1;
  const base = params && typeof params === "object" ? params : {};
  return { ...base, _: freshRead };
}
