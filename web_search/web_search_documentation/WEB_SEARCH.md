# Web Search Module

## Responsabilite
Toutes les interactions HTTP avec le web externe (Brave, pages, YouTube).

## Fichiers
- **web_search.py** : Interface publique (re-exporte les fonctions)
- **web_search_core/brave_search.py** : Brave Search avec pagination (4 pages = ~80 resultats)
- **web_search_core/page_fetcher.py** : Fetch page → texte + URLs YouTube
- **web_search_core/youtube_checker.py** : Visite chaine YouTube → abonnes, derniere video

## Rate Limiting
Toutes les requetes passent par utils/rate_limiter.py :
- 2-4s entre chaque requete (global)
- 5s minimum entre requetes au meme domaine
- Gestion 429 (rate limited) avec retry apres 60s
