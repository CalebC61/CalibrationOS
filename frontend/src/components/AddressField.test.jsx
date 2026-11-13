import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import AddressField, { resetPlacesLoader } from "./AddressField";

const VALLEY = { south: 32.9, west: -112.9, north: 33.9, east: -111.4 };

function renderField(props = {}) {
  const onChange = jest.fn();
  const onPlace = jest.fn();
  const onPlaces = jest.fn();
  render(
    <AddressField
      id="address"
      value=""
      onChange={onChange}
      onPlace={onPlace}
      onPlaces={onPlaces}
      placeholder="Street, city, AZ"
      testId="address"
      required
      {...props}
    />,
  );
  return { onChange, onPlace, onPlaces };
}

beforeEach(() => {
  resetPlacesLoader();
  delete window.google;
  delete window.gm_authFailure;
  delete window.__cosMapsReady;
  document.head.querySelectorAll("script").forEach((node) => {
    if (String(node.src).includes("maps.googleapis.com")) node.remove();
  });
});

afterEach(() => {
  delete process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
});

test("Places errors fall back to an enabled typed address", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  window.google = {
    maps: {
      importLibrary: jest.fn(async () => {
        throw new Error("ApiNotActivatedMapError");
      }),
    },
  };
  const { onChange, onPlaces } = renderField();

  const input = await screen.findByTestId("address");
  await waitFor(() => expect(onPlaces).toHaveBeenCalledWith(false));
  expect(window.google.maps.importLibrary).toHaveBeenCalledWith("places");
  expect(input.tagName).toBe("INPUT");
  expect(input).toBeEnabled();
  expect(input).not.toBeDisabled();
  fireEvent.change(input, { target: { value: "100 W Guadalupe Rd, Gilbert, AZ" } });
  expect(onChange).toHaveBeenCalledWith("100 W Guadalupe Rd, Gilbert, AZ");
  expect(document.querySelector("[data-address-mode='places']")).toBeNull();
});

test("a Maps script error leaves the typed address enabled", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const append = document.head.appendChild.bind(document.head);
  jest.spyOn(document.head, "appendChild").mockImplementation((node) => {
    if (node.tagName === "SCRIPT" && String(node.src).includes("maps.googleapis.com")) {
      expect(node.src).toContain("loading=async");
      expect(node.src).not.toContain("libraries=places");
      queueMicrotask(() => node.onerror(new Event("error")));
      return node;
    }
    return append(node);
  });
  const { onPlaces } = renderField();
  const input = await screen.findByTestId("address");
  await waitFor(() => expect(onPlaces).toHaveBeenCalledWith(false));
  expect(input).toBeEnabled();
  expect(input.tagName).toBe("INPUT");
  document.head.appendChild.mockRestore();
});

test("gm_authFailure and gmp-error drop the widget and keep a typed input", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  function FakeAutocomplete(options) {
    const el = document.createElement("div");
    el.dataset.options = JSON.stringify(options);
    return el;
  }
  window.google = {
    maps: {
      importLibrary: jest.fn(async () => ({ PlaceAutocompleteElement: FakeAutocomplete })),
    },
  };
  const { onPlaces } = renderField();
  await waitFor(() => expect(screen.getByTestId("address").getAttribute("data-address-mode")).toBe("places"));
  const widget = screen.getByTestId("address");
  expect(JSON.parse(widget.dataset.options).includedRegionCodes).toEqual(["us"]);
  expect(JSON.parse(widget.dataset.options).locationRestriction).toEqual(VALLEY);

  await act(async () => {
    window.gm_authFailure();
  });
  const typed = await screen.findByTestId("address");
  expect(typed.tagName).toBe("INPUT");
  expect(typed).toBeEnabled();
  expect(onPlaces).toHaveBeenCalledWith(false);
});

test("a Places request error drops the widget and keeps a typed input", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  function FakeAutocomplete() {
    return document.createElement("div");
  }
  window.google = {
    maps: {
      importLibrary: jest.fn(async () => ({ PlaceAutocompleteElement: FakeAutocomplete })),
    },
  };
  renderField();
  await waitFor(() => expect(screen.getByTestId("address").getAttribute("data-address-mode")).toBe("places"));
  await act(async () => {
    screen.getByTestId("address").dispatchEvent(new Event("gmp-error"));
  });
  const typed = await screen.findByTestId("address");
  expect(typed.tagName).toBe("INPUT");
  expect(typed).toBeEnabled();
});

test("a picked suggestion sends the place id and formatted address", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  function FakeAutocomplete() {
    return document.createElement("div");
  }
  window.google = {
    maps: {
      importLibrary: jest.fn(async () => ({ PlaceAutocompleteElement: FakeAutocomplete })),
    },
  };
  const { onPlace } = renderField();
  await waitFor(() => expect(screen.getByTestId("address").getAttribute("data-address-mode")).toBe("places"));
  const widget = screen.getByTestId("address");
  const event = new Event("gmp-select");
  event.placePrediction = {
    toPlace() {
      return {
        fetchFields: async () => {},
        formattedAddress: "100 W Guadalupe Rd, Gilbert, AZ 85233, USA",
        id: "ChIJ-suggestion",
        location: { lat: () => 33.3528, lng: () => -111.789 },
      };
    },
  };
  widget.dispatchEvent(event);
  await waitFor(() => expect(onPlace).toHaveBeenCalledWith({
    address: "100 W Guadalupe Rd, Gilbert, AZ 85233, USA",
    placeId: "ChIJ-suggestion",
    lat: 33.3528,
    lng: -111.789,
  }));
});
