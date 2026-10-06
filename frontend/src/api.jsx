import { useState as useStateSafe } from "react";

// Appels au serveur + petits outils d'affichage partagés par tous les écrans.
let onLogout = () => {};
export const setOnLogout = fn => { onLogout = fn; };

// localStorage peut être indisponible (navigation privée stricte) : le site doit marcher quand même.
const store = {
  get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* tant pis */ } },
  del: k => { try { localStorage.removeItem(k); } catch { /* tant pis */ } },
};
let memoryToken = null;
export const getToken = () => memoryToken ?? store.get("token");
export const setToken = t => { memoryToken = t; if (t) store.set("token", t); else store.del("token"); };

export async function api(path, opts = {}) {
  const headers = { ...(opts.body instanceof FormData ? {} : { "Content-Type": "application/json" }) };
  const tok = getToken();
  if (tok) headers.Authorization = `Bearer ${tok}`;
  const r = await fetch(path, { ...opts, headers });
  const open = ["/api/login", "/api/signup", "/api/public"].includes(path);
  if (r.status === 401 && !open) { onLogout(); throw new Error("Session expirée, reconnecte-toi."); }
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    const d = e.detail;
    throw new Error(typeof d === "string" ? d : d?.error ? [d.error, d.help].filter(Boolean).join(" → ") : `Erreur ${r.status}`);
  }
  return r.json();
}
export const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body ?? {}) });
export const put = (path, body) => api(path, { method: "PUT", body: JSON.stringify(body ?? {}) });

export const ago = ts => {
  if (!ts) return "jamais";
  const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  if (m < 1440) return `il y a ${Math.round(m / 60)} h`;
  return `il y a ${Math.round(m / 1440)} j`;
};
export const Dot = ({ ok }) => <span className={`dot ${ok ? "ok" : "ko"}`} />;
export const List = ({ title, items }) => items?.length ? <><h4>{title}</h4><ul>{items.map((x, i) => <li key={i}>{x}</li>)}</ul></> : null;

// Petit assistant : lance une action, affiche « en cours », puis le résultat ou l'erreur.
export function useAction() {
  const [msg, setMsg] = useStateSafe("");
  const [busy, setBusy] = useStateSafe(false);
  const act = async (label, fn) => {
    setBusy(true); setMsg(label);
    try { const r = await fn(); setMsg(typeof r === "string" ? r : "Enregistré."); }
    catch (e) { setMsg("Erreur : " + e.message); }
    setBusy(false);
  };
  return { msg, busy, act, setMsg };
}
