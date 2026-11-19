import { useEffect, useRef, useState } from "react";

export function sectionFromLocation(allowed, fallback) {
  const value = new URLSearchParams(window.location.search).get("section");
  return allowed.includes(value) ? value : fallback;
}

/**
 * Remember which panel is open in the query string so a redirect can land on it.
 * `readLocation` wins when a page has an extra rule (the Xero return flag).
 */
export function useOwnerSection(path, allowed, fallback, readLocation = null) {
  const readRef = useRef(readLocation);
  readRef.current = readLocation;
  const [section, setSection] = useState(() => (
    readLocation ? readLocation() : sectionFromLocation(allowed, fallback)
  ));

  useEffect(() => {
    function sync() {
      const read = readRef.current;
      setSection(read ? read() : sectionFromLocation(allowed, fallback));
    }
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [allowed, fallback]);

  function choose(next) {
    if (!allowed.includes(next)) return;
    setSection(next);
    const url = next === fallback ? path : `${path}?section=${encodeURIComponent(next)}`;
    const current = `${window.location.pathname}${window.location.search}`;
    if (current !== url) window.history.pushState({}, "", url);
  }

  return [section, choose];
}
