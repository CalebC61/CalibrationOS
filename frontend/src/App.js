import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import "@/App.css";
import { getStoredAuth } from "@/lib/api";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import ShopsList from "@/pages/ShopsList";
import ShopNew from "@/pages/ShopNew";
import ShopDetail from "@/pages/ShopDetail";
import PublicBooking from "@/pages/PublicBooking";
import Field from "@/pages/Field";
import Invoices from "@/pages/Invoices";
import Messages from "@/pages/Messages";
import Settings from "@/pages/Settings";

function Protected({ children, ownerOnly }) {
  const loc = useLocation();
  const auth = getStoredAuth();
  if (!auth) return <Navigate to="/login" state={{ from: loc }} replace />;
  if (ownerOnly && auth.role !== "owner") return <Navigate to="/field" replace />;
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
          <Route path="/book/:token" element={<PublicBooking />} />
          <Route path="/dashboard" element={<Protected ownerOnly><Dashboard /></Protected>} />
          <Route path="/shops" element={<Protected ownerOnly><ShopsList /></Protected>} />
          <Route path="/shops/new" element={<Protected ownerOnly><ShopNew /></Protected>} />
          <Route path="/shops/:id" element={<Protected ownerOnly><ShopDetail /></Protected>} />
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
