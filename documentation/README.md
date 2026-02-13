# YouTube Scout v2 — Architecture

## Arborescence
```
youtube-scout-v2/
├── main.py                              ← Point d'entree unique
├── START.bat                            ← Lanceur Windows (venv + deps + serveur)
│
├── server/                              ← Module serveur web
│   ├── server.py                        ← Assemble les routes en app aiohttp
│   ├── server_core/
│   │   ├── state.py                     ← Etat global (singleton AppState)
│   │   ├── gpu_monitor.py               ← Monitoring VRAM/GPU/CPU/RAM
│   │   ├── llama_manager.py             ← Demarrage/arret llama-server
│   │   └── llm_client.py               ← Envoi prompts → llama.cpp → JSON
│   ├── server_ui/
│   │   ├── routes.py                    ← Endpoints HTTP (API REST)
│   │   └── index.html                   ← Interface web complete
│   └── server_documentation/
│       └── SERVER.md
│
├── pipeline/                            ← Module pipeline de recherche
│   ├── pipeline.py                      ← Orchestrateur (7 phases + resolution)
│   ├── pipeline_core/
│   │   ├── query_generator.py           ← Phase 1: generation requetes
│   │   ├── result_triage.py             ← Phase 3: scoring resultats
│   │   ├── page_extractor.py            ← Phase 4: extraction fragments
│   │   ├── candidate_assembler.py       ← Phase 5: assemblage candidats
│   │   ├── followup_search.py           ← Phase 5b: recherches complementaires
│   │   ├── verification.py              ← Phase 6: verification adversariale
│   │   └── escalation.py               ← Analyse d'echec + escalade
│   ├── pipeline_ui/
│   │   └── progress.py                  ← Callbacks progression → UI
│   └── pipeline_documentation/
│       └── PIPELINE.md
│
├── web_search/                          ← Module recherche web
│   ├── web_search.py                    ← Interface publique (re-exports)
│   ├── web_search_core/
│   │   ├── brave_search.py              ← Brave Search + pagination
│   │   ├── page_fetcher.py              ← Fetch pages + extraction texte
│   │   └── youtube_checker.py           ← Verification chaines YouTube
│   └── web_search_documentation/
│       └── WEB_SEARCH.md
│
├── config/
│   ├── settings.py                      ← Constantes (ports, seuils, limites)
│   └── cities.py                        ← 50 etats × 3 villes + categories
│
├── models/
│   └── data_models.py                   ← Fragment, ChannelCandidate, Resolutions
│
├── utils/
│   ├── logger.py                        ← Logging centralise
│   ├── json_extract.py                  ← Extraction JSON robuste
│   └── rate_limiter.py                  ← Rate limiting web
│
├── prompts/                             ← 1 fichier par prompt LLM
│   ├── strategy_prompt.py               ← Phase 1
│   ├── triage_prompt.py                 ← Phase 3
│   ├── extraction_prompt.py             ← Phase 4
│   ├── assembly_prompt.py               ← Phase 5
│   ├── followup_prompt.py               ← Phase 5b
│   ├── adversarial_prompt.py            ← Phase 6
│   ├── category_prompt.py               ← Phase 6b
│   └── escalation_prompt.py             ← Escalade
│
└── documentation/
    └── README.md                        ← Ce fichier
```

## Pipeline (7 phases)
1. LLM genere requetes multi-angles (presse, Reddit, listes, events...)
2. Brave Search avec pagination (80-100 resultats/requete)
3. LLM score les snippets, selectionne les pages a explorer
4. Fetch pages, LLM extrait fragments (noms, URLs, citations ville)
5. LLM recoupe fragments de sources independantes → candidats
6. Verification YouTube reelle (abonnes, derniere video)
7. LLM fait verification adversariale (avocat du diable)

## Resolution
- Ville resolue = 3 categories resolues (ou echouees apres 3 vagues)
- Etat resolu = 3 villes resolues
- Pas de passage a la ville suivante avant resolution
