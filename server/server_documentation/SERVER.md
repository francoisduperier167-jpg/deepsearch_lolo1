# Server Module

## Responsabilite
Serveur web aiohttp + gestion llama-server + API REST.

## Fichiers
- **server.py** : Assemble les routes, cree l'app aiohttp
- **server_core/state.py** : Singleton AppState (etat global)
- **server_core/gpu_monitor.py** : nvidia-smi → metriques GPU, fallback RAM
- **server_core/llama_manager.py** : start/stop llama-server subprocess
- **server_core/llm_client.py** : Envoi prompt → llama.cpp → parse JSON
- **server_ui/routes.py** : Tous les endpoints HTTP
- **server_ui/index.html** : Interface web

## API Endpoints
| Route | Methode | Description |
|---|---|---|
| / | GET | Interface HTML |
| /api/status | GET | Etat complet (GPU, scan, modele) |
| /api/model/start | POST | Demarre llama-server |
| /api/model/stop | POST | Arrete llama-server |
| /api/scan/start | POST | Lance le scan |
| /api/scan/stop | POST | Arrete le scan |
| /api/results | GET | Resultats actuels |
| /api/export | GET | Export JSON |
| /api/logs | GET | Logs recents |
