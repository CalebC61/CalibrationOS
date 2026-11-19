import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import "@/App.css";
import { getStoredAuth } from "@/lib/api";
import { getPortalAuth } from "@/lib/portalApi";
import HomePage from "@/marketing/HomePage";
import { AboutPage, AreaPage, FaqPage, PricingPage, ServicesPage } from "@/marketing/InfoPages";
import ContactPage from "@/marketing/ContactPage";
import SignupPage from "@/marketing/SignupPage";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import ShopsList from "@/pages/ShopsList";
import ShopNew from "@/pages/ShopNew";
import ShopDetail from "@/pages/ShopDetail";
import OwnerBook from "@/pages/PublicBooking";
import PortalScorecard from "@/pages/PortalScorecard";
import OwnerAction from "@/pages/OwnerAction";
import Field from "@/pages/Field";
import Money from "@/pages/Money";
import Settings from "@/pages/Settings";
import MapPins from "@/pages/MapPins";
import { OWNER_REDIRECTS } from "@/ownerNav";
import PortalLogin from "@/pages/PortalLogin";
import PortalRegister from "@/pages/PortalRegister";
import PortalSetupReturn from "@/pages/PortalSetupReturn";
import PortalDashboard from "@/pages/PortalDashboard";
import PortalJobsList from "@/pages/PortalJobsList";
import PortalJobDetail from "@/pages/PortalJobDetail";
import PortalBook from "@/pages/PortalBook";
import PortalSettings from "@/pages/PortalSettings";
import PortalReady from "@/pages/PortalReady";
import PortalForgot from "@/pages/PortalForgot";
import PortalReset from "@/pages/PortalReset";

function Protected({ children, ownerOnly }) {
  const loc = useLocation();
  const auth = getStoredAuth();
  if (!auth) return <Navigate to="/login" state={{ from: loc }} replace />;
  if (ownerOnly && auth.role !== "owner") return <Navigate to="/field" replace />;
  return children;
}

function PortalProtected({ children }) {
  const auth = getPortalAuth();
  if (!auth) return <Navigate to="/portal/login" replace />;
  return children;
}

function RoleRedirect() {
  const auth = getStoredAuth();
  if (!auth) return <Navigate to="/" replace />;
  return <Navigate to={auth.role === "owner" ? "/dashboard" : "/field"} replace />;
}

function OldShopLink({ notice, next }) {
  return <Navigate to="/portal/login" replace state={{ notice, next }} />;
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/services" element={<ServicesPage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/service-area" element={<AreaPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/faq" element={<FaqPage />} />
          <Route path="/contact" element={<ContactPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/login" element={<Login />} />
          <Route path="/scorecard/:token" element={
            <OldShopLink notice="Your scorecard is in your shop portal. Log in to see it." next="/portal/scorecard" />
          } />
          <Route path="/book/:token" element={
            <OldShopLink notice="Booking now happens in your shop portal. Log in to book." next="/portal/book" />
          } />
          <Route path="/owner-action/:token" element={<OwnerAction />} />

          {/* Portal (shop user) */}
          <Route path="/portal/login" element={<PortalLogin />} />
          <Route path="/portal/forgot" element={<PortalForgot />} />
          <Route path="/portal/reset/:token" element={<PortalReset />} />
          <Route path="/portal/invite/:token" element={<PortalRegister />} />
          <Route path="/portal/ready" element={<PortalProtected><PortalReady /></PortalProtected>} />
          <Route path="/portal/setup-return" element={<PortalProtected><PortalSetupReturn /></PortalProtected>} />
          <Route path="/portal" element={<PortalProtected><PortalDashboard /></PortalProtected>} />
          <Route path="/portal/jobs" element={<PortalProtected><PortalJobsList /></PortalProtected>} />
          <Route path="/portal/jobs/:id" element={<PortalProtected><PortalJobDetail /></PortalProtected>} />
          <Route path="/portal/book" element={<PortalProtected><PortalBook /></PortalProtected>} />
          <Route path="/portal/scorecard" element={<PortalProtected><PortalScorecard /></PortalProtected>} />
          <Route path="/portal/settings" element={<PortalProtected><PortalSettings /></PortalProtected>} />

          {/* Owner dashboard */}
          <Route path="/dashboard" element={<Protected ownerOnly><Dashboard /></Protected>} />
          <Route path="/shops" element={<Protected ownerOnly><ShopsList /></Protected>} />
          <Route path="/shops/new" element={<Protected ownerOnly><ShopNew /></Protected>} />
          <Route path="/shops/:id/book" element={<Protected ownerOnly><OwnerBook /></Protected>} />
          <Route path="/shops/:id" element={<Protected ownerOnly><ShopDetail /></Protected>} />
          <Route path="/money" element={<Protected ownerOnly><Money /></Protected>} />
          <Route path="/settings" element={<Protected ownerOnly><Settings /></Protected>} />
          <Route path="/map-pins" element={<Protected ownerOnly><MapPins /></Protected>} />
          {OWNER_REDIRECTS.map((item) => (
            <Route
              key={item.path}
              path={item.path}
              element={<Protected ownerOnly><Navigate to={item.to} replace /></Protected>}
            />
          ))}
          <Route path="/field" element={<Protected><Field /></Protected>} />
          <Route path="*" element={<RoleRedirect />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
