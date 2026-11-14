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

const UNIT_LABEL = /^(?:#\s*\S+|(?:suite|ste|apt|apartment|unit|bldg|building|floor|fl|room|rm)\b.*|\d+[a-z]?)$/i;
const PO_BOX = /^p\.?\s*o\.?\s*box\b/i;

function componentText(component, short) {
  if (!component) return "";
  const value = short
    ? (component.shortText || component.short_name || component.longText || component.long_name)
    : (component.longText || component.long_name || component.shortText || component.short_name);
  return String(value || "").trim();
}

function findComponent(components, type) {
  return (components || []).find((component) => (component.types || []).includes(type)) || null;
}

function isUnitLabel(value) {
  return UNIT_LABEL.test(String(value || "").trim());
}

/** Drop a leading business name. Keep a unit, a PO box, and a line that already starts with the street number. */
export function streetLine(address) {
  const parts = String(address || "").split(",").map((part) => part.trim()).filter(Boolean);
  if (!parts.length) return "";
  const streetAt = parts.findIndex((part) => /^\d/.test(part));
  if (streetAt <= 0) return parts.join(", ");
  const kept = parts.slice(0, streetAt).filter((part) => /^\d/.test(part) || isUnitLabel(part) || PO_BOX.test(part));
  return [...kept, ...parts.slice(streetAt)].join(", ");
}

/** Street, city, state, and ZIP. The establishment name on a Places result is not part of the address. */
export function postalAddressFromPlace(place) {
  const components = place?.addressComponents || place?.address_components || [];
  const number = componentText(findComponent(components, "street_number"));
  const route = componentText(findComponent(components, "route"), true);
  let street = [number, route].filter(Boolean).join(" ").trim();
  if (street) {
    const unit = componentText(findComponent(components, "subpremise"));
    if (unit && isUnitLabel(unit)) street = `${street} ${unit}`.trim();
    const city = componentText(findComponent(components, "locality"))
      || componentText(findComponent(components, "postal_town"))
      || componentText(findComponent(components, "sublocality"));
    const state = componentText(findComponent(components, "administrative_area_level_1"), true);
    const zip = componentText(findComponent(components, "postal_code"));
    const region = [state, zip].filter(Boolean).join(" ");
    const cityLine = [city, region].filter(Boolean).join(", ");
    let country = componentText(findComponent(components, "country"), true);
    if (country === "US" || country === "USA") country = "USA";
    return [street, cityLine, country].filter(Boolean).join(", ");
  }
  const formatted = place?.formattedAddress || place?.formatted_address || "";
  const name = place?.displayName;
  const label = (typeof name === "string" ? name : name?.text || "").trim();
  if (label && formatted.toLowerCase().startsWith(label.toLowerCase())) {
    const stripped = formatted.slice(label.length).replace(/^[\s,]+/, "");
    if (stripped) return streetLine(stripped) || stripped;
  }
  return streetLine(formatted) || formatted;
}

function predictionLabel(prediction) {
  const text = prediction?.text;
  if (!text) return "";
  return typeof text === "string" ? text : (text.text || "");
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
      let echoed = new Set();
      let restoring = false;

      element.addEventListener("input", () => {
        const text = element.value || "";
        if (picked && text === picked) return;
        if (picked && echoed.has(text)) {
          if (!restoring && element.value !== picked) {
            restoring = true;
            element.value = picked;
            restoring = false;
          }
          return;
        }
        picked = "";
        echoed = new Set();
        onChangeRef.current?.(text);
      });
      element.addEventListener("gmp-error", () => fail());
      element.addEventListener("gmp-select", async (event) => {
        try {
          const prediction = event.placePrediction || event.detail?.placePrediction;
          const place = prediction?.toPlace ? prediction.toPlace() : null;
          if (!place?.fetchFields) return;
          await place.fetchFields({
            fields: ["formattedAddress", "addressComponents", "displayName", "location", "id"],
          });
          const formatted = place.formattedAddress || "";
          const street = postalAddressFromPlace(place) || formatted;
          const lat = coord(place.location?.lat);
          const lng = coord(place.location?.lng);
          if (!street || lat == null || lng == null) return;
          picked = street;
          echoed = new Set([formatted, predictionLabel(prediction), element.value].filter(Boolean));
          if (element.value !== street) element.value = street;
          if (!insideValley(lat, lng)) {
            onChangeRef.current?.(street);
            return;
          }
          onPlaceRef.current?.({
            address: street,
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
