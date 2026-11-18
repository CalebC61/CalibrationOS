import { act, render, screen } from "@testing-library/react";

import AppErrorBoundary, { reportClientError } from "./AppErrorBoundary";

function Boom() {
  throw new Error("render exploded");
}

beforeEach(() => {
  process.env.REACT_APP_BACKEND_URL = "https://api.example.test";
  global.fetch = jest.fn(() => Promise.resolve({ ok: true }));
  jest.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  console.error.mockRestore();
  delete global.fetch;
});

test("renders children while the page is fine", () => {
  render(
    <AppErrorBoundary>
      <p>Dispatch is open</p>
    </AppErrorBoundary>,
  );
  expect(screen.getByText("Dispatch is open")).toBeInTheDocument();
});

test("shows a refresh screen and reports a render error once", () => {
  render(
    <AppErrorBoundary>
      <Boom />
    </AppErrorBoundary>,
  );
  expect(screen.getByRole("heading", { name: /something went wrong/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /refresh/i })).toBeInTheDocument();
  expect(global.fetch).toHaveBeenCalledTimes(1);
  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toBe("https://api.example.test/api/client-errors");
  expect(options.method).toBe("POST");
  expect(options.headers.Authorization).toBeUndefined();
  expect(options.headers["Content-Type"]).toBe("application/json");
  const body = JSON.parse(options.body);
  expect(body.message).toBe("render exploded");
  expect(body.source).toBe("boundary");
  expect(body.path.split("?")[0]).toBe(body.path);
});

test("shows the same screen for a window error and an unhandled rejection", () => {
  const view = render(
    <AppErrorBoundary>
      <p>Still here</p>
    </AppErrorBoundary>,
  );
  act(() => {
    window.dispatchEvent(new ErrorEvent("error", {
      message: "window blew up",
      error: new Error("window blew up"),
    }));
  });
  expect(screen.getByRole("heading", { name: /something went wrong/i })).toBeInTheDocument();
  expect(JSON.parse(global.fetch.mock.calls[0][1].body).source).toBe("window");

  view.unmount();
  global.fetch.mockClear();
  render(
    <AppErrorBoundary>
      <p>Still here</p>
    </AppErrorBoundary>,
  );
  const rejection = new Event("unhandledrejection");
  Object.defineProperty(rejection, "reason", { value: new Error("promise blew up") });
  act(() => {
    window.dispatchEvent(rejection);
  });
  expect(screen.getByRole("heading", { name: /something went wrong/i })).toBeInTheDocument();
  const body = JSON.parse(global.fetch.mock.calls[0][1].body);
  expect(body.source).toBe("unhandledrejection");
  expect(body.message).toBe("promise blew up");
});

test("reportClientError posts the path without the query and never throws", () => {
  reportClientError({
    message: "window blew up",
    stack: "at main",
    source: "window",
    path: "/field?token=secret-token",
  });
  const body = JSON.parse(global.fetch.mock.calls[0][1].body);
  expect(body.path).toBe("/field");
  expect(body.stack).toBe("at main");
  expect(JSON.stringify(body)).not.toContain("secret-token");

  global.fetch.mockImplementation(() => Promise.reject(new Error("offline")));
  expect(() => reportClientError({ message: "again", source: "window" })).not.toThrow();
});
