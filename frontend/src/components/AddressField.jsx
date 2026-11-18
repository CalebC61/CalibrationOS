import { useEffect, useRef, useState } from "react";

const VALLEY = { south: 32.9, west: -112.9, north: 33.9, east: -111.4 };

/** One Places lookup per pause, for whatever is in the field when the pause ends. */
const SUGGESTION_PAUSE_MS = 200;

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
  if (typeof text === "string") return text;
  if (typeof text.text === "string") return text.text;
  return "";
}

/**
 * Phoenix Valley address. Suggestions come from the autocomplete data API
 * after a short pause, including when the field already has the shop address.
 * A picked suggestion inside the valley is the confirmed address.
 * Places failures stay a typed input.
 */
export default function AddressField({ value, onChange, onPlace, onPlaces, onBlur, className = "input", id, testId, placeholder, required }) {
  const onChangeRef = useRef(onChange);
  const onPlaceRef = useRef(onPlace);
  const onPlacesRef = useRef(onPlaces);
  const onBlurRef = useRef(onBlur);
  onChangeRef.current = onChange;
  onPlaceRef.current = onPlace;
  onPlacesRef.current = onPlaces;
  onBlurRef.current = onBlur;
  const placesRef = useRef(null);
  const sessionRef = useRef(null);
  const requestRef = useRef(0);
  const readyRef = useRef(false);
  const textRef = useRef(value || "");
  const editedRef = useRef(false);
  const focusRef = useRef(false);
  const pauseRef = useRef(null);
  const flightRef = useRef(false);
  const retryRef = useRef(false);
  const runRef = useRef(async () => {});
  const [ready, setReady] = useState(false);
  const [text, setText] = useState(value || "");
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const key = process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
  const listId = `${id || testId || "address"}-suggestions`;

  function clearPause() {
    if (pauseRef.current) {
      clearTimeout(pauseRef.current);
      pauseRef.current = null;
    }
  }

  function scheduleSuggestions() {
    clearPause();
    pauseRef.current = setTimeout(() => {
      pauseRef.current = null;
      runSuggestions();
    }, SUGGESTION_PAUSE_MS);
  }

  useEffect(() => {
    const next = value || "";
    textRef.current = next;
    setText(next);
  }, [value]);

  useEffect(() => {
    readyRef.current = ready;
  }, [ready]);

  useEffect(() => {
    if (!key) {
      placesRef.current = null;
      readyRef.current = false;
      requestRef.current += 1;
      clearPause();
      setReady(false);
      setSuggestions([]);
      setOpen(false);
      onPlacesRef.current?.(false);
      return undefined;
    }
    let cancelled = false;
    const previousAuthFailure = window.gm_authFailure;

    function fail() {
      placesRef.current = null;
      sessionRef.current = null;
      readyRef.current = false;
      if (!cancelled) {
        setReady(false);
        setSuggestions([]);
        setOpen(false);
        onPlacesRef.current?.(false);
      }
    }

    window.gm_authFailure = () => {
      fail();
      if (typeof previousAuthFailure === "function") previousAuthFailure();
    };

    loadPlacesLibrary(key).then((places) => {
      if (cancelled) return;
      const fetchSuggestions = places?.AutocompleteSuggestion?.fetchAutocompleteSuggestions;
      if (typeof fetchSuggestions !== "function") {
        fail();
        return;
      }
      placesRef.current = places;
      readyRef.current = true;
      setReady(true);
      onPlacesRef.current?.(true);
      if (editedRef.current && String(textRef.current || "").trim() && !pauseRef.current) {
        runRef.current();
      }
    }).catch(() => fail());

    return () => {
      cancelled = true;
      requestRef.current += 1;
      clearPause();
      placesRef.current = null;
      readyRef.current = false;
      window.gm_authFailure = previousAuthFailure;
    };
  }, [key]);

  async function runSuggestions() {
    if (flightRef.current) {
      retryRef.current = true;
      return;
    }
    const places = placesRef.current;
    const fetchSuggestions = places?.AutocompleteSuggestion?.fetchAutocompleteSuggestions;
    const next = textRef.current;
    if (!readyRef.current || typeof fetchSuggestions !== "function") return;
    if (!String(next || "").trim()) {
      requestRef.current += 1;
      setSuggestions([]);
      setOpen(false);
      return;
    }
    const requestId = ++requestRef.current;
    flightRef.current = true;
    retryRef.current = false;
    try {
      const body = {
        input: next,
        includedRegionCodes: ["us"],
        locationRestriction: { ...VALLEY },
      };
      const Token = places.AutocompleteSessionToken;
      if (typeof Token === "function") {
        if (!sessionRef.current) sessionRef.current = new Token();
        body.sessionToken = sessionRef.current;
      }
      const result = await fetchSuggestions(body);
      if (requestId !== requestRef.current || textRef.current !== next) return;
      const rows = (result?.suggestions || []).filter((row) => row?.placePrediction?.toPlace);
      setSuggestions(rows);
      setOpen(rows.length > 0 && focusRef.current);
      setActive(0);
    } catch {
      if (requestId !== requestRef.current || textRef.current !== next) return;
      setSuggestions([]);
      setOpen(false);
    } finally {
      flightRef.current = false;
      const retry = retryRef.current || textRef.current !== next;
      retryRef.current = false;
      if (requestId !== requestRef.current) return;
      if (retry && String(textRef.current || "").trim()) scheduleSuggestions();
    }
  }

  runRef.current = runSuggestions;

  async function choose(suggestion) {
    const prediction = suggestion?.placePrediction;
    const place = prediction?.toPlace ? prediction.toPlace() : null;
    if (!place?.fetchFields) return;
    clearPause();
    requestRef.current += 1;
    setOpen(false);
    try {
      await place.fetchFields({
        fields: ["formattedAddress", "addressComponents", "displayName", "location", "id"],
      });
      const formatted = place.formattedAddress || "";
      const street = postalAddressFromPlace(place) || formatted;
      const lat = coord(place.location?.lat);
      const lng = coord(place.location?.lng);
      if (!street || lat == null || lng == null) return;
      sessionRef.current = null;
      textRef.current = street;
      setText(street);
      onChangeRef.current?.(street);
      if (!insideValley(lat, lng)) return;
      onPlaceRef.current?.({
        address: street,
        placeId: place.id || null,
        lat,
        lng,
      });
    } catch {
      setSuggestions([]);
      setOpen(false);
    }
  }

  function onKeyDown(event) {
    if (!open || suggestions.length === 0) return;
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => (index + 1) % suggestions.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => (index - 1 + suggestions.length) % suggestions.length);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const suggestion = suggestions[active] || suggestions[0];
      if (suggestion) choose(suggestion);
    }
  }

  const shown = open && suggestions.length > 0;

  return (
    <div className="address-field">
      <input
        id={id}
        className={className}
        value={text}
        required={required}
        placeholder={placeholder}
        autoComplete="off"
        disabled={false}
        aria-autocomplete={ready ? "list" : undefined}
        aria-expanded={ready ? shown : undefined}
        aria-controls={ready ? listId : undefined}
        onFocus={() => {
          focusRef.current = true;
        }}
        onChange={(event) => {
          const next = event.target.value;
          textRef.current = next;
          editedRef.current = true;
          focusRef.current = true;
          setText(next);
          onChangeRef.current?.(next);
          if (!String(next || "").trim()) {
            clearPause();
            requestRef.current += 1;
            setSuggestions([]);
            setOpen(false);
            return;
          }
          scheduleSuggestions();
        }}
        onBlur={(event) => {
          focusRef.current = false;
          setOpen(false);
          onBlurRef.current?.(event.target.value);
        }}
        onKeyDown={onKeyDown}
        data-testid={testId}
        data-address-mode={ready ? "places" : "typed"}
      />
      {shown && (
        <ul id={listId} className="address-suggestions" role="listbox">
          {suggestions.map((suggestion, index) => {
            const label = predictionLabel(suggestion.placePrediction);
            return (
              <li key={`${label}-${index}`} role="presentation">
                <button
                  type="button"
                  role="option"
                  aria-selected={index === active}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(suggestion)}
                >
                  {label}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
