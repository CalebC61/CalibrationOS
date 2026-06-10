import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import "@/App.css";
import { getStoredAuth } from "@/lib/api";
import { getPortalAuth } from "@/lib/portalApi";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import ShopsList from "@/pages/ShopsList";
import ShopNew from "@/pages/ShopNew";
import ShopDetail from "@/pages/ShopDetail";
import PublicShopStatus from "@/pages/PublicShopStatus";
import Field from "@/pages/Field";
import Invoices from "@/pages/Invoices";
import Messages from "@/pages/Messages";
import Settings from "@/pages/Settings";
import Invites from "@/pages/Invites";
import ChargeQueue from "@/pages/ChargeQueue";
import PortalLogin from "@/pages/PortalLogin";
import PortalRegister from "@/pages/PortalRegister";
import PortalSetupReturn from "@/pages/PortalSetupReturn";
import PortalDashboard from "@/pages/PortalDashboard";
import PortalJobsList from "@/pages/PortalJobsList";
import PortalJobDetail from "@/pages/PortalJobDetail";
import PortalBook from "@/pages/PortalBook";
import PortalSettings from "@/pages/PortalSettings";

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
  if (!auth) return <Navigate to="/login" replace />;
  return <Navigate to={auth.role === "owner" ? "/dashboard" : "/field"} replace />;
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<RoleRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/scorecard/:token" element={<PublicShopStatus />} />

          {/* Portal (shop user) */}
          <Route path="/portal/login" element={<PortalLogin />} />
          <Route path="/portal/invite/:token" element={<PortalRegister />} />
          <Route path="/portal/setup-return" element={<PortalProtected><PortalSetupReturn /></PortalProtected>} />
          <Route path="/portal" element={<PortalProtected><PortalDashboard /></PortalProtected>} />
          <Route path="/portal/jobs" element={<PortalProtected><PortalJobsList /></PortalProtected>} />
          <Route path="/portal/jobs/:id" element={<PortalProtected><PortalJobDetail /></PortalProtected>} />
          <Route path="/portal/book" element={<PortalProtected><PortalBook /></PortalProtected>} />
          <Route path="/portal/settings" element={<PortalProtected><PortalSettings /></PortalProtected>} />

          {/* Owner dashboard */}
          <Route path="/dashboard" element={<Protected ownerOnly><Dashboard /></Protected>} />
          <Route path="/shops" element={<Protected ownerOnly><ShopsList /></Protected>} />
          <Route path="/shops/new" element={<Protected ownerOnly><ShopNew /></Protected>} />
          <Route path="/shops/:id" element={<Protected ownerOnly><ShopDetail /></Protected>} />
          <Route path="/invites" element={<Protected ownerOnly><Invites /></Protected>} />
          <Route path="/charges" element={<Protected ownerOnly><ChargeQueue /></Protected>} />
          <Route path="/invoices" element={<Protected ownerOnly><Invoices /></Protected>} />
          <Route path="/messages" element={<Protected ownerOnly><Messages /></Protected>} />
          <Route path="/settings" element={<Protected ownerOnly><Settings /></Protected>} />
          <Route path="/field" element={<Protected><Field /></Protected>} />
          <Route path="*" element={<RoleRedirect />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
