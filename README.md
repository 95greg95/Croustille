# Croustille — Blog d'affiliation air fryer 100 % automatisé

Un blog statique (GitHub + Netlify) qui **publie automatiquement un article SEO de ~2500 mots chaque jour** (guides, comparatifs, conseils), avec **vos liens affiliés Amazon insérés automatiquement** et une intégration **Google AdSense** prête à activer.

## Comment ça marche

```
Chaque jour à 6h30 (Paris)
        │
        ▼
GitHub Actions lance scripts/generate_article.py
        │  → prend le prochain sujet dans content/topics.json
        │  → génère l'article via l'API Claude (~2500 mots, optimisé SEO)
        │  → insère les marqueurs produits {{product:...}}
        ▼
Commit + push automatique sur le dépôt
        │
        ▼
Netlify détecte le push → lance scripts/build.py
        │  → convertit les articles en pages HTML
        │  → transforme les marqueurs en liens affiliés avec VOTRE tag
        │  → génère sitemap, RSS, données structurées, pages légales
        ▼
Site en ligne, article publié. Zéro intervention.
```

## Installation (une seule fois, ~20 minutes)

### 1. Personnaliser `config.json`

- `site_name`, `site_tagline` : le nom de votre blog (changez « Croustille » si vous préférez).
- `amazon_tag` : votre identifiant Partenaire Amazon (ex. `monblog-21`). **Sans lui, aucune commission ne vous sera versée.** Si vous n'avez pas encore de compte : [partenaires.amazon.fr](https://partenaires.amazon.fr) (inscription gratuite, il faut un site en ligne — mettez le site en ligne d'abord, ajoutez le tag ensuite).
- `site_url` : l'URL finale du site (à mettre à jour après l'étape 3).

Personnalisez aussi les placeholders `[VOTRE NOM]`, `[VOTRE ADRESSE]`, `[VOTRE EMAIL]` dans `scripts/build.py` (sections mentions légales / confidentialité / à propos) : **ces pages sont légalement obligatoires en France et exigées par AdSense**.

### 2. Créer le dépôt GitHub

```bash
cd airfryer-blog
git init && git add . && git commit -m "Lancement du blog"
git branch -M main
git remote add origin https://github.com/VOTRE-COMPTE/airfryer-blog.git
git push -u origin main
```

Puis ajoutez votre clé API Anthropic (créée sur [console.anthropic.com](https://console.anthropic.com)) :
**Settings → Secrets and variables → Actions → New repository secret**
- Nom : `ANTHROPIC_API_KEY`
- Valeur : votre clé `sk-ant-...`

> Coût indicatif : un article de 2500 mots coûte quelques centimes d'API par jour.

### 3. Connecter Netlify

1. [app.netlify.com](https://app.netlify.com) → **Add new site → Import an existing project** → choisissez votre dépôt GitHub.
2. Netlify lit `netlify.toml` automatiquement : ne changez rien, cliquez **Deploy**.
3. Récupérez l'URL (`https://xxx.netlify.app`), reportez-la dans `site_url` de `config.json`, commitez. (Un domaine personnalisé type `croustille.fr` est fortement recommandé pour le SEO et AdSense — configurable dans Netlify → Domain settings.)

### 4. Tester la publication automatique

Onglet **Actions** du dépôt GitHub → workflow **« Article quotidien »** → **Run workflow**. Deux minutes plus tard, un nouvel article est commité et Netlify redéploie. Ensuite, ça tourne tout seul chaque matin.

### 5. Activer Google AdSense (quand le site a du contenu)

AdSense n'accepte que les sites avec du contenu réel : **attendez 3-4 semaines de publication** (20-30 articles) avant de postuler, c'est le facteur n°1 d'acceptation.

1. Inscrivez-vous sur [adsense.google.com](https://adsense.google.com) avec l'URL du site.
2. Dans `config.json` : `adsense_enabled: true` et votre identifiant dans `adsense_client` (`ca-pub-...`). Commitez.
3. Le site charge alors les **Auto Ads** de Google (annonces placées automatiquement « un peu partout », optimisées par Google) **derrière une bannière de consentement RGPD** déjà intégrée — obligatoire en France. Le fichier `ads.txt` requis est généré automatiquement.
4. Dans votre compte AdSense, activez aussi le **message de consentement européen (CMP)** proposé par Google (Confidentialité et messages) pour une conformité maximale.

## La vie du blog au quotidien

- **Ajouter des sujets** : la file `content/topics.json` contient 45 sujets (~6 semaines). Ajoutez-en quand vous voulez, le format est évident. Quand la file est vide, le workflow s'arrête proprement sans erreur.
- **Écrire un article à la main** : déposez un fichier `AAAA-MM-JJ-mon-slug.md` dans `content/articles/` avec le même frontmatter que les articles existants. Utilisez `{{product:Nom du produit}}` et `{{box:Nom|Accroche}}` : les liens affiliés seront générés au build.
- **Changer de tag Amazon** : modifiez `config.json`, commitez — tous les liens du site sont mis à jour d'un coup.
- **Prévisualiser en local** : `pip install markdown` puis `python scripts/build.py` et ouvrez `public/index.html`.

## SEO : ce qui est déjà intégré

- Balises title/meta description optimisées par article, canonical, Open Graph
- Données structurées Schema.org : `Article`, `FAQPage` (position 0 possible sur Google), `BreadcrumbList`, `WebSite`, `CollectionPage`
- `sitemap.xml` + `robots.txt` + flux RSS — pensez à soumettre le sitemap dans [Google Search Console](https://search.google.com/search-console) dès la mise en ligne (indispensable)
- Maillage interne automatique (« À lire aussi ») + liens contextuels entre articles
- Liens affiliés en `rel="sponsored nofollow"` (exigence Google)
- Site statique ultra-rapide : excellents Core Web Vitals

## Rappels importants (à lire vraiment)

- **Amazon impose de mentionner l'affiliation** : la mention est déjà présente en pied de page et en tête de chaque article. Ne la retirez pas, c'est une condition du programme Partenaires.
- **Amazon exige aussi des clics dans les 180 premiers jours** après l'inscription au programme, sinon le compte est fermé (réinscription possible).
- **Relisez de temps en temps les articles générés** : l'IA rédige bien, mais un œil humain régulier (caractéristiques produits, cohérence) améliore la qualité, la confiance des lecteurs… et le référencement. Google valorise les sites où l'on sent une supervision éditoriale réelle.
- Les pages mentions légales et politique de confidentialité contiennent des placeholders `[...]` à remplir : c'est une obligation légale française.
