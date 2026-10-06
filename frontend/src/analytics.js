// Mesure d'audience Google Analytics, chargée UNIQUEMENT si le visiteur a cliqué « Accepter ».
// Aucune donnée personnelle n'est envoyée : seulement le nom de l'écran consulté.
const KEY = "audience";
const read = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const write = v => { try { localStorage.setItem(KEY, v); } catch { /* navigation privée stricte */ } };

let started = false;
export const choice = () => read();              // "yes", "no" ou null (pas encore répondu)

function start(id) {
  if (started || !id) return;
  started = true;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  window.gtag("config", id, { anonymize_ip: true, send_page_view: false });
  const s = document.createElement("script");
  s.async = true;
  s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id);
  document.head.appendChild(s);
}

export function accept(id) { write("yes"); start(id); }

export function refuse() {
  write("no");
  // efface les cookies de mesure déjà déposés si la personne change d'avis
  document.cookie.split(";").map(c => c.split("=")[0].trim()).filter(n => n.startsWith("_ga"))
    .forEach(n => { document.cookie = `${n}=; Max-Age=0; path=/`; document.cookie = `${n}=; Max-Age=0; path=/; domain=${location.hostname}`; });
  if (started) window.location.reload();          // arrête la mesure en cours
}

export function resume(id) { if (read() === "yes") start(id); }

export function page(name) { if (started && window.gtag) window.gtag("event", "page_view", { page_title: name, page_location: location.origin + "/" + name }); }
