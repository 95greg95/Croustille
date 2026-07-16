#!/usr/bin/env python3
"""
Générateur de site statique pour le blog air fryer.

- Convertit content/articles/*.md en pages HTML optimisées SEO
- Remplace les marqueurs {{product:...}} et {{box:...|...}} par des liens
  affiliés Amazon (tag défini dans config.json)
- Génère : accueil, pages catégories, pages légales, sitemap.xml, robots.txt,
  flux RSS, ads.txt, 404
- Injecte les données structurées (Article, FAQPage, BreadcrumbList)
- Intègre Google AdSense (Auto Ads) derrière une bannière de consentement RGPD

Sortie : public/
"""

import html
import json
import re
import shutil
import urllib.parse
from datetime import datetime
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
ARTICLES_DIR = ROOT / "content" / "articles"
STATIC_DIR = ROOT / "static"
OUT = ROOT / "public"

SITE = CONFIG["site_url"].rstrip("/")
TAG = CONFIG["amazon_tag"]
AMAZON = CONFIG["amazon_domain"]
TYPE_LABEL = {"guide": "Guide", "comparatif": "Comparatif", "article": "Conseils", "recette": "Recette"}
TYPE_SLUG = {"guide": "guides", "comparatif": "comparatifs", "article": "conseils", "recette": "recettes"}
TYPE_EMOJI = {"guide": "🎯", "comparatif": "⚖️", "article": "💡", "recette": "🍽️"}

MD = markdown.Markdown(extensions=["extra", "sane_lists", "smarty"])


# ---------------------------------------------------------------- utilitaires

def esc(s: str) -> str:
    return html.escape(s, quote=True)


def amazon_link(product: str) -> str:
    q = urllib.parse.quote_plus(product)
    return f"https://{AMAZON}/s?k={q}&tag={TAG}"


def replace_affiliates(md_text: str) -> str:
    """Transforme les marqueurs produits en liens affiliés."""

    def box(m):
        name, pitch = m.group(1).strip(), m.group(2).strip()
        return (
            f'\n<div class="product-box">'
            f'<p class="product-box-name">{esc(name)}</p>'
            f'<p class="product-box-pitch">{esc(pitch)}</p>'
            f'<a class="product-box-btn" href="{amazon_link(name)}" '
            f'rel="sponsored nofollow noopener" target="_blank">Voir le prix sur Amazon&nbsp;→</a>'
            f'</div>\n'
        )

    def inline(m):
        name = m.group(1).strip()
        return (
            f'<a href="{amazon_link(name)}" rel="sponsored nofollow noopener" '
            f'target="_blank" class="aff-link">{esc(name)}</a>'
        )

    md_text = re.sub(r"\{\{box:([^|{}]+)\|([^{}]+)\}\}", box, md_text)
    md_text = re.sub(r"\{\{product:([^{}]+)\}\}", inline, md_text)
    return md_text


def replace_illustrations(md_text: str) -> str:
    """Transforme {{img:EMOJIS|Légende}} en illustration responsive."""

    def figure(m):
        emojis, caption = m.group(1).strip(), m.group(2).strip()
        variant = (sum(ord(c) for c in caption) % 4) + 1
        return (
            f'\n<figure class="art"><div class="art-canvas art-v{variant}" role="img" '
            f'aria-label="{esc(caption)}"><span class="art-emoji">{esc(emojis)}</span></div>'
            f'<figcaption>{esc(caption)}</figcaption></figure>\n'
        )

    return re.sub(r"\{\{img:([^|{}]+)\|([^{}]+)\}\}", figure, md_text)


def parse_frontmatter(raw: str) -> tuple[dict, str]:
    meta = {}
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
            body = parts[2]
    return meta, body.strip()


def extract_faq(md_text: str) -> list[tuple[str, str]]:
    """Extrait les paires question/réponse de la section ## FAQ pour le JSON-LD."""
    m = re.search(r"^## +FAQ.*?$", md_text, flags=re.M)
    if not m:
        return []
    section = md_text[m.end():]
    stop = re.search(r"^## +", section, flags=re.M)
    if stop:
        section = section[: stop.start()]
    faqs = []
    blocks = re.split(r"^### +", section, flags=re.M)
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        question = lines[0].strip()
        answer = " ".join(l.strip() for l in lines[1:] if l.strip())
        answer = re.sub(r"<[^>]+>", "", answer)
        answer = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", answer)
        answer = re.sub(r"[*_`#]", "", answer)
        if question and answer:
            faqs.append((question, answer))
    return faqs


def reading_time(md_text: str) -> int:
    return max(1, round(len(re.findall(r"\w+", md_text)) / 220))


def slug_anchor(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", t.lower()).strip("-")[:60] or "section"


def add_heading_anchors(html_text: str) -> tuple[str, list[tuple[str, str]]]:
    """Ajoute un id à chaque H2 et retourne la liste (id, titre) pour le sommaire."""
    toc: list[tuple[str, str]] = []
    used: set[str] = set()

    def repl(m):
        inner = m.group(1)
        text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        anchor = slug_anchor(text)
        i = 2
        while anchor in used:
            anchor = f"{slug_anchor(text)}-{i}"
            i += 1
        used.add(anchor)
        toc.append((anchor, text))
        return f'<h2 id="{anchor}">{inner}</h2>'

    html_text = re.sub(r"<h2>(.*?)</h2>", repl, html_text, flags=re.S)
    return html_text, toc


def clean_md_inline(text: str) -> str:
    """Nettoie une ligne markdown : marqueurs produits, gras, liens."""
    text = re.sub(r"\{\{product:([^{}]+)\}\}", r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`]", "", text)
    return text.strip()


def extract_recipe(md_text: str) -> dict | None:
    """Extrait ingrédients, étapes et temps d'un article recette pour le
    balisage Schema.org Recipe (fiches enrichies Google)."""
    def section(pattern):
        m = re.search(rf"^## +{pattern}.*?$", md_text, flags=re.M | re.I)
        if not m:
            return ""
        rest = md_text[m.end():]
        stop = re.search(r"^## +", rest, flags=re.M)
        return rest[: stop.start()] if stop else rest

    ing_section = section(r"Ingr[ée]dients")
    ingredients = [clean_md_inline(x) for x in re.findall(r"^[-*] +(.+)$", ing_section, re.M)]

    steps_section = section(r".*pas [àa] pas") or section(r"Pr[ée]paration")
    steps = [clean_md_inline(x) for x in re.findall(r"^\d+\. +(.+)$", steps_section, re.M)]

    if not ingredients or not steps:
        return None

    total_min = 0
    for lo, hi in re.findall(r"(\d+)(?:\s*(?:à|-)\s*(\d+))?\s*min", section(r"Temps")):
        total_min += int(hi or lo)

    m = re.search(r"pour +(\d+) +personnes", md_text, flags=re.I)
    persons = m.group(1) if m else "4"

    return {
        "ingredients": ingredients,
        "steps": steps,
        "total_min": total_min or None,
        "yield": f"{persons} personnes",
    }


# ------------------------------------------------------------------ gabarits

def adsense_head() -> str:
    """Code AdSense officiel, inséré dans le <head> de TOUTES les pages.
    C'est ce que Google exige pour la validation du site et les Auto Ads.
    La gestion du consentement RGPD est assurée par le CMP de Google
    (AdSense → Confidentialité et messages), à activer dans le compte AdSense."""
    if not CONFIG.get("adsense_enabled") or "XXXX" in CONFIG.get("adsense_client", ""):
        return ""
    client = esc(CONFIG["adsense_client"])
    return (
        f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
        f'?client={client}" crossorigin="anonymous"></script>'
    )


def page_shell(title: str, description: str, canonical: str, content: str,
               jsonld: list[dict] | None = None, noindex: bool = False) -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>'
        for j in (jsonld or [])
    )
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    nav_items = [
        ("/guides/", "Guides"),
        ("/comparatifs/", "Comparatifs"),
        ("/recettes/", "Recettes"),
        ("/conseils/", "Conseils"),
        ("/convertisseur/", "Convertisseur"),
    ]
    nav = "".join(f'<a href="{u}">{l}</a>' for u, l in nav_items)
    year = datetime.now().year
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical}">
{robots}
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="{esc(CONFIG['site_name'])}">
<meta property="og:image" content="{SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta property="og:locale" content="fr_FR">
<link rel="alternate" type="application/rss+xml" title="{esc(CONFIG['site_name'])}" href="{SITE}/rss.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650;9..144,720&family=Public+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
{adsense_head()}
{scripts}
</head>
<body>
<div id="progress" aria-hidden="true"></div>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="logo" href="/" aria-label="{esc(CONFIG['site_name'])} — accueil">
      <svg class="logo-mark" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 15c2.5-1.5 4-4.5 3-7 3 .5 5 3 5 6 1.5-1 2.5-2.8 2.5-5C17.5 11 20 13 20 16a8 8 0 0 1-16 0v-1z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
      <span>{esc(CONFIG['site_name'])}<em>°</em></span>
    </a>
    <nav class="site-nav" aria-label="Navigation principale">{nav}
      <button id="search-btn" class="search-btn" aria-label="Rechercher sur le site" title="Rechercher (Ctrl+K)">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m16.5 16.5 4.5 4.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      </button>
    </nav>
  </div>
</header>
<main class="wrap">
{content}
</main>
<script src="/app.js" defer></script>
<footer class="site-footer">
  <div class="wrap">
    <p class="footer-disclosure">En tant que Partenaire Amazon, {esc(CONFIG['site_name'])} réalise un bénéfice sur les achats remplissant les conditions requises. Les liens produits de ce site sont des liens affiliés.</p>
    <nav class="footer-nav">
      <a href="/a-propos/">À propos</a>
      <a href="/mentions-legales/">Mentions légales</a>
      <a href="/confidentialite/">Politique de confidentialité</a>
      <a href="/rss.xml">Flux RSS</a>
    </nav>
    <p class="footer-copy">© {year} {esc(CONFIG['site_name'])} — {esc(CONFIG['site_tagline'])}</p>
  </div>
</footer>
</body>
</html>"""


def card(article: dict) -> str:
    d = datetime.fromisoformat(article["date"])
    return f"""<article class="card">
  <p class="card-badge badge-{article['type']}">{TYPE_LABEL[article['type']]}</p>
  <h2 class="card-title"><a href="{article['url']}">{esc(article['title'])}</a></h2>
  <p class="card-desc">{esc(article['description'])}</p>
  <p class="card-meta"><time datetime="{article['date']}">{d.strftime('%d/%m/%Y')}</time> · {article['minutes']} min de lecture</p>
</article>"""


# --------------------------------------------------------------- construction

def load_articles() -> list[dict]:
    articles = []
    for f in sorted(ARTICLES_DIR.glob("*.md"), reverse=True):
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)\.md$", f.name)
        if not m:
            continue
        pub_date, slug = m.group(1), m.group(2)
        meta, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        body_aff = replace_illustrations(replace_affiliates(body))
        MD.reset()
        html_body, toc = add_heading_anchors(MD.convert(body_aff))
        articles.append({
            "slug": slug,
            "emoji": meta.get("emoji", "").strip(),
            "date": pub_date,
            "title": meta.get("title", slug.replace("-", " ").capitalize()),
            "description": meta.get("description", ""),
            "keywords": meta.get("keywords", ""),
            "type": meta.get("type", "article"),
            "faq": extract_faq(body),
            "recipe": extract_recipe(body) if meta.get("type") == "recette" else None,
            "minutes": reading_time(body),
            "html": html_body,
            "toc": toc,
            "url": f"/{slug}/",
        })
    return articles


def render_article(a: dict, all_articles: list[dict]) -> str:
    d = datetime.fromisoformat(a["date"])
    label = TYPE_LABEL[a["type"]]
    cat_url = f"/{TYPE_SLUG[a['type']]}/"

    related = [x for x in all_articles if x["slug"] != a["slug"] and x["type"] == a["type"]]
    related += [x for x in all_articles if x["slug"] != a["slug"] and x not in related]
    related = related[:3]
    related_html = ""
    if related:
        related_html = (
            '<aside class="related"><h2>À lire aussi</h2><div class="card-grid">'
            + "".join(card(r) for r in related)
            + "</div></aside>"
        )

    jsonld = [
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": a["title"],
            "description": a["description"],
            "datePublished": a["date"],
            "dateModified": a["date"],
            "inLanguage": "fr-FR",
            "author": {"@type": "Organization", "name": CONFIG["author"]},
            "publisher": {"@type": "Organization", "name": CONFIG["site_name"]},
            "mainEntityOfPage": SITE + a["url"],
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Accueil", "item": SITE + "/"},
                {"@type": "ListItem", "position": 2, "name": label, "item": SITE + cat_url},
                {"@type": "ListItem", "position": 3, "name": a["title"], "item": SITE + a["url"]},
            ],
        },
    ]
    if a["faq"]:
        jsonld.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": q,
                    "acceptedAnswer": {"@type": "Answer", "text": ans},
                }
                for q, ans in a["faq"]
            ],
        })
    if a.get("recipe"):
        r = a["recipe"]
        recipe_ld = {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": a["title"],
            "description": a["description"],
            "image": [SITE + "/og-image.png"],
            "datePublished": a["date"],
            "author": {"@type": "Organization", "name": CONFIG["author"]},
            "recipeIngredient": r["ingredients"],
            "recipeInstructions": [
                {"@type": "HowToStep", "text": s} for s in r["steps"]
            ],
            "recipeYield": r["yield"],
            "recipeCuisine": "Française",
            "recipeCategory": "Air fryer",
            "keywords": a["keywords"],
            "inLanguage": "fr-FR",
        }
        if r["total_min"]:
            recipe_ld["totalTime"] = f"PT{r['total_min']}M"
        jsonld.append(recipe_ld)

    hero_emoji = a.get("emoji") or TYPE_EMOJI.get(a["type"], "🍟")
    hero_variant = (sum(ord(c) for c in a["slug"]) % 4) + 1

    toc_html = ""
    if len(a["toc"]) >= 3:
        items = "".join(f'<li><a href="#{i}">{esc(t)}</a></li>' for i, t in a["toc"])
        toc_html = (
            '<details class="toc" open><summary>Sommaire</summary>'
            f'<ol>{items}</ol></details>'
        )

    content = f"""<nav class="breadcrumb" aria-label="Fil d'Ariane">
  <a href="/">Accueil</a> › <a href="{cat_url}">{label}</a>
</nav>
<article class="post">
  <div class="post-hero art-v{hero_variant}" aria-hidden="true"><span class="art-emoji">{esc(hero_emoji)}</span></div>
  <header class="post-header">
    <p class="card-badge badge-{a['type']}">{label}</p>
    <h1>{esc(a['title'])}</h1>
    <p class="post-meta">Publié le <time datetime="{a['date']}">{d.strftime('%d/%m/%Y')}</time> · {a['minutes']} min de lecture · Par {esc(CONFIG['author'])}</p>
    {'<button id="print-btn" class="print-btn" type="button">🖨️ Imprimer la recette</button>' if a.get("recipe") else ''}
  </header>
  <p class="disclosure">Cet article contient des liens affiliés Amazon : si vous achetez via ces liens, nous touchons une commission, sans surcoût pour vous. C'est ce qui finance nos tests et guides. <a href="/a-propos/">En savoir plus</a>.</p>
  {toc_html}
  <div class="post-body">
{a['html']}
  </div>
</article>
{related_html}"""
    return page_shell(
        f"{a['title']} | {CONFIG['site_name']}",
        a["description"] or CONFIG["site_description"],
        SITE + a["url"],
        content,
        jsonld,
    )


def render_listing(title: str, description: str, url_path: str,
                   articles: list[dict], intro: str) -> str:
    grid = "".join(card(a) for a in articles) or "<p>Les premiers articles arrivent très vite !</p>"
    content = f"""<header class="page-header">
  <h1>{esc(title)}</h1>
  <p class="page-intro">{intro}</p>
</header>
<div class="card-grid">{grid}</div>"""
    jsonld = [{
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": SITE + url_path,
        "inLanguage": "fr-FR",
    }]
    return page_shell(f"{title} | {CONFIG['site_name']}", description,
                      SITE + url_path, content, jsonld)


def render_index(articles: list[dict]) -> str:
    hero = ""
    rest = articles
    if articles:
        a = articles[0]
        rest = articles[1:]
        hero = f"""<section class="hero">
  <p class="hero-eyebrow">Dernier article · {TYPE_LABEL[a['type']]}</p>
  <h1 class="hero-title"><a href="{a['url']}">{esc(a['title'])}</a></h1>
  <p class="hero-desc">{esc(a['description'])}</p>
  <a class="hero-btn" href="{a['url']}">Lire l'article →</a>
</section>"""
    grid = "".join(card(a) for a in rest[:12])
    content = f"""{hero}
<section>
  <h2 class="section-title">Tous nos guides &amp; comparatifs</h2>
  <div class="card-grid">{grid}</div>
</section>"""
    jsonld = [{
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": CONFIG["site_name"],
        "url": SITE + "/",
        "description": CONFIG["site_description"],
        "inLanguage": "fr-FR",
    }]
    return page_shell(
        f"{CONFIG['site_name']} — {CONFIG['site_tagline']}",
        CONFIG["site_description"], SITE + "/", content, jsonld,
    )


def render_converter() -> str:
    content = """<article class="post">
  <header class="post-header">
    <h1>Convertisseur four → air fryer</h1>
    <p class="page-intro">Adaptez n'importe quelle recette au four pour votre air fryer : entrez la température et le temps indiqués dans la recette, l'outil calcule les réglages équivalents.</p>
  </header>
  <div class="conv" id="conv">
    <div class="conv-grid">
      <label>Température de la recette au four
        <input type="number" id="conv-temp" min="80" max="280" step="5" value="200" inputmode="numeric"> °C
      </label>
      <label>Temps de cuisson au four
        <input type="number" id="conv-time" min="1" max="240" step="1" value="30" inputmode="numeric"> min
      </label>
      <label>Type de four de la recette
        <select id="conv-type">
          <option value="statique">Four traditionnel (statique)</option>
          <option value="tournante">Four à chaleur tournante</option>
        </select>
      </label>
    </div>
    <div class="conv-result" id="conv-result" aria-live="polite"></div>
    <p class="conv-note">⚠️ Ces valeurs sont un point de départ fiable, mais chaque appareil varie : vérifiez la cuisson 2-3 minutes avant la fin la première fois, vous pourrez toujours prolonger.</p>
  </div>
  <div class="post-body">
    <h2>Comment fonctionne cette conversion ?</h2>
    <p>Un air fryer est un petit four à convection très puissant : l'air chaud circule vite dans une cavité réduite, ce qui accélère les transferts de chaleur. La règle éprouvée : <strong>par rapport à un four traditionnel, baissez la température d'environ 30 °C et réduisez le temps de 20 %</strong>. Par rapport à un four à chaleur tournante (déjà ventilé), une baisse de 20 °C suffit.</p>
    <h2>Repères rapides pour les cuissons courantes</h2>
    <table>
      <tr><th>Plat</th><th>Au four</th><th>À l'air fryer</th></tr>
      <tr><td>Frites surgelées</td><td>220 °C · 25 min</td><td>190 °C · 15-18 min</td></tr>
      <tr><td>Blanc de poulet</td><td>200 °C · 25 min</td><td>170 °C · 18-20 min</td></tr>
      <tr><td>Légumes rôtis</td><td>200 °C · 35 min</td><td>180 °C · 20-25 min</td></tr>
      <tr><td>Poisson pané</td><td>210 °C · 20 min</td><td>190 °C · 12-14 min</td></tr>
      <tr><td>Gâteau / moelleux</td><td>180 °C · 30 min</td><td>150-160 °C · 22-25 min</td></tr>
    </table>
    <p>Trois réflexes complètent la conversion : cuisez en une seule couche, secouez ou retournez à mi-cuisson, et n'ouvrez pas le tiroir toutes les deux minutes. Pour aller plus loin, consultez nos <a href="/recettes/">recettes calibrées pour l'air fryer</a> et nos <a href="/conseils/">conseils de cuisson</a>.</p>
  </div>
</article>"""
    jsonld = [{
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Convertisseur four → air fryer",
        "description": "Convertissez les températures et temps de cuisson du four traditionnel vers l'air fryer.",
        "url": SITE + "/convertisseur/",
        "inLanguage": "fr-FR",
    }]
    return page_shell(
        f"Convertisseur four → air fryer : températures et temps | {CONFIG['site_name']}",
        "Adaptez n'importe quelle recette au four pour votre air fryer : notre convertisseur calcule la température et le temps équivalents, avec tableau de repères.",
        SITE + "/convertisseur/", content, jsonld,
    )


def static_page(title: str, path: str, body_md: str, noindex: bool = False) -> str:
    MD.reset()
    content = f'<article class="post"><header class="post-header"><h1>{esc(title)}</h1></header><div class="post-body">{MD.convert(body_md)}</div></article>'
    return page_shell(f"{title} | {CONFIG['site_name']}", CONFIG["site_description"],
                      SITE + path, content, noindex=noindex)


LEGAL_MENTIONS = """
**Éditeur du site** : [VOTRE NOM OU RAISON SOCIALE] — [VOTRE ADRESSE] — Contact : [VOTRE EMAIL]

**Directeur de la publication** : [VOTRE NOM]

**Hébergement** : Netlify, Inc. — 512 2nd Street, Suite 200, San Francisco, CA 94107, États-Unis — [netlify.com](https://www.netlify.com)

**Propriété intellectuelle** : l'ensemble des contenus de ce site (textes, illustrations, logo) est protégé par le droit d'auteur. Toute reproduction sans autorisation est interdite.

**Programme Partenaires Amazon** : ce site participe au Programme Partenaires d'Amazon EU, un programme d'affiliation conçu pour permettre à des sites de percevoir une rémunération grâce à la création de liens vers Amazon.fr. En tant que Partenaire Amazon, nous réalisons un bénéfice sur les achats remplissant les conditions requises.

**Responsabilité** : les informations publiées le sont à titre informatif. Les caractéristiques et prix des produits mentionnés sont susceptibles d'évoluer ; référez-vous toujours à la fiche produit du marchand avant tout achat.
"""

LEGAL_PRIVACY = """
Dernière mise à jour : {date}

### Données collectées

Ce site ne collecte aucune donnée personnelle directement : pas de compte, pas de formulaire, pas de newsletter à ce jour.

### Cookies et publicité

Ce site peut afficher des annonces fournies par **Google AdSense**. Google et ses partenaires utilisent des cookies pour diffuser des annonces, y compris des annonces personnalisées en fonction de vos visites sur ce site et d'autres sites. Vous pouvez configurer vos préférences publicitaires sur la page [Paramètres des annonces de Google](https://adssettings.google.com/) et en savoir plus sur l'utilisation des données par Google sur [policies.google.com/technologies/partner-sites](https://policies.google.com/technologies/partner-sites).

Lors de votre première visite, une bannière vous permet d'accepter ou de refuser le dépôt de ces cookies. Aucun cookie publicitaire n'est déposé sans votre consentement. Vous pouvez retirer votre consentement à tout moment en effaçant les cookies de votre navigateur.

### Liens d'affiliation Amazon

Les liens vers Amazon présents sur ce site contiennent un identifiant de partenaire. Amazon peut déposer des cookies lors de votre clic afin d'attribuer la commission. Consultez la [politique de confidentialité d'Amazon](https://www.amazon.fr/gp/help/customer/display.html?nodeId=201909010) pour plus d'informations.

### Mesure d'audience

Si un outil de mesure d'audience est utilisé, il est configuré en mode anonymisé ou exempté de consentement selon les recommandations de la CNIL.

### Vos droits

Conformément au RGPD, vous disposez d'un droit d'accès, de rectification et d'effacement de vos données. Contact : [VOTRE EMAIL].
"""

ABOUT = """
**{site}** est un blog indépendant entièrement consacré aux air fryers (friteuses sans huile) : guides d'achat, comparatifs détaillés, recettes, temps de cuisson et conseils d'entretien.

### Notre mission

Vous aider à choisir le bon appareil du premier coup, puis à en tirer le meilleur au quotidien — sans jargon, avec des explications claires et des recommandations honnêtes.

### Comment nous nous finançons

Ce site est gratuit. Il est financé par deux moyens, toujours signalés :

- **Des liens affiliés Amazon** : quand vous achetez un produit via l'un de nos liens, Amazon nous verse une petite commission, sans aucun surcoût pour vous. Cela n'influence jamais notre avis : nous recommandons un produit parce qu'il le mérite, pas l'inverse.
- **De la publicité** : des annonces peuvent être affichées via Google AdSense.

### Une question, une remarque ?

Écrivez-nous : [VOTRE EMAIL]. Nous lisons tout.
"""


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # Fichiers statiques
    for f in STATIC_DIR.glob("*"):
        shutil.copy(f, OUT / f.name)

    articles = load_articles()
    print(f"{len(articles)} article(s) trouvé(s).")

    # Articles
    for a in articles:
        d = OUT / a["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(render_article(a, articles), encoding="utf-8")

    # Accueil
    (OUT / "index.html").write_text(render_index(articles), encoding="utf-8")

    # Catégories
    cats = [
        ("guide", "Guides d'achat air fryer",
         "Nos guides complets pour bien choisir et bien utiliser votre air fryer.",
         "Capacité, puissance, budget, usages : tout ce qu'il faut savoir avant d'acheter, expliqué simplement."),
        ("comparatif", "Comparatifs d'air fryers",
         "Nos comparatifs détaillés des meilleurs air fryers du marché.",
         "Modèle par modèle, marque par marque : nos verdicts clairs pour chaque profil et chaque budget."),
        ("recette", "Recettes à l'air fryer",
         "Nos recettes à l'air fryer pas à pas : temps, températures et astuces pour tout réussir.",
         "Viandes, poissons, légumes, desserts : des recettes détaillées avec temps et températures précis, testées pour la friteuse à air chaud."),
        ("article", "Conseils & astuces air fryer",
         "Temps de cuisson, astuces et entretien : nos conseils pratiques air fryer.",
         "Des articles pratiques et actionnables pour tirer le meilleur de votre friteuse à air chaud au quotidien."),
    ]
    for t, title, desc, intro in cats:
        d = OUT / TYPE_SLUG[t]
        d.mkdir(parents=True, exist_ok=True)
        arts = [a for a in articles if a["type"] == t]
        (d / "index.html").write_text(
            render_listing(title, desc, f"/{TYPE_SLUG[t]}/", arts, intro), encoding="utf-8")

    # Pages statiques
    pages = [
        ("À propos", "a-propos", ABOUT.format(site=CONFIG["site_name"]), False),
        ("Mentions légales", "mentions-legales", LEGAL_MENTIONS, True),
        ("Politique de confidentialité", "confidentialite",
         LEGAL_PRIVACY.format(date=datetime.now().strftime("%d/%m/%Y")), True),
    ]
    for title, slug, body, noindex in pages:
        d = OUT / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(static_page(title, f"/{slug}/", body, noindex), encoding="utf-8")

    # Convertisseur four → air fryer
    d = OUT / "convertisseur"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(render_converter(), encoding="utf-8")

    # 404
    (OUT / "404.html").write_text(
        static_page("Page introuvable", "/404.html",
                    "Cette page n'existe pas (ou plus). [Retour à l'accueil](/) pour retrouver tous nos guides.",
                    noindex=True),
        encoding="utf-8")

    # robots.txt
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")

    # sitemap.xml
    urls = [("/", None)] + [(f"/{TYPE_SLUG[t]}/", None) for t, *_ in cats] \
        + [("/a-propos/", None), ("/convertisseur/", None)] + [(a["url"], a["date"]) for a in articles]
    entries = "".join(
        f"<url><loc>{SITE}{u}</loc>{f'<lastmod>{d}</lastmod>' if d else ''}</url>"
        for u, d in urls
    )
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>',
        encoding="utf-8")

    # RSS
    items = "".join(
        f"<item><title>{esc(a['title'])}</title><link>{SITE}{a['url']}</link>"
        f"<guid>{SITE}{a['url']}</guid><pubDate>{datetime.fromisoformat(a['date']).strftime('%a, %d %b %Y 06:00:00 GMT')}</pubDate>"
        f"<description>{esc(a['description'])}</description></item>"
        for a in articles[:20]
    )
    (OUT / "rss.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{esc(CONFIG['site_name'])}</title><link>{SITE}/</link>"
        f"<description>{esc(CONFIG['site_description'])}</description>"
        f"<language>fr-FR</language>{items}</channel></rss>",
        encoding="utf-8")

    # Index de recherche interne
    search_index = [
        {
            "t": a["title"],
            "d": a["description"],
            "k": a["keywords"],
            "u": a["url"],
            "c": TYPE_LABEL[a["type"]],
        }
        for a in articles
    ]
    (OUT / "search-index.json").write_text(
        json.dumps(search_index, ensure_ascii=False), encoding="utf-8")

    # ads.txt (requis par AdSense)
    if CONFIG.get("adsense_enabled") and "XXXX" not in CONFIG.get("adsense_client", ""):
        pub = CONFIG["adsense_client"].replace("ca-", "")
        (OUT / "ads.txt").write_text(
            f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")

    print(f"Site généré dans {OUT} ({len(list(OUT.rglob('*.html')))} pages HTML).")


if __name__ == "__main__":
    main()
