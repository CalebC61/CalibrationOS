import { fireEvent, render, screen } from "@testing-library/react";

jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
}), { virtual: true });

jest.mock("../components/PortalShell", () => ({ children }) => <div>{children}</div>);

jest.mock("../lib/api", () => ({
  phoenixTodayStr: () => "2026-11-18",
}));

jest.mock("../lib/portalApi", () => ({
  portalApi: { get: jest.fn(), post: jest.fn() },
}));

import PortalBook from "./PortalBook";
import { portalApi } from "../lib/portalApi";

test("portal booking quotes the shop wholesale card", async () => {
  portalApi.get.mockResolvedValue({
    data: {
      shop: {
        name: "Real Fast Auto Glass",
        address: "1 Shop St, Phoenix, AZ",
        booking_link_token: "tok",
        contact_phone: "4805550100",
        prices: { static: 115, dynamic: 100, dual: 165, triple: 175, tesla: 215 },
      },
      setup: { allowed: true },
    },
  });
  portalApi.post.mockResolvedValue({
    data: { slots: [{ start: "2026-11-18T16:00:00Z" }] },
  });

  render(<PortalBook />);
  fireEvent.change(await screen.findByTestId("b-date"), { target: { value: "2026-11-18" } });
  fireEvent.click(await screen.findByTestId("b-slot-2026-11-18T16:00:00Z"));
  fireEvent.click(screen.getByRole("button", { name: "Continue →" }));

  expect(screen.getByRole("button", { name: /Static ADAS Calibration/ })).toHaveTextContent("$115.00");
  expect(screen.getByRole("button", { name: /Dynamic ADAS Calibration/ })).toHaveTextContent("$100.00");
  expect(screen.getByRole("button", { name: /Dual ADAS Calibration/ })).toHaveTextContent("$165.00");
});
