# Pipeline Module

## Responsabilite
Orchestration des 7 phases de recherche + logique de resolution.

## Fichiers
- **pipeline.py** : Orchestrateur principal (process_state → process_city → process_category_wave)
- **pipeline_core/query_generator.py** : Phase 1 — LLM genere requetes multi-angles
- **pipeline_core/result_triage.py** : Phase 3 — LLM score les snippets (0-10)
- **pipeline_core/page_extractor.py** : Phase 4 — LLM extrait fragments des pages
- **pipeline_core/candidate_assembler.py** : Phase 5 — LLM recoupe fragments en candidats
- **pipeline_core/followup_search.py** : Phase 5b — Recherches ciblees pour candidats incomplets
- **pipeline_core/verification.py** : Phase 6 — Verification adversariale ville + categorie
- **pipeline_core/escalation.py** : Analyse echec + recommandations nouvelle strategie
- **pipeline_ui/progress.py** : Callbacks pour mettre a jour l'interface

## Logique de resolution
```
Pour chaque etat:
  Pour chaque ville (bloquant):
    Pour chaque categorie:
      Wave 1: requetes → Brave → triage → fetch → extract → assemble → verify
      Si echec → escalation → Wave 2 (strategie differente)
      Si echec → escalation → Wave 3
      Si echec → marque FAILED
    Ville resolue quand 3 categories done
  Etat resolu quand 3 villes done
```
