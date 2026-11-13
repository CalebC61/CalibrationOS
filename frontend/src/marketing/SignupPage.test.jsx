import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import SignupPage from "./SignupPage";
import * as stripe from "@stripe/react-stripe-js";

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Link: ({ children, to }) => React.createElement("a", { href: to }, children),
    NavLink: ({ children, to, className }) => {
      const cls = typeof className === "function" ? className({ isActive: false }) : className;
      return React.createElement("a", { href: to, className: cls }, children);
    },
    useLocation: () => ({ pathname: "/signup", hash: "", search: "" }),
    useNavigate: () => jest.fn(),
  };
}, { virtual: true });

jest.mock("axios", () => {
  const instance = {
    get: jest.fn(),
    post: jest.fn(),
    interceptors: { request: { use: jest.fn() } },
  };
  return {
    __esModule: true,
    default: {
      get: jest.fn(),
      post: jest.fn(),
      create: jest.fn(() => instance),
    },
  };
});

jest.mock("@stripe/stripe-js", () => ({
  loadStripe: jest.fn(() => Promise.resolve({})),
}));

jest.mock("@stripe/react-stripe-js", () => {
  const React = require("react");
  const confirmSetup = jest.fn();
  const retrieveSetupIntent = jest.fn();
  return {
    Elements: ({ children }) => React.createElement("div", { "data-testid": "stripe-elements" }, children),
    PaymentElement: (props) => React.createElement("div", {
      "data-testid": "payment-element",
      "data-options": JSON.stringify(props.options || {}),
    }),
    useStripe: () => ({ confirmSetup, retrieveSetupIntent }),
    useElements: () => ({ ready: true }),
    __mocks: { confirmSetup, retrieveSetupIntent },
  };
});

function fillAccount(email = "ada@jarvis.example") {
  fireEvent.change(screen.getByTestId("signup-shop-name"), { target: { value: "Jarvis Glass" } });
  fireEvent.change(screen.getByTestId("signup-contact-name"), { target: { value: "Ada Glass" } });
  fireEvent.change(screen.getByTestId("signup-mobile"), { target: { value: "4805550100" } });
  fireEvent.change(screen.getByTestId("signup-email"), { target: { value: email } });
  fireEvent.change(screen.getByTestId("signup-password"), { target: { value: "longenough" } });
  fireEvent.change(screen.getByTestId("signup-confirm"), { target: { value: "longenough" } });
  fireEvent.change(screen.getByTestId("signup-address"), { target: { value: "100 W Guadalupe Rd, Gilbert, AZ" } });
  fireEvent.change(screen.getByTestId("signup-signature"), { target: { value: "Ada Glass" } });
  fireEvent.click(screen.getByTestId("signup-agree"));
  fireEvent.click(screen.getByTestId("signup-charge"));
}

test("a duplicate shop does not confirm the card again on retry", async () => {
  const calls = [];
  const shopBodies = [];
  stripe.__mocks.retrieveSetupIntent.mockImplementation(async () => {
    calls.push("retrieve");
    return { setupIntent: { status: "requires_payment_method" } };
  });
  stripe.__mocks.confirmSetup.mockImplementation(async () => {
    calls.push("confirm");
    return { setupIntent: { status: "succeeded", payment_method: "pm_card" } };
  });
  axios.get.mockResolvedValue({
    data: {
      sections: [],
      acceptance: "Charge the card after the job.",
      password_rule: "At least 8 characters.",
      password_min_length: 8,
    },
  });
  axios.post.mockImplementation(async (url, body) => {
    if (String(url).endsWith("/public/card-setup")) {
      calls.push("card-setup");
      return { data: { client_secret: "seti_secret_test", stripe_unavailable: false } };
    }
    if (String(url).endsWith("/public/shops/check")) {
      calls.push("check");
      return { data: { ok: true } };
    }
    if (String(url).endsWith("/public/shops")) {
      calls.push("shops");
      shopBodies.push(body);
      if (shopBodies.length === 1) {
        const error = new Error("duplicate");
        error.response = {
          data: {
            detail: {
              code: "duplicate_email",
              message: "That email already has a shop account. Log in, or reset the password.",
            },
          },
        };
        throw error;
      }
      return {
        data: {
          token: "tok",
          full_name: "Ada Glass",
          shop_name: "Jarvis Glass",
          shop_user_id: "user-1",
          shop_id: "shop-1",
          has_payment_method: true,
        },
      };
    }
    throw new Error(url);
  });

  render(<SignupPage />);

  await screen.findByTestId("payment-element");
  const wallets = JSON.parse(screen.getByTestId("payment-element").getAttribute("data-options")).wallets;
  expect(wallets).toEqual({ applePay: "never", googlePay: "never", link: "never" });
  expect(screen.getByTestId("signup-address-hint").textContent).not.toMatch(/suggestion you pick/i);
  expect(screen.getByTestId("signup-address-hint").textContent).toMatch(/confirm the address we find/i);

  fillAccount();
  fireEvent.click(screen.getByTestId("signup-submit"));
  expect(await screen.findByTestId("signup-error")).toHaveTextContent(/already has a shop account/i);

  fireEvent.change(screen.getByTestId("signup-email"), { target: { value: "new@jarvis.example" } });
  fireEvent.click(screen.getByTestId("signup-submit"));

  await waitFor(() => expect(shopBodies).toHaveLength(2));
  expect(stripe.__mocks.confirmSetup).toHaveBeenCalledTimes(1);
  const confirmIndex = calls.indexOf("confirm");
  expect(calls.slice(0, confirmIndex)).toContain("check");
  expect(calls.indexOf("shops")).toBeGreaterThan(confirmIndex);
  expect(shopBodies[0].payment_method_id).toBe("pm_card");
  expect(shopBodies[1].payment_method_id).toBe("pm_card");
  expect(shopBodies[1].email).toBe("new@jarvis.example");
  expect(calls.filter(name => name === "confirm")).toEqual(["confirm"]);
});

test("shows the password rule and blocks submit until the password passes", async () => {
  axios.get.mockResolvedValue({
    data: {
      sections: [],
      password_rule: "At least 10 characters.",
      password_min_length: 10,
    },
  });
  axios.post.mockResolvedValue({ data: { client_secret: "seti_secret_test" } });

  render(<SignupPage />);

  expect(await screen.findByText("At least 10 characters.")).toBeInTheDocument();
  fireEvent.change(screen.getByTestId("signup-password"), { target: { value: "shortpass" } });
  expect(screen.getByTestId("signup-password-error")).toHaveTextContent("Password must be at least 10 characters.");

  fireEvent.change(screen.getByTestId("signup-shop-name"), { target: { value: "Jarvis Glass" } });
  fireEvent.change(screen.getByTestId("signup-contact-name"), { target: { value: "Ada Glass" } });
  fireEvent.change(screen.getByTestId("signup-mobile"), { target: { value: "4805550100" } });
  fireEvent.change(screen.getByTestId("signup-email"), { target: { value: "ada@jarvis.example" } });
  fireEvent.change(screen.getByTestId("signup-confirm"), { target: { value: "shortpass" } });
  fireEvent.change(screen.getByTestId("signup-address"), { target: { value: "100 W Guadalupe Rd, Gilbert, AZ" } });
  fireEvent.change(screen.getByTestId("signup-signature"), { target: { value: "Ada Glass" } });
  fireEvent.click(screen.getByTestId("signup-agree"));
  fireEvent.click(screen.getByTestId("signup-charge"));
  fireEvent.click(screen.getByTestId("signup-submit"));

  const shopPosts = axios.post.mock.calls.filter(([url]) => String(url).includes("/public/shops"));
  expect(shopPosts).toHaveLength(0);

  fireEvent.change(screen.getByTestId("signup-password"), { target: { value: "longenough1" } });
  expect(screen.queryByTestId("signup-password-error")).not.toBeInTheDocument();
  fireEvent.change(screen.getByTestId("signup-confirm"), { target: { value: "different1" } });
  expect(screen.getByTestId("signup-confirm-error")).toHaveTextContent(/don't match/i);
  fireEvent.click(screen.getByTestId("signup-submit"));
  const shopPostsAfter = axios.post.mock.calls.filter(([url]) => String(url).includes("/public/shops"));
  expect(shopPostsAfter).toHaveLength(0);
});
