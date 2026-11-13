import { useEffect, useRef, useState } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements, PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { portalApi } from "../lib/portalApi";

const publishable = process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY || "";
const livePublishable = publishable.startsWith("pk_live_");
const stripePromise = publishable && !livePublishable ? loadStripe(publishable) : null;

const STRIPE_COPY = {
  setup_intent_unexpected_state: "That card is already saved. Submit again to finish creating the shop.",
  card_declined: "That card was declined. Try a different card.",
  expired_card: "That card is expired. Try a different card.",
  incorrect_cvc: "The security code doesn't match. Check it and try again.",
  incorrect_number: "That card number doesn't look right.",
  incomplete_number: "Enter the full card number.",
  incomplete_cvc: "Enter the card's security code.",
  incomplete_expiry: "Enter the expiration date.",
  processing_error: "The bank couldn't process that card. Try again in a moment.",
  setup_intent_authentication_failure: "The bank didn't approve that card. Try again or use a different card.",
  payment_intent_authentication_failure: "The bank didn't approve that card. Try again or use a different card.",
};

const OPAQUE_STRIPE = /processing error occurred/i;

export const SIGNUP_CARD_ELEMENT_OPTIONS = {
  wallets: { applePay: "never", googlePay: "never", link: "never" },
};

export function paymentMethodId(paymentMethod) {
  if (!paymentMethod) return "";
  if (typeof paymentMethod === "string") return paymentMethod;
  return paymentMethod.id || "";
}

export function stripeErrorMessage(error) {
  if (!error) return "Card setup failed. Check the card and try again.";
  const code = error.code || error.decline_code;
  if (code && STRIPE_COPY[code]) return STRIPE_COPY[code];
  if ((error.type === "card_error" || error.type === "validation_error") && error.message && !OPAQUE_STRIPE.test(error.message)) {
    return error.message;
  }
  return "Card setup failed. Check the card and try again.";
}

async function readSucceededPaymentMethod(retrieveSetupIntent) {
  if (!retrieveSetupIntent) return "";
  try {
    const existing = await retrieveSetupIntent();
    if (!existing || existing.error || existing.setupIntent?.status !== "succeeded") return "";
    return paymentMethodId(existing.setupIntent.payment_method);
  } catch {
    return "";
  }
}

export async function resolveSignupPaymentMethod({ savedId, cardEdited, retrieveSetupIntent, confirmSetup }) {
  if (savedId && !cardEdited) return savedId;
  if (!cardEdited) {
    const existingId = await readSucceededPaymentMethod(retrieveSetupIntent);
    if (existingId) return existingId;
  }
  const result = await confirmSetup();
  if (result?.error) {
    if (result.error.code === "setup_intent_unexpected_state") {
      if (cardEdited) {
        throw new Error("You changed the card after it was saved. Reload the page and enter the card again.");
      }
      const existingId = await readSucceededPaymentMethod(retrieveSetupIntent);
      if (existingId) return existingId;
    }
    throw new Error(stripeErrorMessage(result.error));
  }
  const id = paymentMethodId(result?.setupIntent?.payment_method);
  if (!id) throw new Error("Stripe did not return a card.");
  return id;
}

function CardFields({ bindRef, returnUrl, clientSecret }) {
  const stripe = useStripe();
  const elements = useElements();
  const savedPaymentMethod = useRef("");
  const cardEdited = useRef(false);
  const confirming = useRef(false);

  function onCardChange(event) {
    if (confirming.current || !savedPaymentMethod.current) return;
    if (event && event.complete !== false) return;
    savedPaymentMethod.current = "";
    cardEdited.current = true;
  }

  useEffect(() => {
    if (!bindRef) return undefined;
    bindRef.current = async () => {
      if (!stripe || !elements) throw new Error("Card form is still loading.");
      confirming.current = true;
      try {
        const id = await resolveSignupPaymentMethod({
          savedId: cardEdited.current ? "" : savedPaymentMethod.current,
          cardEdited: cardEdited.current,
          retrieveSetupIntent: clientSecret && stripe.retrieveSetupIntent
            ? () => stripe.retrieveSetupIntent(clientSecret)
            : null,
          confirmSetup: () => stripe.confirmSetup({
            elements,
            redirect: "if_required",
            confirmParams: { return_url: returnUrl || (window.location.origin + "/signup") },
          }),
        });
        savedPaymentMethod.current = id;
        cardEdited.current = false;
        return id;
      } finally {
        confirming.current = false;
      }
    };
    return () => { bindRef.current = null; };
  }, [stripe, elements, bindRef, returnUrl, clientSecret]);
  return <PaymentElement options={SIGNUP_CARD_ELEMENT_OPTIONS} onChange={onCardChange} />;
}

function SetupForm({ onSaved }) {
  const stripe = useStripe();
  const elements = useElements();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!stripe || !elements) return;
    setBusy(true);
    setError("");
    const result = await stripe.confirmSetup({
      elements,
      redirect: "if_required",
      confirmParams: { return_url: window.location.origin + "/portal/setup-return" },
    });
    if (result.error) {
      setError(stripeErrorMessage(result.error));
      setBusy(false);
      return;
    }
    const paymentMethod = result.setupIntent?.payment_method;
    if (!paymentMethod) {
      setError("Stripe did not return a card.");
      setBusy(false);
      return;
    }
    try {
      const { data } = await portalApi.post("/portal/payment-method", {
        payment_method_id: typeof paymentMethod === "string" ? paymentMethod : paymentMethod.id,
      });
      onSaved(data.shop_user);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save the card.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <PaymentElement />
      {error && <div style={{ color: "var(--red)", fontSize: 13, marginTop: 12 }}>{error}</div>}
      <button className="btn btn-primary" style={{ width: "100%", marginTop: 16 }} disabled={!stripe || busy} data-testid="save-card">
        {busy ? "Saving…" : "Save card"}
      </button>
    </form>
  );
}

export function CardSetup({ clientSecret, onSaved, bindRef, returnUrl }) {
  if (livePublishable) {
    return (
      <p className="muted" style={{ fontSize: 14 }} data-testid="stripe-live-blocked">
        This site is using a live Stripe key. Use a pk_test_ key until you turn billing on.
      </p>
    );
  }
  if (!stripePromise || !clientSecret) {
    return (
      <p className="muted" style={{ fontSize: 14 }}>
        Card setup needs a Stripe test publishable key (REACT_APP_STRIPE_PUBLISHABLE_KEY) and a test secret key on the API.
      </p>
    );
  }
  return (
    <Elements stripe={stripePromise} options={{
      clientSecret,
      appearance: { theme: "night", variables: { colorPrimary: "#FF5F1F", colorBackground: "#404653", colorText: "#F5F5F5" } },
    }}>
      {bindRef ? <CardFields bindRef={bindRef} returnUrl={returnUrl} clientSecret={clientSecret} /> : <SetupForm onSaved={onSaved} />}
    </Elements>
  );
}

export function ChargeAcceptance({ text, busy, onAccept }) {
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="charge-title"
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.72)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16, zIndex: 40 }}>
      <div className="surface" style={{ maxWidth: 480, padding: 24 }}>
        <h2 id="charge-title" className="h2" style={{ marginBottom: 12 }}>Before you finish</h2>
        <p style={{ lineHeight: 1.55 }}>{text}</p>
        <button className="btn btn-primary" style={{ width: "100%", marginTop: 16 }} disabled={busy} onClick={onAccept} data-testid="accept-charge">
          {busy ? "Saving…" : "I understand"}
        </button>
      </div>
    </div>
  );
}

export const CHARGE_ACCEPTANCE_FALLBACK = "You understand that after each job is completed, you authorize The Calibration Crew to charge this card, unless you asked beforehand to be invoiced, in which case you have 7 days to pay before a one-time $25 late fee. A $30 trip fee may be added when the address is outside our service area, or charged instead of the calibration price when we cannot calibrate because of a bad installation or because of the customer or the vehicle.";
