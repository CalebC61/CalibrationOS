import { Navigate } from "react-router-dom";

/** Old scorecard links open Today. The four counts live on that page. */
export default function PortalScorecard() {
  return <Navigate to="/portal" replace />;
}
