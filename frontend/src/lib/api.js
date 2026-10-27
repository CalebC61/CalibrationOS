import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("cos_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

export function setToken(t) {
  if (t) localStorage.setItem("cos_token", t);
  else localStorage.removeItem("cos_token");
}

export function getStoredAuth() {
  const t = localStorage.getItem("cos_token");
  const r = localStorage.getItem("cos_role");
  const n = localStorage.getItem("cos_name");
  const i = localStorage.getItem("cos_tech_id");
  if (!t) return null;
  return { token: t, role: r, name: n, tech_id: i };
}

export function setStoredAuth(d) {
  if (d) {
    localStorage.setItem("cos_token", d.token);
    localStorage.setItem("cos_role", d.role);
    localStorage.setItem("cos_name", d.name);
    localStorage.setItem("cos_tech_id", d.tech_id);
  } else {
    ["cos_token", "cos_role", "cos_name", "cos_tech_id"].forEach(k => localStorage.removeItem(k));
  }
}

export function formatTime(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
export function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
export function todayStr() {
  const d = new Date();
  const y = d.getFullYear(); const m = String(d.getMonth()+1).padStart(2,"0"); const day = String(d.getDate()).padStart(2,"0");
  return `${y}-${m}-${day}`;
}

// America/Phoenix civil date (UTC−7, no DST). Intl is built in; formatToParts avoids
// locale-dependent string order. Pass an instant to format a specific moment.
export function phoenixTodayStr(instant = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Phoenix",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(instant);
  const get = (type) => parts.find((p) => p.type === type).value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}
export function dateStr(d) {
  const y = d.getFullYear(); const m = String(d.getMonth()+1).padStart(2,"0"); const day = String(d.getDate()).padStart(2,"0");
  return `${y}-${m}-${day}`;
}
