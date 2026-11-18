import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const mockRouter = { nav: jest.fn() };

jest.mock("react-router-dom", () => ({
  Link: ({ children, to }) => <a href={to}>{children}</a>,
  useNavigate: () => mockRouter.nav,
  useParams: () => ({ token: "invite-token" }),
}), { virtual: true });

jest.mock("../components/CardSetup", () => ({
  CardSetup: ({ onSaved }) => (
    <div>
      <button type="button" data-testid="fake-save-accepted" onClick={() => onSaved({ charge_authorization_accepted_at: "2026-11-18T00:00:00+00:00" })}>
        Save accepted
      </button>
      <button type="button" data-testid="fake-save-pending" onClick={() => onSaved({ charge_authorization_accepted_at: null })}>
        Save pending
      </button>
    </div>
  ),
  ChargeAcceptance: ({ text }) => <div data-testid="charge-modal">{text}</div>,
  CHARGE_ACCEPTANCE_FALLBACK: "Fallback charge terms.",
}));

jest.mock("../lib/portalApi", () => ({
  portalApi: { get: jest.fn(), post: jest.fn() },
  setPortalAuth: jest.fn(),
}));

import PortalRegister from "./PortalRegister";
import { portalApi } from "../lib/portalApi";

const TERMS = "You authorize a charge after each completed job.";

beforeEach(() => {
  mockRouter.nav.mockReset();
  portalApi.get.mockImplementation((url) => {
    const path = String(url);
    if (path.includes("/public/site")) return Promise.resolve({ data: { owner_phone: "(480) 269-1329" } });
    if (path.includes("/public/agreement")) return Promise.resolve({ data: { acceptance: TERMS } });
    if (path.includes("/public/invites/")) {
      return Promise.resolve({
        data: {
          shop_name: "Jarvis Glass",
          shop_id: "shop-1",
          recipient_email: "ada@jarvis.example",
          agreement_sections: [{ heading: "How you pay", body: "We charge the card on file." }],
        },
      });
    }
    return Promise.reject(new Error(path));
  });
  portalApi.post.mockResolvedValue({
    data: {
      token: "portal-jwt",
      shop_user_id: "user-1",
      stripe_client_secret: "seti_secret",
    },
  });
});

function fillAccount() {
  fireEvent.change(screen.getByTestId("reg-name"), { target: { value: "Ada Glass" } });
  fireEvent.change(screen.getByTestId("reg-password"), { target: { value: "longenough" } });
  fireEvent.change(screen.getByTestId("reg-confirm"), { target: { value: "longenough" } });
  fireEvent.change(screen.getByTestId("reg-signature"), { target: { value: "Ada Glass" } });
  fireEvent.click(screen.getByTestId("reg-agree"));
}

test("invite setup requires the same charge terms as signup before the card", async () => {
  render(<PortalRegister />);
  expect(await screen.findByText(TERMS)).toBeInTheDocument();
  fillAccount();
  fireEvent.click(screen.getByTestId("reg-submit"));
  expect(await screen.findByTestId("reg-error")).toHaveTextContent("Accept the charge terms to continue.");
  expect(portalApi.post).not.toHaveBeenCalled();

  fireEvent.click(screen.getByTestId("reg-charge"));
  fireEvent.click(screen.getByTestId("reg-submit"));
  await waitFor(() => expect(portalApi.post).toHaveBeenCalledWith(
    "/public/invites/invite-token/register",
    expect.objectContaining({
      terms_agreed: true,
      terms_signature: "Ada Glass",
      charge_accepted: true,
    }),
  ));
  expect(await screen.findByTestId("fake-save-accepted")).toBeInTheDocument();
});

test("a saved invite card that already recorded charge acceptance opens booking", async () => {
  render(<PortalRegister />);
  await screen.findByText(TERMS);
  fillAccount();
  fireEvent.click(screen.getByTestId("reg-charge"));
  fireEvent.click(screen.getByTestId("reg-submit"));
  fireEvent.click(await screen.findByTestId("fake-save-accepted"));
  expect(mockRouter.nav).toHaveBeenCalledWith("/portal/book");
  expect(screen.queryByTestId("charge-modal")).not.toBeInTheDocument();
});

test("a saved invite card without charge acceptance still asks", async () => {
  render(<PortalRegister />);
  await screen.findByText(TERMS);
  fillAccount();
  fireEvent.click(screen.getByTestId("reg-charge"));
  fireEvent.click(screen.getByTestId("reg-submit"));
  fireEvent.click(await screen.findByTestId("fake-save-pending"));
  expect(await screen.findByTestId("charge-modal")).toHaveTextContent(TERMS);
  expect(mockRouter.nav).not.toHaveBeenCalled();
});
