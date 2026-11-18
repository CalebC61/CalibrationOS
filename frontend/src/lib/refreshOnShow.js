import { useEffect } from "react";

/** Refetch when the owner comes back to the tab, the window, or a cached page. */
export function useRefreshOnShow(refresh) {
  useEffect(() => {
    if (typeof refresh !== "function") return undefined;
    function onShow() { refresh(); }
    function onVisible() {
      if (document.visibilityState === "visible") refresh();
    }
    window.addEventListener("focus", onShow);
    window.addEventListener("pageshow", onShow);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", onShow);
      window.removeEventListener("pageshow", onShow);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);
}
