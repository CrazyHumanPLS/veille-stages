import { useCallback, useEffect, useState } from "react";
import { api, post, put, ago, Dot, useAction } from "./api.jsx";

// Publications prêtes à copier, fabriquées à partir des vraies offres de la semaine (aucun appel à l'IA).
function Posts() {
  const [data, setData] = useState(null);
  const [region, setRegion] = useState("");
  const [msg, setMsg] = useState("");
  const load = r => { setMsg("Préparation…"); api(`/api/admin/posts?region=${encodeURIComponent(r)}`).then(d => { setData(d); setMsg(""); }).catch(e => setMsg("Erreur : " + e.message)); };
  const copy = async (text, what) => {
    try { await navigator.clipboard.writeText(text); setMsg(`${what} : texte copié.`); }
    catch { setMsg("Copie impossible : sélectionne le texte à la main."); }
  };
  const KINDS = [["x", "X (Twitter)"], ["linkedin", "LinkedIn"], ["video", "Script de vidéo courte (TikTok, Reels)"]];
  return (<div className="card posts">
    <p className="mute">Un texte par domaine qui compte au moins 3 offres cette semaine. Les chiffres et les offres viennent du stock du site. Relis toujours avant de publier, et adapte la première phrase à ta façon de parler.</p>
    <div className="row">
      <select aria-label="Région" value={region} onChange={e => { setRegion(e.target.value); if (data) load(e.target.value); }}>
        <option value="">Toute la France</option>
        {Object.entries(data?.regions || {}).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <button className="btn" onClick={() => load(region)}>{data ? "Actualiser" : "Préparer les publications du jour"}</button>
    </div>
    {msg && <p className="note">{msg}</p>}
    {data && !data.app_url && <p className="err small">La variable APP_URL n'est pas renseignée : les liens des textes sont incomplets.</p>}
    {data && !data.posts.length && <p className="mute">Pas assez d'offres cette semaine pour cette sélection.</p>}
    {data?.posts.map(p => (<details key={p.domain}>
      <summary><b>{p.label}</b> : {p.count} offres</summary>
      {KINDS.map(([k, l]) => (<div key={k}>
        <h4>{l}{k === "x" && ` (${p.x.length} caractères sur 280)`}</h4>
        <textarea readOnly value={p[k]} onFocus={e => e.target.select()} />
        <button className="btn ghost" onClick={() => copy(p[k], l)}>Copier</button>
      </div>))}
    </details>))}
  </div>);
}

export default function Admin({ me }) {
  const [ov, setOv] = useState(null);
  const [set, setSet] = useState(null);
  const [temp, setTemp] = useState(null);
  const [mail, setMail] = useState("");
  const { msg, busy, act } = useAction();
  const load = useCallback(() => { api("/api/admin/overview").then(setOv).catch(() => {}); }, []);
  useEffect(() => { load(); api("/api/admin/settings").then(setSet).catch(() => {}); }, [load]);
  if (!ov || !set) return <p className="mute">Chargement…</p>;
  const c = ov.config;
  const checks = [["Base de données en ligne (Postgres)", c.database === "postgres"], ["Clé secrète du site (SECRET_KEY)", c.secret],
    ["Clé Gemini commune (GEMINI_API_KEY)", c.gemini], ["Réveil automatique (CRON_KEY)", c.cron], ["Adresse du site (APP_URL)", c.app_url],
    ["Envoi d'e-mails : confirmation d'adresse et mot de passe oublié (BREVO_API_KEY et MAIL_FROM)", c.mail], ["Adzuna (facultatif)", c.adzuna], ["France Travail (facultatif)", c.france_travail], ["Bot Telegram (facultatif)", c.telegram]];
  const save = body => act("Enregistrement…", async () => { setSet(await put("/api/admin/settings", body)); });
  const lim = k => ({ type: "number", min: 0, value: set.limits[k], onChange: e => setSet({ ...set, limits: { ...set.limits, [k]: +e.target.value } }) });
  const lines = k => ({ value: (set.criteria[k] || []).join("\n"), onChange: e => setSet({ ...set, criteria: { ...set.criteria, [k]: e.target.value.split("\n") } }) });
  const user = (u, label, fn) => act(label, async () => { const r = await fn(); load(); return r; });
  const active = ov.users.filter(u => !u.disabled && !u.paused).length;
  return (<>
    {msg && <p className="note">{msg}</p>}
    <div className="stats">
      <div><b>{ov.stats.total}</b><span>inscrits ({active} avec veille active)</span></div>
      <div><b>{ov.stats.active_7d}</b><span>venus sur le site en 7 jours</span></div>
      <div><b>{ov.stats.new_7d}</b><span>nouveaux en 7 jours</span></div>
      <div><b>{ov.shared.used} / {ov.shared.limit}</b><span>appels à la clé commune aujourd'hui</span></div>
      <div><b>{ov.pool}</b><span>offres dans le stock commun</span></div>
      <div><b>{ov.last_run ? ago(ov.last_run.at) : "jamais"}</b><span>dernière collecte</span></div>
      <button className="btn ghost" disabled={busy} onClick={() => act("Collecte en cours…", async () => { const r = await post("/api/admin/collect"); load(); return r.skipped ? "Une collecte était déjà en cours." : `Collecte faite : ${r.new} nouvelle(s) offre(s), ${r.scored} notée(s), ${r.alerts} alerte(s), ${r.users} compte(s) traité(s).`; })}>Collecter maintenant</button>
    </div>

    <p className="mute">Sur {ov.stats.total} inscrits : {ov.stats.with_cv} ont importé un CV, {ov.stats.with_alerts} ont branché une alerte, {ov.stats.own_key} utilisent leur propre clé, {ov.stats.premium} sont en Premium, {ov.stats.active_30d} sont venus dans les 30 derniers jours.</p>

    <h3>Publications du jour</h3>
    <Posts />

    <h3>Inscrits</h3>
    {temp && <p className="note">Mot de passe provisoire de {temp.email} : <code>{temp.password}</code><br />Transmets-le-lui ; il le changera dans Réglages. Il ne sera plus affiché.</p>}
    <div className="card scroll"><table>
      <thead><tr><th>Compte</th><th>Dernière visite</th><th>CV</th><th>Alertes</th><th>IA aujourd'hui</th><th></th></tr></thead>
      <tbody>{ov.users.map(u => (
        <tr key={u.id}>
          <td><Dot ok={!u.disabled && !u.paused} /> {u.name || "(sans prénom)"}{u.is_admin && <span className="tag">admin</span>}{u.premium && <span className="tag gold">Premium jusqu'au {new Date(u.premium_until * 1000).toLocaleDateString("fr-FR")}</span>}<div className="mute">{u.email}</div>
            {!u.verified && <div className="mute">adresse e-mail non confirmée</div>}{u.disabled && <div className="err">désactivé</div>}{!u.disabled && u.paused && <div className="mute">veille en pause (inactif)</div>}
            {u.ai_error && <div className="err small">IA : {u.ai_error}</div>}{u.alert_error && <div className="err small">Alertes : {u.alert_error}</div>}</td>
          <td>{ago(u.last_seen)}</td><td>{u.cv}</td><td>{u.channels.join(", ") || "aucune"}</td>
          <td>{u.own_key ? "sa clé" : "clé commune"}<div className="mute">{u.usage.score || 0} notes · {u.usage.assist || 0} générations</div></td>
          <td><div className="row" style={{ margin: 0 }}>
            <button className="btn ghost" disabled={busy} onClick={() => user(u, "…", async () => { await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: JSON.stringify({ premium_days: 30 }) }); return `30 jours de Premium ajoutés à ${u.email}.`; })}>+30 j Premium</button>
            {u.premium && <button className="btn ghost" disabled={busy} onClick={() => user(u, "…", async () => { await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: JSON.stringify({ premium_days: 0 }) }); return "Premium retiré."; })}>Retirer Premium</button>}
            {u.id !== me.id && <><button className="btn ghost" disabled={busy} onClick={() => user(u, "…", async () => { const r = await post(`/api/admin/users/${u.id}/reset`); setTemp({ email: u.email, password: r.password }); return "Mot de passe provisoire créé."; })}>Nouveau mot de passe</button>
            <button className="btn ghost" disabled={busy} onClick={() => user(u, "…", async () => { await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: JSON.stringify({ disabled: !u.disabled }) }); return u.disabled ? "Compte réactivé." : "Compte désactivé."; })}>{u.disabled ? "Réactiver" : "Désactiver"}</button>
            <button className="btn ghost" disabled={busy} onClick={() => window.confirm(`Supprimer définitivement le compte ${u.email} et toutes ses données ?`) && user(u, "…", async () => { await api(`/api/admin/users/${u.id}`, { method: "DELETE" }); return "Compte supprimé."; })}>Supprimer</button></>}
          </div></td>
        </tr>))}</tbody>
    </table></div>

    <h3>Inscriptions et limites</h3>
    <div className="card">
      <div className="row">
        <label>Inscriptions <select value={set.site.signup} onChange={e => setSet({ ...set, site: { ...set.site, signup: e.target.value } })}>
          <option value="open">ouvertes à tous</option><option value="invite">avec un code d'invitation</option><option value="closed">fermées</option></select></label>
        {set.site.signup === "invite" && <label>Code <input value={set.site.invite_code} onChange={e => setSet({ ...set, site: { ...set.site, invite_code: e.target.value } })} /></label>}
        <label>Nombre maximal d'inscrits <input {...lim("max_users")} /></label>
      </div>
      <p className="mute">Limites par personne et par jour en formule gratuite (elles s'appliquent aussi à ceux qui ont mis leur propre clé) :</p>
      <div className="row">
        <label>Offres notées <input {...lim("score")} /></label>
        <label>Générations de l'assistant <input {...lim("assist")} /></label>
        <label>Analyses de CV <input {...lim("cv")} /></label>
        <label>Plafond global d'appels à la clé commune <input {...lim("shared_requests")} style={{ width: 90 }} /></label>
      </div>
      <p className="mute">Les mêmes limites pour les comptes Premium :</p>
      <div className="row">
        <label>Offres notées <input {...lim("p_score")} /></label>
        <label>Générations de l'assistant <input {...lim("p_assist")} /></label>
        <label>Analyses de CV <input {...lim("p_cv")} /></label>
        <label>Appels communs réservés aux Premium <input {...lim("p_reserve")} style={{ width: 90 }} /></label>
      </div>
      <p className="mute">Pour vendre le Premium : mets ton lien de paiement dans la variable PREMIUM_URL et le prix affiché dans PREMIUM_PRICE (Render, onglet Environment). Quand quelqu'un a payé, clique « +30 j Premium » sur sa ligne.</p>
      <button className="btn" disabled={busy} onClick={() => save({ limits: set.limits, site: set.site })}>Enregistrer</button>
    </div>

    <h3>Branchements du site</h3>
    <div className="card">{checks.map(([l, ok]) => <div key={l}><Dot ok={ok} /> {l}</div>)}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn ghost" disabled={busy} onClick={async () => {
          setMail("Envoi en cours…");
          try { const r = await post("/api/admin/mail/test"); setMail(`Brevo a accepté l'e-mail, envoyé à ${r.to} depuis ${r.from}. S'il n'arrive pas d'ici deux minutes, regarde tes indésirables, puis le journal « Transactionnel » de Brevo.`); }
          catch (e) { setMail("Échec : " + e.message); }
        }}>Envoyer un e-mail de test</button>
      </div>
      {mail && <p className={mail.startsWith("Échec") ? "err" : "note"} style={{ marginBottom: 0 }}>{mail}</p>}
    </div>

    <h3>État des sources</h3>
    <div className="card scroll"><table>
      <thead><tr><th>Source</th><th>Dernier passage</th><th>Offres lues</th><th>Nouvelles</th><th></th></tr></thead>
      <tbody>{Object.entries(ov.sources).sort().map(([n, s]) => (
        <tr key={n}><td><Dot ok={s.ok} /> {n}</td><td>{ago(s.last)}</td><td>{s.found ?? ""}</td><td>{s.new ?? ""}</td><td className="err">{s.ok ? "" : s.error}</td></tr>))}</tbody>
    </table>{!Object.keys(ov.sources).length && <p className="mute">Aucune collecte n'a encore eu lieu.</p>}</div>

    <h3>Collecte commune</h3>
    <div className="card">
      <p className="mute">Ces réglages décident de ce qui entre dans le stock commun d'offres. Les trois listes de mots-clés servent aussi de listes par défaut à chaque inscrit.</p>
      <div className="row"><label>Ignorer une offre sous le score <input type="number" min={0} max={100} value={set.criteria.min_kw} onChange={e => setSet({ ...set, criteria: { ...set.criteria, min_kw: +e.target.value } })} /></label></div>
      <div className="cols">
        <div><h4>Mots-clés forts (un par ligne)</h4><textarea {...lines("strong")} /></div>
        <div><h4>Technologies (une par ligne)</h4><textarea {...lines("tech")} /></div>
        <div><h4>Mots à pénaliser dans le titre</h4><textarea {...lines("negative")} /></div>
        <div><h4>Requêtes Adzuna (une par ligne, tous les mots obligatoires)</h4><textarea {...lines("adzuna_queries")} /></div>
        <div><h4>Requêtes France Travail (mots séparés par des virgules)</h4><textarea {...lines("ft_queries")} /></div>
        <div><h4>Flux RSS à surveiller (un par ligne, « Nom | adresse »)</h4><textarea {...lines("rss_feeds")} placeholder="LinkedIn réseaux | https://www.google.com/alerts/feeds/…" /></div>
      </div>
      <button className="btn" disabled={busy} onClick={() => save({ criteria: set.criteria })}>Enregistrer la collecte</button>
    </div>
  </>);
}
