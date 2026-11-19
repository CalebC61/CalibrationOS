/** Owner bar. Old paths stay as redirects so bookmarks and mail links still open. */
export const OWNER_NAV = [
  { to: "/dashboard", label: "Today", testId: "nav-today", end: true },
  { to: "/shops", label: "Shops", testId: "nav-shops" },
  { to: "/money", label: "Money", testId: "nav-money", end: true },
  { to: "/settings", label: "Settings", testId: "nav-settings", end: true, also: ["/map-pins"] },
];

export const OWNER_REDIRECTS = [
  { path: "/requests", to: "/shops?section=signups" },
  { path: "/invites", to: "/shops?section=invites" },
  { path: "/charges", to: "/money" },
  { path: "/invoices", to: "/money?section=invoices" },
  { path: "/days-off", to: "/settings?section=days-off" },
  { path: "/email-preview", to: "/settings?section=email" },
  { path: "/messages", to: "/settings?section=messages" },
  { path: "/growth", to: "/settings?section=growth" },
];
