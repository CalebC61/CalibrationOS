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

function placeResult(fields) {
  return {
    fetchFields: fields.fetchFields || (async () => {}),
    formattedAddress: fields.formattedAddress,
    displayName: fields.displayName,
    id: fields.id,
    location: fields.location,
    addressComponents: fields.addressComponents,
  };
}

function installPlaces(fetchAutocompleteSuggestions) {
  window.google = {
    maps: {
      importLibrary: jest.fn(async () => ({
        AutocompleteSuggestion: { fetchAutocompleteSuggestions },
      })),
    },
  };
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
  expect(screen.queryByRole("listbox")).toBeNull();
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

test("gm_authFailure drops suggestions and keeps a typed input", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const fetchSuggestions = jest.fn(async () => ({ suggestions: [] }));
  installPlaces(fetchSuggestions);
  const { onPlaces } = renderField();
  await waitFor(() => expect(screen.getByTestId("address").getAttribute("data-address-mode")).toBe("places"));

  await act(async () => {
    window.gm_authFailure();
  });
  const typed = await screen.findByTestId("address");
  expect(typed.tagName).toBe("INPUT");
  expect(typed).toBeEnabled();
  expect(typed.getAttribute("data-address-mode")).toBe("typed");
  expect(onPlaces).toHaveBeenCalledWith(false);
});

test("a place details error keeps the typed address and does not confirm it", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const fetchSuggestions = jest.fn(async () => ({
    suggestions: [{
      placePrediction: {
        text: { text: "100 W Guadalupe Rd, Gilbert, AZ" },
        toPlace() {
          return { fetchFields: async () => { throw new Error("places request failed"); } };
        },
      },
    }],
  }));
  installPlaces(fetchSuggestions);
  const { onPlace } = renderField();
  const input = await screen.findByTestId("address");
  await waitFor(() => expect(input.getAttribute("data-address-mode")).toBe("places"));
  fireEvent.change(input, { target: { value: "100 W Guadalupe" } });
  const option = await screen.findByRole("option");
  await act(async () => {
    fireEvent.click(option);
  });
  expect(onPlace).not.toHaveBeenCalled();
  expect(screen.getByTestId("address")).toBeEnabled();
  expect(screen.getByTestId("address").tagName).toBe("INPUT");
  expect(screen.getByTestId("address")).toHaveValue("100 W Guadalupe");
});

test("a picked suggestion sends the place id and formatted address", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const fetchSuggestions = jest.fn(async () => ({
    suggestions: [{
      placePrediction: {
        text: { text: "100 W Guadalupe Rd, Gilbert, AZ 85233, USA" },
        toPlace() {
          return placeResult({
            formattedAddress: "100 W Guadalupe Rd, Gilbert, AZ 85233, USA",
            id: "ChIJ-suggestion",
            location: { lat: () => 33.3528, lng: () => -111.789 },
          });
        },
      },
    }],
  }));
  installPlaces(fetchSuggestions);
  const { onPlace } = renderField();
  const input = await screen.findByTestId("address");
  await waitFor(() => expect(input.getAttribute("data-address-mode")).toBe("places"));
  fireEvent.change(input, { target: { value: "100 W Guadalupe" } });
  expect(fetchSuggestions).toHaveBeenCalledWith(expect.objectContaining({
    input: "100 W Guadalupe",
    includedRegionCodes: ["us"],
    locationRestriction: VALLEY,
  }));
  fireEvent.click(await screen.findByRole("option"));
  await waitFor(() => expect(onPlace).toHaveBeenCalledWith({
    address: "100 W Guadalupe Rd, Gilbert, AZ 85233, USA",
    placeId: "ChIJ-suggestion",
    lat: 33.3528,
    lng: -111.789,
  }));
});

test("an establishment suggestion submits the street, not the business name", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const business = "Downtown Phoenix Inc, 1 E Washington St, Phoenix, AZ 85004, USA";
  const street = "1 E Washington St, Phoenix, AZ 85004, USA";
  const fetchSuggestions = jest.fn(async () => ({
    suggestions: [{
      placePrediction: {
        text: { text: business },
        toPlace() {
          return placeResult({
            formattedAddress: business,
            displayName: { text: "Downtown Phoenix Inc" },
            id: "ChIJdowntown",
            location: { lat: () => 33.4480932, lng: () => -112.0728494 },
            addressComponents: [
              { longText: "Downtown Phoenix Inc", shortText: "Downtown Phoenix Inc", types: ["point_of_interest", "establishment"] },
              { longText: "1", shortText: "1", types: ["street_number"] },
              { longText: "East Washington Street", shortText: "E Washington St", types: ["route"] },
              { longText: "Phoenix", shortText: "Phoenix", types: ["locality", "political"] },
              { longText: "Arizona", shortText: "AZ", types: ["administrative_area_level_1", "political"] },
              { longText: "United States", shortText: "US", types: ["country", "political"] },
              { longText: "85004", shortText: "85004", types: ["postal_code"] },
            ],
          });
        },
      },
    }],
  }));
  installPlaces(fetchSuggestions);
  const { onPlace } = renderField();
  await waitFor(() => expect(screen.getByTestId("address").getAttribute("data-address-mode")).toBe("places"));
  fireEvent.change(screen.getByTestId("address"), { target: { value: "Downtown Phoenix" } });
  fireEvent.click(await screen.findByRole("option"));
  await waitFor(() => expect(onPlace).toHaveBeenCalledWith({
    address: street,
    placeId: "ChIJdowntown",
    lat: 33.4480932,
    lng: -112.0728494,
  }));
  expect(screen.getByTestId("address")).toHaveValue(street);
});

test("a suggestion outside the valley does not confirm the place", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const fetchSuggestions = jest.fn(async () => ({
    suggestions: [{
      placePrediction: {
        text: { text: "1 Main St, New York, NY" },
        toPlace() {
          return placeResult({
            formattedAddress: "1 Main St, New York, NY, USA",
            id: "ChIJnyc",
            location: { lat: () => 40.7, lng: () => -74.0 },
          });
        },
      },
    }],
  }));
  installPlaces(fetchSuggestions);
  const { onChange, onPlace } = renderField();
  await waitFor(() => expect(screen.getByTestId("address").getAttribute("data-address-mode")).toBe("places"));
  fireEvent.change(screen.getByTestId("address"), { target: { value: "1 Main" } });
  onChange.mockClear();
  fireEvent.click(await screen.findByRole("option"));
  await waitFor(() => expect(onChange).toHaveBeenCalledWith("1 Main St, New York, NY, USA"));
  expect(onPlace).not.toHaveBeenCalled();
});

test("editing a prefilled address requests suggestions for the whole new text", async () => {
  process.env.REACT_APP_GOOGLE_MAPS_API_KEY = "test-maps-key";
  const shop = "100 W Main, Gilbert, AZ";
  const edited = "200 Other St, Mesa, AZ";
  const fetchSuggestions = jest.fn(async ({ input }) => ({
    suggestions: [{
      placePrediction: {
        text: { text: `${input}, USA` },
        toPlace() {
          return placeResult({
            formattedAddress: "200 Other St, Mesa, AZ 85201, USA",
            id: "ChIJmesa",
            location: { lat: () => 33.42, lng: () => -111.83 },
          });
        },
      },
    }],
  }));
  installPlaces(fetchSuggestions);
  const { onPlace } = renderField({ value: shop });
  const input = await screen.findByTestId("address");
  await waitFor(() => expect(input.getAttribute("data-address-mode")).toBe("places"));
  expect(input).toHaveValue(shop);
  expect(fetchSuggestions).not.toHaveBeenCalled();

  fireEvent.change(input, { target: { value: edited } });
  const option = await screen.findByRole("option");
  expect(option).toHaveTextContent(edited);
  expect(fetchSuggestions).toHaveBeenCalledWith(expect.objectContaining({ input: edited }));
  expect(fetchSuggestions).not.toHaveBeenCalledWith(expect.objectContaining({ input: shop }));

  fireEvent.click(option);
  await waitFor(() => expect(onPlace).toHaveBeenCalledWith(expect.objectContaining({
    placeId: "ChIJmesa",
    lat: 33.42,
    lng: -111.83,
  })));
});
