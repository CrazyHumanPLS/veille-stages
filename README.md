# Veille Stages : la version publique, avec un compte par personne

Version multi-utilisateurs de l'application personnelle `stage-app`. Chaque inscrit a son compte, ses CV,
ses réglages, ses candidatures et ses propres alertes. Les offres, elles, sont collectées une seule fois
pour tout le monde. Tout reste gratuit.

## Comment ça marche

1. **Collecte commune.** Toutes les 3 minutes, le site interroge les pages carrières de `backend/companies.json`,
   Adzuna et les flux RSS, garde les stages en Île-de-France et supprime les doublons. Ce stock est partagé :
   10 ou 200 inscrits coûtent la même chose en collecte.
2. **Tri personnel.** Pour chaque inscrit, le site trie le stock avec ses mots-clés, puis l'IA note les
   nouveautés de 0 à 100 d'après son CV et indique quel CV envoyer.
3. **Alertes personnelles.** Chacun branche son propre canal dans l'onglet Réglages (Discord conseillé, ou ntfy).
4. **Assistant.** Lettre, adaptation du CV, message au recruteur, préparation d'entretien, suivi des candidatures.

## Qui paie l'IA : personne

- Le site possède une **clé Gemini commune** (`GEMINI_API_KEY`). Les inscrits qui n'ont rien configuré
  l'utilisent, avec une limite par jour et par personne : 40 offres notées, 5 générations de l'assistant,
  6 analyses de CV. Un plafond global (800 appels par jour) protège la clé. Au-delà, les offres gardent
  un score par mots-clés et rien ne casse.
- Chaque inscrit peut coller **sa propre clé Gemini gratuite** dans Réglages (2 minutes, sans carte bancaire).
  Il n'a alors plus de limite côté site et ne consomme plus la clé commune.
- Toutes ces limites se changent dans l'onglet **Administration**, sans toucher au code.
- Un compte qui ne visite pas le site pendant 3 semaines est mis en pause (plus de notation ni d'alerte)
  et reprend à la connexion suivante.

## Mise en ligne, dans l'ordre

Garde un fichier texte ouvert pour noter chaque valeur.

### 1. Mettre le dossier sur GitHub (GitHub Desktop)
1. Menu **File** → **Add local repository…** → **Choose…** → sélectionne le dossier `veille-stages`.
2. GitHub Desktop dit que ce n'est pas un dépôt : clique le lien **create a repository**, puis **Create repository**.
3. Clique **Publish repository**, laisse **Keep this code private** coché, puis **Publish repository**.

### 2. Nouvelle base de données Supabase
1. https://supabase.com → **New project** (région Europe, mot de passe **sans caractères spéciaux**).
   C'est un deuxième projet : l'offre gratuite en autorise deux, celui de ton application personnelle reste intact.
2. Bouton **Connect** → onglet **Session pooler** → copie l'adresse `postgresql://…` et remplace
   `[YOUR-PASSWORD]` par ton mot de passe. C'est `DATABASE_URL`.

### 3. Clé Gemini commune
https://aistudio.google.com/apikey → **Create API key**. Crée-la de préférence **dans un nouveau projet Google**,
pour qu'elle ne partage pas le quota de ton application personnelle. C'est `GEMINI_API_KEY`.

### 4. Service Render
1. https://dashboard.render.com → **New** → **Blueprint** → choisis le dépôt `veille-stages`.
2. Remplis : `DATABASE_URL`, `ADMIN_EMAIL` (ton adresse e-mail), `CRON_KEY` (un mot secret, lettres et
   chiffres uniquement), `GEMINI_API_KEY`, et si tu veux `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` (les mêmes que
   ton application personnelle). Laisse le reste vide. `SECRET_KEY` est créée par Render : **ne la modifie jamais**.
3. Clique **Apply**. Quand le service est en ligne, copie son adresse et mets-la dans la variable `APP_URL`
   (onglet **Environment** du service), puis **Save Changes**.

### 5. Réveil automatique
https://cron-job.org → **Create cronjob** → adresse `https://TON-SERVICE.onrender.com/api/cron?key=TA_CRON_KEY`,
toutes les 5 minutes.

### 6. Ton compte administrateur
Ouvre le site, clique **Créer un compte** et inscris-toi avec l'adresse mise dans `ADMIN_EMAIL` :
l'onglet **Administration** apparaît. Importe ton CV dans **Profil**, branche Discord dans **Réglages**,
clique **Envoyer un test**.

## Attention : les heures gratuites de Render

Render donne 750 heures gratuites par mois **pour tout ton compte**. Un service réveillé jour et nuit en
consomme environ 730. Deux services réveillés en permanence (ton application personnelle + celle-ci)
épuisent donc le quota vers le milieu du mois, et Render suspend alors les deux jusqu'au mois suivant.
Le plus simple : tester cette version quelques jours, puis utiliser ton propre compte dessus et suspendre
l'ancien service (le dossier et le dépôt `stage-app` ne sont pas touchés).

## Ce qu'un administrateur peut faire

- Voir les inscrits, leur dernière visite, leur consommation d'IA du jour, leurs erreurs d'alerte.
- Créer un mot de passe provisoire pour quelqu'un qui a oublié le sien (il n'y a pas d'envoi d'e-mail).
- Désactiver ou supprimer un compte.
- Ouvrir, fermer ou protéger les inscriptions par un code d'invitation ; fixer un nombre maximal d'inscrits.
- Changer les limites d'IA et les réglages de la collecte commune (mots-clés, requêtes Adzuna, flux RSS).

## Données personnelles

Le site enregistre des CV : tu en es responsable. Ce qui est en place : consentement à l'inscription,
page « Confidentialité et données », téléchargement de ses données, suppression immédiate du compte,
mots de passe hachés (scrypt), clés Gemini et adresses d'alerte chiffrées en base. Ne partage jamais
`SECRET_KEY` ni `DATABASE_URL`, et mets ton adresse dans `CONTACT_EMAIL` pour que les inscrits puissent t'écrire.

## Tester sur ton PC (facultatif)

```
cd backend
pip install -r requirements.txt pytest
python -m pytest -q
```
