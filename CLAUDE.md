# Veille Stages (version publique) — contexte pour reprendre le projet

Créé le 06/10/2026 à partir de l'application personnelle `stage-app` (même auteur, voir son propre CLAUDE.md).
À tenir à jour à chaque évolution importante.

## L'utilisateur et son besoin

- Aghiles, étudiant en M2 (UVSQ, Paris-Saclay). Il veut ouvrir sa veille de stages à ses amis, puis à tous.
- N'est pas développeur de métier : étapes numérotées, concrètes, en français, noms exacts des boutons.
  Il utilise **GitHub Desktop** sous Windows. Tout doit rester **gratuit**.
- **Ne jamais modifier le dossier `stage-app`** (son application personnelle) : ce projet vit à côté.

## Où tout se trouve

| Élément | Emplacement |
|---|---|
| Code sur le PC | `C:\Users\User\Downloads\stage-m2-app\veille-stages` |
| Dépôt GitHub | à créer par l'utilisateur (privé), voir README étape 1 |
| Site, base, réveil | pas encore mis en ligne au 06/10/2026 (README étapes 2 à 6) |

Variables d'environnement (valeurs dans Render uniquement) : `DATABASE_URL`, `SECRET_KEY` (créée par Render,
ne jamais la changer), `ADMIN_EMAIL`, `CRON_KEY`, `APP_URL`, `APP_NAME`, `GEMINI_API_KEY` (clé commune),
`GEMINI_MODEL`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `SIGNUP_MODE`, `INVITE_CODE`, `CONTACT_EMAIL`, `DONATE_URL`,
`TELEGRAM_TOKEN`, `TELEGRAM_BOT`, `COLLECT_EVERY_SEC`.

## Choix de conception (décidés le 06/10/2026, l'utilisateur a délégué)

- **Offres communes, tout le reste par utilisateur.** Table `offers` partagée ; `user_offers` porte pour chaque
  personne son score par mots-clés, la note de l'IA, le CV conseillé, l'état (new/saved/hidden/applied),
  l'alerte envoyée ou non. `applications` et `usage` ont un `user_id`.
- **Coût de l'IA nul pour le propriétaire.** Clé commune avec limites par jour et par personne (40 notes,
  5 générations, 6 analyses de CV, plafond global 800 appels) ou clé Gemini personnelle sans limite.
  Réglable dans Administration (kv `limits`). Pas de publicité : inutile à cette échelle. Lien de don
  facultatif (`DONATE_URL`).
- **Alertes par personne** : webhook Discord personnel (conseillé), sujet ntfy, ou Telegram si le site a un bot.
- **Comptes** : e-mail + mot de passe (scrypt), jeton signé 30 jours, pas d'envoi d'e-mail. Mot de passe oublié :
  l'administrateur en crée un provisoire. Le premier compte (ou celui de `ADMIN_EMAIL`) est administrateur.
- **Périmètre de la collecte inchangé** : stages en Île-de-France, sources et mots-clés orientés informatique,
  réseaux, cybersécurité, cloud. Chaque inscrit ajuste ses mots-clés et son objectif.
- Comptes inactifs depuis 21 jours : veille en pause. 300 inscrits maximum par défaut.

## Architecture

- `backend/main.py` : API FastAPI (comptes, réglages, offres, assistant, administration), sert le site compilé.
- `backend/collector.py` : `collect()` (stock commun) puis `process_user()` pour chaque compte actif
  (tri, notation dans la limite du quota, alertes). `resync_one()` après un changement de CV ou de mots-clés.
- `backend/accounts.py` : comptes, réglages, secrets chiffrés. `backend/security.py` : mots de passe, jetons, chiffrement.
- `backend/quota.py` : qui paie l'IA, limites, consommation du jour.
- `backend/scoring.py`, `sources.py`, `ai.py`, `notify.py`, `cvstore.py`, `db.py` : repris de `stage-app`, adaptés
  pour recevoir l'utilisateur ou sa clé en paramètre.
- `backend/tests/test_pipeline.py` : tests avec réseau simulé (`python -m pytest -q` dans `backend`).
- `frontend/src/` : `App.jsx` (connexion, offres, suivi, assistant, profil), `Settings.jsx`, `Admin.jsx`, `api.jsx`.

## Règles de travail (reprises de stage-app)

1. Vérifier chaque écriture sur le PC en relisant les fichiers et en comparant leur empreinte.
2. Pas d'accès au dépôt GitHub : l'utilisateur fait Commit puis Push dans GitHub Desktop.
3. Les vraies API ne sont pas testables depuis la session : tests avec réponses simulées, et le dire clairement.
4. `create_all` n'ajoute pas de colonne à une table existante : passer par la boucle `ALTER TABLE` de `db.py`.
5. Les réglages enregistrés (kv `criteria`, `limits`, `site`) priment sur les valeurs par défaut du code.
6. `CRON_KEY` : lettres et chiffres uniquement. `/api/collect` est bloqué par les bloqueurs de publicité.

## Points à surveiller

- Render gratuit : 750 heures par mois pour tout le compte. Deux services réveillés en permanence
  (celui-ci et `stage-m2`) dépassent le quota. Voir le README.
- Les quotas gratuits de Gemini changent souvent : ajuster le plafond global dans Administration d'après
  ce qu'affiche Google AI Studio pour la clé commune.
- Avec une clé gratuite, Google peut utiliser les textes envoyés : c'est écrit dans la page Confidentialité.

## État au 06/10/2026

- Code écrit, 4 tests automatiques réussis, site compilé et parcouru dans un navigateur en local
  (inscription, offres, réglages, administration). Jamais mis en ligne, jamais testé avec les vraies API.

## Pistes non faites

Vérification de l'adresse e-mail et « mot de passe oublié » par e-mail ; récapitulatif quotidien ;
option alternance ou autres régions ; import des candidatures de l'application personnelle.
