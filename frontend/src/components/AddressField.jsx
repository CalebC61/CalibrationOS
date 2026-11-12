import { useEffect, useRef } from "react";

const VALLEY = { south: 32.9, west: -112.9, north: 33.9, east: -111.4 };

let placesPromise = null;

function loadPlaces(key) {
  if (window.google?.maps?.places) return Promise.resolve();
  if (!placesPromise) {
    placesPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&libraries=places`;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Places failed to load"));
      document.head.appendChild(script);
    });
  }
  return placesPromise;
}

/** Google Places autocomplete limited to the Phoenix Valley. */
export default function AddressField({ value, onChange, onPlace, className = "input", id, testId, placeholder, required }) {
  const ref = useRef(null);
  const onPlaceRef = useRef(onPlace);
  onPlaceRef.current = onPlace;
  const key = process.env.REACT_APP_GOOGLE_MAPS_API_KEY;

  useEffect(() => {
    if (!key || !ref.current) return undefined;
    let autocomplete;
    let cancelled = false;
    loadPlaces(key).then(() => {
      if (cancelled || !ref.current || !window.google?.maps?.places) return;
      const bounds = new window.google.maps.LatLngBounds(
        new window.google.maps.LatLng(VALLEY.south, VALLEY.west),
        new window.google.maps.LatLng(VALLEY.north, VALLEY.east),
      );
      autocomplete = new window.google.maps.places.Autocomplete(ref.current, {
        bounds,
        strictBounds: true,
        componentRestrictions: { country: "us" },
        fields: ["formatted_address", "geometry", "place_id"],
      });
      autocomplete.addListener("place_changed", () => {
        const place = autocomplete.getPlace();
        const loc = place.geometry?.location;
        if (!place.formatted_address || !loc) return;
        const lat = loc.lat();
        const lng = loc.lng();
        const inside = lat > VALLEY.south && lat < VALLEY.north && lng > VALLEY.west && lng < VALLEY.east;
        if (!inside) return;
        onPlaceRef.current({
          address: place.formatted_address,
          placeId: place.place_id || null,
          lat,
          lng,
        });
      });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [key]);

  return (
    <input
      ref={ref}
      id={id}
      className={className}
      value={value}
      required={required}
      placeholder={placeholder}
      autoComplete="off"
      onChange={e => onChange(e.target.value)}
      data-testid={testId}
    />
  );
}
