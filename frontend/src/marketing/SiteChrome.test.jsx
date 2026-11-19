import { fireEvent, render, screen, within } from "@testing-library/react";
import ContactPage from "./ContactPage";
import HomePage from "./HomePage";
import { AboutPage, FaqPage, PricingPage, ServicesPage } from "./InfoPages";
import { SiteChrome } from "./SiteChrome";

jest.mock("../lib/api", () => ({
  getStoredAuth: () => ({ role: "owner", name: "Caleb" }),
}));

jest.mock("axios", () => {
  const instance = { get: jest.fn(), post: jest.fn(), interceptors: { request: { use: jest.fn() } } };
  return {
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn(), create: jest.fn(() => instance) },
  };
});

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Link: ({ children, to, ...rest }) => React.createElement("a", { href: to, ...rest }, children),
    NavLink: ({ children, to, className, end, ...rest }) => {
      const cls = typeof className === "function" ? className({ isActive: false }) : className;
      return React.createElement("a", { href: to, className: cls, ...rest }, children);
    },
    useLocation: () => ({ pathname: "/", hash: "", search: "" }),
  };
}, { virtual: true });

const HEADER = [
  ["Home", "/"],
  ["Pricing", "/pricing"],
  ["Service area", "/service-area"],
  ["Contact", "/contact"],
  ["Shop login", "/portal/login"],
  ["Create account", "/signup"],
];

const RETIRED = /by text|online scheduler|book online|real-time etas|job updates by text/i;

function renderPage(ui) {
  return render(ui);
}

test("the public header is six shop links", () => {
  renderPage(<SiteChrome><p>Page</p></SiteChrome>);
  const nav = screen.getByTestId("public-nav");
  const anchors = [...nav.querySelectorAll("a")];
  expect(anchors).toHaveLength(6);
  HEADER.forEach(([name, href]) => {
    const link = anchors.find((node) => node.getAttribute("href") === href);
    expect(link).toHaveAccessibleName(name);
  });
  ["/services", "/about", "/faq", "/login", "/book", "/dashboard"].forEach((href) => {
    expect(nav.querySelector(`a[href="${href}"]`)).toBeNull();
  });
  expect(screen.queryByRole("link", { name: "Book a job" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Dispatch" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Staff login" })).toHaveAttribute("href", "/login");
  expect(screen.getByRole("link", { name: "Services" })).toHaveAttribute("href", "/services");
  expect(screen.getByRole("link", { name: "About Us" })).toHaveAttribute("href", "/about");
  expect(screen.getByRole("link", { name: "FAQ" })).toHaveAttribute("href", "/faq");
});

test("the menu button opens and closes the public nav", () => {
  renderPage(<SiteChrome><p>Page</p></SiteChrome>);
  const menu = screen.getByTestId("public-menu");
  const nav = screen.getByTestId("public-nav");
  expect(menu).toHaveTextContent("Menu");
  expect(menu).toHaveAttribute("aria-expanded", "false");
  expect(menu).toHaveAttribute("aria-controls", "site-nav");
  expect(nav).not.toHaveClass("open");
  fireEvent.click(menu);
  expect(menu).toHaveAttribute("aria-expanded", "true");
  expect(nav).toHaveClass("open");
  fireEvent.click(within(nav).getByRole("link", { name: "Pricing" }));
  expect(menu).toHaveAttribute("aria-expanded", "false");
  expect(nav).not.toHaveClass("open");
});

test("public pages do not promise texts or a public scheduler", () => {
  const pages = [
    <HomePage key="home" />,
    <ServicesPage key="services" />,
    <PricingPage key="pricing" />,
    <AboutPage key="about" />,
    <FaqPage key="faq" />,
    <ContactPage key="contact" />,
  ];
  pages.forEach((page) => {
    const { container, unmount } = renderPage(page);
    expect(container.textContent).not.toMatch(RETIRED);
    const publicBook = [...container.querySelectorAll("a")].filter((node) => {
      const href = node.getAttribute("href") || "";
      return href === "/book" || href.startsWith("/book/");
    });
    expect(publicBook).toEqual([]);
    unmount();
  });
});

test("pricing and contact send booking to the shop account", () => {
  const pricing = renderPage(<PricingPage />);
  expect(pricing.container.textContent).toMatch(/Book and follow the job in your shop account/);
  screen.getAllByRole("link", { name: "Shop login" }).forEach((link) => {
    expect(link).toHaveAttribute("href", "/portal/login");
  });
  expect(screen.getByRole("link", { name: "Create your shop account" })).toHaveAttribute("href", "/signup");
  pricing.unmount();

  renderPage(<ContactPage />);
  screen.getAllByRole("link", { name: "Create account" }).forEach((link) => {
    expect(link).toHaveAttribute("href", "/signup");
  });
  screen.getAllByRole("link", { name: "Shop login" }).forEach((link) => {
    expect(link).toHaveAttribute("href", "/portal/login");
  });
  expect(screen.queryByRole("link", { name: "Book a job" })).not.toBeInTheDocument();
});
