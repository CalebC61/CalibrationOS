import { render, screen } from "@testing-library/react";

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Link: ({ children, to, ...rest }) => React.createElement("a", { href: to, ...rest }, children),
    useNavigate: () => () => {},
  };
}, { virtual: true });

jest.mock("../components/Shell", () => ({ children }) => <div>{children}</div>);
jest.mock("../lib/api", () => ({ api: { get: jest.fn() } }));

import ShopsList from "./ShopsList";
import { api } from "../lib/api";

test("the shop list shows the wholesale card, not the unused tier", async () => {
  api.get.mockResolvedValue({ data: [
    {
      id: "preferred",
      name: "Preferred Auto Glass",
      address: "Gilbert, AZ",
      zone: "east",
      status: "active",
      pricing_tier: "standard",
      rate_label: "Preferred: $115 / $75 / $165",
    },
    {
      id: "plain",
      name: "Star Windshield",
      address: "Mesa, AZ",
      zone: "east",
      status: "active",
      pricing_tier: "standard",
      rate_label: "Standard",
    },
  ] });

  render(<ShopsList />);

  expect(await screen.findByTestId("shop-rates-preferred")).toHaveTextContent("Preferred: $115 / $75 / $165");
  expect(screen.getByTestId("shop-rates-plain")).toHaveTextContent("Standard");
  expect(screen.getByRole("columnheader", { name: "Rates" })).toBeInTheDocument();
  expect(screen.queryByRole("columnheader", { name: "Tier" })).not.toBeInTheDocument();
  expect(screen.getByTestId("shop-row-preferred")).not.toHaveTextContent(/^Standard$/);
  expect(screen.getByTestId("shop-row-preferred").textContent).not.toMatch(/\bStandard\b/);
});
