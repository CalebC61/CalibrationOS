import { useEffect, useRef, useState } from "react";

const VALLEY = { south: 32.9, west: -112.9, north: 33.9, east: -111.4 };

let mapsPromise = null;

export function resetPlacesLoader() {
  mapsPromise = null;
}

/** Places API (New). loading=async, then importLibrary("places"). A failed load can be retried. */
export function loadPlacesLibrary(key) {
  if (typeof window.google?.maps?.importLibrary === "function") {
    return window.google.maps.importLibrary("places");
  }
  if (!mapsPromise) {
    mapsPromise = new Promise((resolve, reject) => {
      const params = new URLSearchParams();
      params.set("key", key);
      params.set("v", "weekly");
      params.set("loading", "async");
      params.set("callback", "__cosMapsReady");
      window.__cosMapsReady = () => resolve();
      const script = document.createElement("script");
      script.async = true;
      script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
      script.onerror = () => {
        mapsPromise = null;
        reject(new Error("Maps failed to load"));
      };
      document.head.appendChild(script);
    });
  }
  return mapsPromise.then(() => {
    if (typeof window.google?.maps?.importLibrary !== "function") {
      throw new Error("Maps did not load");
    }
    return window.google.maps.importLibrary("places");
  }).catch((error) => {
    mapsPromise = null;
    throw error;
  });
}

function insideValley(lat, lng) {
  return lat > VALLEY.south && lat < VALLEY.north && lng > VALLEY.west && lng < VALLEY.east;
}

function coord(value) {
  if (typeof value === "function") return value();
  return typeof value === "number" ? value : null;
}

/** Phoenix Valley address. A picked suggestion is the confirmed address. Places failures stay a typed input. */
export default function AddressField({ value, onChange, onPlace, onPlaces, className = "input", id, testId, placeholder, required }) {
  const hostRef = useRef(null);
  const widgetRef = useRef(null);
  const onChangeRef = useRef(onChange);
  const onPlaceRef = useRef(onPlace);
  const onPlacesRef = useRef(onPlaces);
  const valueRef = useRef(value);
  onChangeRef.current = onChange;
  onPlaceRef.current = onPlace;
  onPlacesRef.current = onPlaces;
  valueRef.current = value;
  const [ready, setReady] = useState(false);
  const key = process.env.REACT_APP_GOOGLE_MAPS_API_KEY;

  useEffect(() => {
    if (!key) {
      setReady(false);
      onPlacesRef.current?.(false);
      return undefined;
    }
    let cancelled = false;
    let failed = false;
    let element = null;
    const previousAuthFailure = window.gm_authFailure;

    function fail() {
      failed = true;
      element?.remove();
      element = null;
      widgetRef.current = null;
      if (!cancelled) {
        setReady(false);
        onPlacesRef.current?.(false);
      }
    }

    window.gm_authFailure = () => {
      fail();
      if (typeof previousAuthFailure === "function") previousAuthFailure();
    };

    loadPlacesLibrary(key).then((places) => {
      if (cancelled || failed) return;
      const PlaceAutocompleteElement = places?.PlaceAutocompleteElement;
      if (typeof PlaceAutocompleteElement !== "function" || !hostRef.current) {
        fail();
        return;
      }
      try {
        element = new PlaceAutocompleteElement({
          includedRegionCodes: ["us"],
          locationRestriction: { ...VALLEY },
        });
      } catch {
        fail();
        return;
      }
      element.className = `address-places ${className || ""}`.trim();
      element.placeholder = placeholder || "";
      if (id) element.id = id;
      if (testId) element.setAttribute("data-testid", testId);
      element.setAttribute("data-address-mode", "places");
      if (valueRef.current) element.value = valueRef.current;
      let picked = "";

      element.addEventListener("input", () => {
        const text = element.value || "";
        if (text === picked) return;
        onChangeRef.current?.(text);
      });
      element.addEventListener("gmp-error", () => fail());
      element.addEventListener("gmp-select", async (event) => {
        try {
          const prediction = event.placePrediction || event.detail?.placePrediction;
          const place = prediction?.toPlace ? prediction.toPlace() : null;
          if (!place?.fetchFields) return;
          await place.fetchFields({ fields: ["formattedAddress", "location", "id"] });
          const formatted = place.formattedAddress || "";
          const lat = coord(place.location?.lat);
          const lng = coord(place.location?.lng);
          if (!formatted || lat == null || lng == null) return;
          picked = formatted;
          if (!insideValley(lat, lng)) {
            onChangeRef.current?.(formatted);
            return;
          }
          onPlaceRef.current?.({
            address: formatted,
            placeId: place.id || null,
            lat,
            lng,
          });
        } catch {
          fail();
        }
      });
      hostRef.current.appendChild(element);
      widgetRef.current = element;
      if (cancelled || failed) {
        element.remove();
        return;
      }
      setReady(true);
      onPlacesRef.current?.(true);
    }).catch(() => fail());

    return () => {
      cancelled = true;
      element?.remove();
      widgetRef.current = null;
      window.gm_authFailure = previousAuthFailure;
    };
  }, [key, className, id, placeholder, testId]);

  useEffect(() => {
    const element = widgetRef.current;
    if (!element || element.value === value) return;
    element.value = value || "";
  }, [value, ready]);

  return (
    <div className="address-field">
      <div ref={hostRef} hidden={!ready} />
      {!ready && (
        <input
          id={id}
          className={className}
          value={value}
          required={required}
          placeholder={placeholder}
          autoComplete="off"
          disabled={false}
          onChange={event => onChange(event.target.value)}
          data-testid={testId}
          data-address-mode="typed"
        />
      )}
    </div>
  );
}
