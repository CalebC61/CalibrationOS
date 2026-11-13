import { useEffect, useState } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements, PaymentElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { portalApi } from "../lib/portalApi";

const publishable = process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY || "";
const livePublishable = publishable.startsWith("pk_live_");
const stripePromise = publishable && !livePublishable ? loadStripe(publishable) : null;

function CardFields({ bindRef, returnUrl }) {
  const stripe = useStripe();
  const elements = useElements();
  useEffect(() => {
    if (!bindRef) return undefined;
    bindRef.current = async () => {
      if (!stripe || !elements) throw new Error("Card form is still loading.");
      const result = await stripe.confirmSetup({
        elements,
        redirect: "if_required",
        confirmParams: { return_url: returnUrl || (window.location.origin + "/signup") },
      });
      if (result.error) throw new Error(result.error.message || "Card setup failed.");
      const paymentMethod = result.setupIntent?.payment_method;
      if (!paymentMethod) throw new Error("Stripe did not return a card.");
      return typeof paymentMethod === "string" ? paymentMethod : paymentMethod.id;
    };
    return () => { bindRef.current = null; };
  }, [stripe, elements, bindRef, returnUrl]);
  return <PaymentElement />;
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
      setError(result.error.message || "Card setup failed.");
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
      {bindRef ? <CardFields bindRef={bindRef} returnUrl={returnUrl} /> : <SetupForm onSaved={onSaved} />}
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
