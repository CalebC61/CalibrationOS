import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const PORTAL_TOKEN_KEY = "cos_portal_token";

export const portalApi = axios.create({ baseURL: API });
portalApi.interceptors.request.use((cfg) => {
  const t = localStorage.getItem(PORTAL_TOKEN_KEY);
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

export function getPortalAuth() {
  const t = localStorage.getItem(PORTAL_TOKEN_KEY);
  const n = localStorage.getItem("cos_portal_name");
  const s = localStorage.getItem("cos_portal_shop");
  const id = localStorage.getItem("cos_portal_user_id");
  const sid = localStorage.getItem("cos_portal_shop_id");
  const hpm = localStorage.getItem("cos_portal_has_pm") === "true";
  if (!t) return null;
  return { token: t, full_name: n, shop_name: s, shop_user_id: id, shop_id: sid, has_payment_method: hpm };
}

export function setPortalAuth(d) {
  if (d) {
    localStorage.setItem(PORTAL_TOKEN_KEY, d.token);
    localStorage.setItem("cos_portal_name", d.full_name || "");
    localStorage.setItem("cos_portal_shop", d.shop_name || "");
    localStorage.setItem("cos_portal_user_id", d.shop_user_id || "");
    localStorage.setItem("cos_portal_shop_id", d.shop_id || "");
    localStorage.setItem("cos_portal_has_pm", String(!!d.has_payment_method));
  } else {
    ["cos_portal_token","cos_portal_name","cos_portal_shop","cos_portal_user_id","cos_portal_shop_id","cos_portal_has_pm"].forEach(k => localStorage.removeItem(k));
  }
}
