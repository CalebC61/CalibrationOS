import { render, screen } from "@testing-library/react";

jest.mock("../components/PortalShell", () => ({ children }) => children);
jest.mock("../components/AgreementView", () => () => null);
jest.mock("../components/CardSetup", () => ({
  CardSetup: () => null,
  ChargeAcceptance: () => null,
  CHARGE_ACCEPTANCE_FALLBACK: "Accept the card charge.",
}));
jest.mock("../lib/portalApi", () => ({
  portalApi: { get: jest.fn(), post: jest.fn() },
  getPortalAuth: () => null,
  setPortalAuth: jest.fn(),
}));

import PortalSettings from "./PortalSettings";
import { portalApi } from "../lib/portalApi";

function me(shopUser) {
  portalApi.get.mockImplementation((url) => {
    if (String(url).includes("agreement")) {
      return Promise.resolve({ data: { sections: [], paragraphs: [] } });
    }
    return Promise.resolve({
      data: {
        shop_user: shopUser,
        shop: { name: "Jarvis Glass" },
        setup: { allowed: true },
      },
    });
  });
  return render(<PortalSettings />);
}

test("a card on file shows from has_payment_method, not the Stripe id", async () => {
  me({
    full_name: "Ada Glass",
    email: "ada@jarvis.example",
    shop_name: "Jarvis Glass",
    has_payment_method: true,
    card_brand: "visa",
    card_last4: "4242",
    card_exp_month: 12,
    card_exp_year: 2099,
    terms_signed_at: "2026-01-01T00:00:00+00:00",
    terms_signature: "Ada Glass",
  });
  expect(await screen.findByText(/visa/i)).toBeInTheDocument();
  expect(screen.getByText(/4242/)).toBeInTheDocument();
  expect(screen.getByTestId("update-card-btn")).toBeInTheDocument();
  expect(screen.queryByTestId("add-card-btn")).not.toBeInTheDocument();
});

test("a Stripe payment method id alone does not count as a card on file", async () => {
  me({
    full_name: "Ada Glass",
    email: "ada@jarvis.example",
    shop_name: "Jarvis Glass",
    has_payment_method: false,
    stripe_payment_method_id: "pm_should_not_render",
  });
  expect(await screen.findByText("No card on file yet.")).toBeInTheDocument();
  expect(screen.getByTestId("add-card-btn")).toBeInTheDocument();
  expect(screen.queryByText(/pm_should_not_render/)).not.toBeInTheDocument();
});
