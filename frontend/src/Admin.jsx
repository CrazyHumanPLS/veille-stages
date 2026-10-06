import { useCallback, useEffect, useState } from "react";
import { api, post, put, ago, Dot, useAction } from "./api.jsx";

export default function Admin({ me }) {
  const [ov, setOv] = useState(null);
  const [set, setSet] = useState(null);
  const [temp, setTemp] = useState(null);
  const { msg, busy, act } = useAction();
  const load = useCallback(() => { api("/api/admin/overview").then(setOv).catch(() => {}); }, []);
  useEffect(() => { load(); api("/api/admin/settings").then(setSet).catch(() => {}); }, [load]);
  if (!ov || !set) return <p className="mute">Chargement…</p>;
  const c = ov.config;
  const checks = [["Base de données en ligne (Postgres)", c.database === "postgres"], ["Clé secrète du site (SECRET_KEY)", c.secret],
    ["Clé Gemini commune (GEMINI_API_KEY)", c.gemini], ["Réveil automatique (CRON_KEY)", c.cron], ["Adresse du site (APP_URL)", c.app_url],
    ["Adzuna (facultatif)", c.adzuna], ["France Travail (facultatif)", c.france_travail], ["Bot Telegram (facultatif)", c.telegram]];
  const save = body => act("Enregistrement…", async () => { setSet(await put("/api/admin/settings", body)); });
  const lim = k => ({ type: "number", min: 0, value: set.limits[k], onChange: e => setSet({ ...set, limits: { ...set.limits, [k]: +e.target.value } }) });
  const lines = k => ({ value: (set.criteria[k] || []).join("\n"), onChange: e => setSet({ ...set, criteria: { ...set.criteria, [k]: e.target.value.split("\n") } }) });
  const user = (u, label, fn) => act(label, async () => { const r = await fn(); load(); return r; });
  const active = ov.users.filter(u => !u.disabled && !u.paused).length;
  return (<>
    {msg && <p className="note">{msg}</p>}
    <div className="stats">
      <div><b>{ov.users.length}</b><span>inscrits ({active} actifs)</span></div>
      <div><b>{ov.shared.used} / {ov.shared.limit}</b><span>appels à la clé commune aujourd'hui</span></div>
      <div><b>{ov.pool}</b><span>offres dans le stock commun</span></div>
      <div><b>{ov.last_run ? ago(ov.last_run.at) : "jamais"}</b><span>dernière collecte</span></div>
      <button className="btn ghost" disabled={busy} onClick={() => act("Collecte en cours…", async () => { const r = await post("/api/admin/collect"); load(); return r.skipped ? "Une collecte était déjà en cours." : `Collecte faite : ${r.new} nouvelle(s) offre(s), ${r.scored} notée(s), ${r.alerts} alerte(s), ${r.users} compte(s) traité(s).`; })}>Collecter maintenant</button>
    </div>

    <h3>Inscrits</h3>
    {temp && <p className="note">Mot de passe provisoire de {temp.email} : <code>{temp.password}</code><br />Transmets-le-lui ; il le changera dans Réglages. Il ne sera plus affiché.</p>}
    <div className="card scroll"><table>
      <thead><tr><th>Compte</th><th>Dernière visite</th><th>CV</th><th>Alertes</th><th>IA aujourd'hui</th><th></th></tr></thead>
      <tbody>{ov.users.map(u => (
        <tr key={u.id}>
          <td><Dot ok={!u.disabled && !u.paused} /> {u.name || "(sans prénom)"}{u.is_admin && " · admin"}<div className="mute">{u.email}</div>
            {u.disabled && <div className="err">désactivé</div>}{!u.disabled && u.paused && <div className="mute">veille en pause (inactif)</div>}
            {u.ai_error && <div className="err small">IA : {u.ai_error}</div>}{u.alert_error && <div className="err small">Alertes : {u.alert_error}</div>}</td>
          <td>{ago(u.last_seen)}</td><td>{u.cv}</td><td>{u.channels.join(", ") || "aucune"}</td>
          <td>{u.own_key ? "sa clé" : "clé commune"}<div className="mute">{u.usage.score || 0} notes · {u.usage.assist || 0} générations</div></td>
          <td>{u.id !== me.id && <div className="row" style={{ margin: 0 }}>
            <button className="btn ghost" disabled={busy} onClick={() => user(u, "…", async () => { const r = await post(`/api/admin/users/${u.id}/reset`); setTemp({ email: u.email, password: r.password }); return "Mot de passe provisoire créé."; })}>Nouveau mot de passe</button>
            <button className="btn ghost" disabled={busy} onClick={() => user(u, "…", async () => { await api(`/api/admin/users/${u.id}`, { method: "PATCH", body: JSON.stringify({ disabled: !u.disabled }) }); return u.disabled ? "Compte réactivé." : "Compte désactivé."; })}>{u.disabled ? "Réactiver" : "Désactiver"}</button>
            <button className="btn ghost" disabled={busy} onClick={() => window.confirm(`Supprimer définitivement le compte ${u.email} et toutes ses données ?`) && user(u, "…", async () => { await api(`/api/admin/users/${u.id}`, { method: "DELETE" }); return "Compte supprimé."; })}>Supprimer</button>
          </div>}</td>
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
      <p className="mute">Limites par personne et par jour, pour ceux qui utilisent la clé commune (ceux qui ont mis leur propre clé n'ont pas de limite) :</p>
      <div className="row">
        <label>Offres notées <input {...lim("score")} /></label>
        <label>Générations de l'assistant <input {...lim("assist")} /></label>
        <label>Analyses de CV <input {...lim("cv")} /></label>
        <label>Plafond global d'appels à la clé commune <input {...lim("shared_requests")} style={{ width: 90 }} /></label>
      </div>
      <button className="btn" disabled={busy} onClick={() => save({ limits: set.limits, site: set.site })}>Enregistrer</button>
    </div>

    <h3>Branchements du site</h3>
    <div className="card">{checks.map(([l, ok]) => <div key={l}><Dot ok={ok} /> {l}</div>)}</div>

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
