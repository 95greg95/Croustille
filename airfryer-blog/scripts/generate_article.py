#!/usr/bin/env python3
"""
Générateur quotidien d'articles SEO pour le blog air fryer.

- Prend le prochain sujet non traité dans content/topics.json
- Génère un article de ~2500 mots via l'API Anthropic
- Les produits sont marqués {{product:Nom}} / {{box:Nom|Accroche}} dans le
  markdown : c'est le script de build qui les transforme en liens affiliés
  (ainsi, changer de tag Amazon met à jour tout le site d'un coup).
- Sauvegarde dans content/articles/AAAA-MM-JJ-slug.md

Nécessite la variable d'environnement ANTHROPIC_API_KEY.
"""

import json
import os
import re
import sys
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
TOPICS_FILE = ROOT / "content" / "topics.json"
ARTICLES_DIR = ROOT / "content" / "articles"

API_URL = "https://api.anthropic.com/v1/messages"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text[:80]


def existing_titles() -> list[str]:
    titles = []
    for f in sorted(ARTICLES_DIR.glob("*.md")):
        for line in f.read_text(encoding="utf-8").splitlines()[:10]:
            if line.startswith("title:"):
                titles.append(line.split(":", 1)[1].strip())
                break
    return titles


def next_topic(topics: dict) -> dict | None:
    """Prochain sujet non traité. Si un article avec le même slug existe déjà
    (sujet régénéré ou fichier topics.json remplacé), on le marque comme fait
    et on passe au suivant — aucun doublon ne sera jamais publié."""
    existing_slugs = {
        re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", f.name).group(1)
        for f in ARTICLES_DIR.glob("*.md")
        if re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", f.name)
    }
    for t in topics["topics"]:
        if t.get("done"):
            continue
        if slugify(t["title"]) in existing_slugs:
            t["done"] = True
            continue
        return t
    return None


def build_prompt(topic: dict) -> str:
    type_details = {
        "guide": (
            "un GUIDE pédagogique et concis. Structure : introduction accrocheuse, "
            "puis 4 à 6 sections H2 qui couvrent l'essentiel du sujet (critères, "
            "explications techniques vulgarisées, cas d'usage, erreurs à éviter), "
            "avec des recommandations de produits précis là où c'est pertinent."
        ),
        "comparatif": (
            "un COMPARATIF détaillé. Structure : introduction, tableau comparatif "
            "markdown des modèles (colonnes : Modèle, Capacité, Puissance, Points forts, "
            "Pour qui ?), puis une section H2 par produit (3 à 5 produits réels et "
            "actuels) avec avis concis, points forts, points faibles, et un bloc "
            "{{box:...}} par produit. Terminer par un verdict clair par profil "
            "d'utilisateur (meilleur rapport qualité/prix, meilleur haut de gamme, etc.)."
        ),
        "article": (
            "un ARTICLE PRATIQUE et actionnable (astuces, méthodes, entretien). "
            "Structure : introduction, étapes ou listes détaillées en H2/H3, temps et "
            "températures précis quand il s'agit de cuisson, astuces d'expert, "
            "et 1 à 3 recommandations de produits ou accessoires en contexte."
        ),
        "recette": (
            "une RECETTE COMPLÈTE pas à pas. Structure : introduction appétissante (pourquoi "
            "cette recette marche si bien à l'air fryer), une section '## Ingrédients' avec "
            "liste à puces et quantités pour 4 personnes, une section '## Temps et température' "
            "avec un petit tableau markdown (Étape, Température, Durée), une section "
            "'## La recette pas à pas' avec les étapes numérotées très détaillées, puis des "
            "sections H2 : astuces de réussite, variantes, erreurs à éviter, conservation et "
            "réchauffage. Donne TOUJOURS des températures et durées précises et réalistes."
        ),
    }

    return f"""Tu es un rédacteur SEO expert et un passionné de cuisine à l'air fryer. Tu écris pour « {CONFIG['site_name']} », un blog français de référence sur les air fryers.

RÉDIGE {type_details[topic['type']]}

SUJET : {topic['title']}
MOT-CLÉ PRINCIPAL : {topic['keyword']}
LONGUEUR IMPÉRATIVE : entre 400 et 1000 mots, JAMAIS plus de 1000 mots. Vise environ {min(int(CONFIG.get('target_word_count', 800)), 900)} mots. Va droit au but : pas de remplissage, pas de répétitions, chaque phrase doit apporter une information. Mieux vaut un article de 600 mots dense qu'un article de 1000 mots dilué.

RÈGLES SEO IMPÉRATIVES :
- Le mot-clé principal apparaît dans le titre, dans les 100 premiers mots, dans au moins 2 sous-titres H2, et naturellement dans le texte (sans bourrage).
- Utilise des variantes sémantiques (friteuse sans huile, friteuse à air, cuisson à air chaud...).
- Sous-titres H2 (##) et H3 (###) descriptifs qui répondent à de vraies questions.
- Paragraphes courts (3-5 phrases), listes à puces quand c'est pertinent, un tableau markdown si utile.
- Termine par une section « ## FAQ » avec 3 ou 4 questions en H3 (###) suivies chacune d'une réponse de 2-4 phrases. Ces questions doivent correspondre à de vraies recherches Google.
- Après la FAQ, une courte conclusion « ## Le mot de la fin » avec un appel à l'action doux.
- Ton : expert mais accessible, chaleureux, français naturel. Tutoiement interdit, vouvoie le lecteur.
- N'invente JAMAIS de prix précis ni de notes chiffrées de tests que tu n'as pas réalisés. Reste sur les caractéristiques connues des produits.

LIENS AFFILIÉS (très important) :
- Quand tu mentionnes un produit précis achetable (ex. Ninja Foodi MAX Dual Zone AF400EU, Philips Airfryer 5000 XXL, Cosori Turbo Blaze, Moulinex Easy Fry...), écris-le sous la forme : {{{{product:Nom exact du produit}}}}
- Pour mettre en avant un produit recommandé, insère sur une ligne seule un bloc : {{{{box:Nom exact du produit|Une phrase d'accroche qui résume pourquoi on le recommande}}}}
- Utilise entre 2 et 5 marqueurs {{{{product:...}}}} par article, placés naturellement, et 1 à 2 blocs {{{{box:...}}}} selon le type d'article.
- Ne mets JAMAIS d'URL Amazon toi-même : uniquement ces marqueurs.

ILLUSTRATIONS :
- Insère 1 à 2 marqueurs d'illustration dans l'article, chacun sur une ligne seule, entre deux sections : {{{{img:2 ou 3 émojis représentant le contenu|Une légende courte et concrète}}}}
- Exemple : {{{{img:🍗🔥|Le poulet ressort doré et croustillant après 25 minutes à 180 °C}}}}
- Choisis des émojis directement liés au sujet (aliments, ustensiles, feu, minuteur...). Jamais dans un titre ni dans un paragraphe : toujours sur une ligne seule.

FORMAT DE SORTIE — réponds UNIQUEMENT avec ce document markdown, sans préambule ni commentaire :

---
title: [Titre SEO percutant, 50-65 caractères si possible, contenant le mot-clé]
description: [Meta description de 140-155 caractères, incitative, contenant le mot-clé]
keywords: [5-8 mots-clés séparés par des virgules]
type: {topic['type']}
emoji: [2 émojis représentant le sujet, ex. 🍟🔥]
---

[Le corps de l'article en markdown, en commençant directement par le paragraphe d'introduction, SANS répéter le titre en H1]

Titres déjà publiés sur le blog (ne les duplique pas, mais tu peux y faire allusion) :
{chr(10).join('- ' + t for t in existing_titles()[-15:]) or '- (aucun)'}"""


def call_claude(prompt: str) -> str:
    payload = {
        "model": CONFIG.get("anthropic_model", "claude-sonnet-4-6"),
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def sanitize(md: str, topic: dict) -> str:
    md = md.strip()
    # Retire d'éventuelles clôtures ```markdown
    md = re.sub(r"^```(?:markdown)?\s*", "", md)
    md = re.sub(r"\s*```$", "", md)
    # Garantit la présence du frontmatter
    if not md.startswith("---"):
        md = (
            f"---\ntitle: {topic['title']}\n"
            f"description: {topic['title']} : le guide complet sur {CONFIG['site_name']}.\n"
            f"keywords: {topic['keyword']}\ntype: {topic['type']}\n---\n\n" + md
        )
    return md + "\n"


def main() -> int:
    if not API_KEY:
        print("ERREUR : la variable d'environnement ANTHROPIC_API_KEY est absente.", file=sys.stderr)
        return 1

    topics = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    topic = next_topic(topics)
    if topic is None:
        TOPICS_FILE.write_text(
            json.dumps(topics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Tous les sujets ont été traités. Ajoutez de nouveaux sujets dans content/topics.json.")
        return 0

    print(f"Génération : [{topic['type']}] {topic['title']}")
    article = sanitize(call_claude(build_prompt(topic)), topic)

    words = len(re.findall(r"\w+", article))
    print(f"Article généré : {words} mots.")
    if words < 300:
        print("ERREUR : article anormalement court, abandon (le sujet reste dans la file).", file=sys.stderr)
        return 1

    slug = slugify(topic["title"])
    filename = f"{date.today().isoformat()}-{slug}.md"
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    (ARTICLES_DIR / filename).write_text(article, encoding="utf-8")
    print(f"Écrit : content/articles/{filename}")

    topic["done"] = True
    topic["published"] = date.today().isoformat()
    TOPICS_FILE.write_text(
        json.dumps(topics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
