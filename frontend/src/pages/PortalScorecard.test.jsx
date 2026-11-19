import { render, screen } from "@testing-library/react";

jest.mock("react-router-dom", () => {
  const React = require("react");
  return {
    Navigate: ({ to, replace }) => React.createElement("div", {
      "data-testid": "scorecard-redirect",
      "data-to": to,
      "data-replace": String(Boolean(replace)),
    }),
  };
}, { virtual: true });

import PortalScorecard from "./PortalScorecard";

test("the old scorecard address opens Today", () => {
  render(<PortalScorecard />);
  const redirect = screen.getByTestId("scorecard-redirect");
  expect(redirect).toHaveAttribute("data-to", "/portal");
  expect(redirect).toHaveAttribute("data-replace", "true");
});
