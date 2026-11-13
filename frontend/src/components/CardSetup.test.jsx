jest.mock("axios", () => ({
  __esModule: true,
  default: {
    create: () => ({ interceptors: { request: { use: () => {} } } }),
  },
}));

jest.mock("@stripe/stripe-js", () => ({
  loadStripe: () => null,
}));

jest.mock("@stripe/react-stripe-js", () => ({
  Elements: () => null,
  PaymentElement: () => null,
  useElements: () => null,
  useStripe: () => null,
}));

import { resolveSignupPaymentMethod, stripeErrorMessage } from "./CardSetup";

test("maps setup_intent_unexpected_state and other Stripe errors to friendly copy", () => {
  expect(stripeErrorMessage({
    code: "setup_intent_unexpected_state",
    message: "A processing error occurred.",
  })).toBe("That card is already saved. Submit again to finish creating the shop.");
  expect(stripeErrorMessage({ code: "card_declined", message: "Your card was declined." }))
    .toMatch(/declined/i);
  expect(stripeErrorMessage({ code: "expired_card", message: "Your card has expired." }))
    .toMatch(/expired/i);
  expect(stripeErrorMessage({ message: "A processing error occurred." }))
    .toBe("Card setup failed. Check the card and try again.");
});

test("reuses a saved payment method and does not confirm again", async () => {
  const confirmSetup = jest.fn();
  const retrieveSetupIntent = jest.fn();
  const id = await resolveSignupPaymentMethod({
    savedId: "pm_saved",
    cardEdited: false,
    retrieveSetupIntent,
    confirmSetup,
  });
  expect(id).toBe("pm_saved");
  expect(confirmSetup).not.toHaveBeenCalled();
  expect(retrieveSetupIntent).not.toHaveBeenCalled();
});

test("uses a succeeded SetupIntent instead of confirming it again", async () => {
  const confirmSetup = jest.fn();
  const retrieveSetupIntent = jest.fn(async () => ({
    setupIntent: { status: "succeeded", payment_method: { id: "pm_from_intent" } },
  }));
  const id = await resolveSignupPaymentMethod({
    savedId: "",
    cardEdited: false,
    retrieveSetupIntent,
    confirmSetup,
  });
  expect(id).toBe("pm_from_intent");
  expect(confirmSetup).not.toHaveBeenCalled();
});

test("confirms once when the SetupIntent is not succeeded yet", async () => {
  const confirmSetup = jest.fn(async () => ({
    setupIntent: { status: "succeeded", payment_method: "pm_new" },
  }));
  const retrieveSetupIntent = jest.fn(async () => ({
    setupIntent: { status: "requires_payment_method" },
  }));
  const id = await resolveSignupPaymentMethod({
    savedId: "",
    cardEdited: false,
    retrieveSetupIntent,
    confirmSetup,
  });
  expect(id).toBe("pm_new");
  expect(confirmSetup).toHaveBeenCalledTimes(1);
});

test("does not reuse a succeeded card after the shop edits it", async () => {
  const confirmSetup = jest.fn(async () => ({
    error: { code: "setup_intent_unexpected_state", message: "A processing error occurred." },
  }));
  const retrieveSetupIntent = jest.fn(async () => ({
    setupIntent: { status: "succeeded", payment_method: "pm_old" },
  }));
  await expect(resolveSignupPaymentMethod({
    savedId: "",
    cardEdited: true,
    retrieveSetupIntent,
    confirmSetup,
  })).rejects.toThrow(/changed the card/i);
  expect(confirmSetup).toHaveBeenCalledTimes(1);
  expect(retrieveSetupIntent).not.toHaveBeenCalled();
});
