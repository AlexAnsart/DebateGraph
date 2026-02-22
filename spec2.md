# DebateGraph — Real-Time Argumentative Analysis Engine

*From Speech to Structured Logic*

**Alexandre** | February 2026 | v0.2 — Design Document

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Globale](#2-architecture-globale)
3. [Stack Technique & Choix Technologiques](#3-stack-technique--choix-technologiques)
4. [Features Détaillées](#4-features-détaillées)
5. [Visualisation Dynamique](#5-visualisation-dynamique)
6. [Stratégie de Développement](#6-stratégie-de-développement)
7. [Différenciation et Positionnement](#7-différenciation-et-positionnement)
8. [Configuration et Secrets](#8-configuration-et-secrets)
9. [Extensions Futures](#9-extensions-futures)

---

## 1. Executive Summary

DebateGraph est un moteur d'analyse argumentative temps réel qui transforme un flux audio de débat en un graphe logique interactif. Le système combine la reconnaissance vocale (speaker diarization + STT), l'extraction d'arguments via LLM, la détection automatisée de fallacies, le fact-checking asynchrone, et une visualisation dynamique sous forme de graphe orienté.

L'objectif n'est pas de remplacer le jugement humain mais d'agir comme un **co-pilote épistémique** : le système structure, vérifie et interroge les arguments, tout en laissant l'utilisateur maître de son interprétation.

**Positionnement :** L'écosystème actuel est fragmenté entre des architectures industrielles massives (IBM Project Debater), des outils de visualisation légers (Argdown, Kialo), et des réseaux de fact-checking participatifs (CaptainFact). DebateGraph intègre ces trois dimensions dans un pipeline unifié, portable et open-source.

---

## 2. Architecture Globale

Le système suit une architecture multi-agents événementielle, inspirée des frameworks OWL/CAMEL-AI et du standard MCP (Model Context Protocol). Plutôt qu'un modèle monolithique, chaque responsabilité est déléguée à un agent spécialisé orchestré par un routeur d'intention central.

### 2.1 Pipeline principal : Audio → Argument Graph → Analyse

Le pipeline se décompose en cinq étapes séquentielles. Deux modes d'entrée sont supportés : **microphone** (temps réel) et **import de fichier** (batch). La logique d'analyse est identique dans les deux cas ; seul le mécanisme d'ingestion diffère.

| # | Étape | Input → Output | Tech |
|---|-------|----------------|------|
| 1 | Speaker Diarization | Audio brut → Segments timestampés par speaker | pyannote/community-1 (pyannote.audio 4.0) |
| 2 | Speech-to-Text | Segments audio → Texte transcrit par speaker | faster-whisper `large-v3-turbo` (local) |
| 3 | Claim Extraction | Texte transcrit → Claims unitaires typés (prémisse, conclusion, concession, réfutation) | Claude API (structured outputs) |
| 4 | Graph Construction | Claims → Graphe orienté avec arêtes typées (supporte, contredit, reformule, implique) | NetworkX + Claude API pour inférence des relations |
| 5 | Multi-Agent Analysis | Graphe → Annotations (fallacies, fact-checks, scores, cycles) | Agents spécialisés (voir §4) |

**Choix architectural clé :** contrairement à IBM Project Debater qui utilisait un pipeline séquentiel en cascade (segmentation → classification → relation), notre approche privilégie un modèle end-to-end pour les étapes 3–4. Le LLM reçoit un segment de transcription complet et produit simultanément les claims, leurs types, et les relations inter-claims. Cela évite le problème de propagation d'erreurs en cascade documenté dans la littérature.

#### Mode fichier vs. mode microphone

```
Mode fichier :
  [Upload fichier audio/vidéo]
       ↓
  [ffmpeg → WAV 16kHz mono]
       ↓
  [WhisperX : diarization + STT en un seul pass]
       ↓
  [Pipeline d'analyse (étapes 3–5)]
       ↓
  [Graphe complet + visualisation avec waveform playback]

Mode microphone :
  [Web Audio API → chunks 5s avec overlap]
       ↓ (WebSocket)
  [faster-whisper streaming + pyannote VAD]
       ↓
  [Pipeline d'analyse (étapes 3–5) en continu]
       ↓
  [Graphe mis à jour en temps réel]
```

### 2.2 Architecture multi-agents

Un routeur d'intention central distribue de manière asynchrone les claims extraits vers un consortium de quatre agents spécialisés. Chaque agent opère indépendamment et écrit ses annotations dans le graphe partagé via une file Redis Streams.

- **Agent Ontologique (Structurel) :** responsable de la conversion des claims en nœuds AIF (Argument Interchange Format), de l'identification des Argumentative Discourse Units et de la construction du graphe d'ancrage inférentiel. C'est le seul agent qui modifie la topologie du graphe.

- **Agent Sceptique (Fallacy Hunter) :** modèle fine-tuné (~120M paramètres) sur le corpus LOGIC (2 449 échantillons, 13 types de fallacies). Agit comme moniteur de runtime rapide. Ne déclenche un LLM génératif (plus lent, plus précis) que lors de la détection d'une anomalie, pour préserver la latence globale.

- **Agent Chercheur (Fact-Checker) :** pour chaque claim factuel (distingué des claims d'opinion par l'Agent Ontologique), lance une recherche asynchrone via web search API. Retourne un verdict structuré avec sources. Opère de manière découplée du pipeline principal pour ne pas bloquer le temps réel.

- **Agent Prosodique (Emotion Analyzer) :** analyse le signal audio brut (pas le texte) pour extraire les dimensions para-verbales : ton, débit, micro-hésitations, marqueurs de sarcasme. Corrèle ces signaux avec les claims pour détecter les appels à l'émotion fallacieux. *Phase 4 uniquement.*

---

## 3. Stack Technique & Choix Technologiques

### 3.1 Speech-to-Text : faster-whisper `large-v3-turbo`

**Benchmark de référence (Artificial Analysis AA-WER v2.0, fév. 2025) :**

| Modèle | WER (AA-WER) | Speed Factor | Prix/1000 min |
|--------|-------------|-------------|---------------|
| Whisper Large v2 (OpenAI) | **4.2%** | 29x | $6.00 |
| Whisper Large v3 Turbo (Fireworks) | **4.8%** | 442x | $1.00 |
| Whisper Large v3 Turbo (Groq) | **4.8%** | 375x | $0.67 |
| Whisper Large v3 (fal.ai) | 4.3% | 82x | $1.15 |
| NVIDIA Canary Qwen 2.5B (open-source #1) | 5.63% WER* | 418x | gratuit |
| GPT-4o Transcribe (meilleur cloud) | ~3.5% | variable | $6+ |

*WER sur le HuggingFace Open ASR Leaderboard, non comparable directement à AA-WER.*

**Décision : `faster-whisper` avec le modèle `large-v3-turbo` en local.**

Justification : le modèle `large-v3-turbo` d'OpenAI offre 4.8% WER (quasi-identique à `large-v3` pour ~2x le speed factor) et fonctionne nativement avec faster-whisper via CTranslate2, ce qui permet une inférence locale très rapide (GPU optionnel mais recommandé). Pour le mode temps réel, chunking par fenêtres de 5s avec overlap de 1s.

Pour la phase 1 (MVP offline), on utilise également **WhisperX** qui intègre faster-whisper + diarization pyannote dans un pipeline unifié, simplifiant l'étape 1+2 en une seule commande.

### 3.2 Speaker Diarization : pyannote/speaker-diarization-community-1

**Décision : `pyannote/speaker-diarization-community-1` (pyannote.audio 4.0)**

Sorti début 2025, `community-1` est le meilleur modèle open-source de diarization disponible, outperformant `speaker-diarization-3.1` sur toutes les métriques clés (réduction significative du speaker confusion rate, amélioration du speaker counting). Il est gratuit, auto-hébergé, et compatible GPU/CPU. `pyannote-3.1` reste la référence dans la littérature mais `community-1` le surpasse désormais sans contrepartie.

Pour le mode fichier : **WhisperX** wrape les deux (faster-whisper + pyannote community-1) de manière optimale et gère la réconciliation des timestamps STT/diarization, un problème non trivial documenté par l'équipe pyannote.

### 3.3 Frontend : React + Vite + TypeScript

**Décision : React + Vite (TypeScript) avec Tailwind CSS.**

Alternatives considérées :

| Option | Avantages | Inconvénients | Verdict |
|--------|-----------|---------------|---------|
| React + Vite | Standard industrie, écosystème riche, Cytoscape-React natif, WaveSurfer.js, vibe-coding facile | — | ✅ Retenu |
| Svelte/SvelteKit | Léger, DX agréable | Moins mainstream pour portfolio, moins d'intégrations natives | ❌ |
| Vue | Bon DX | Moins reconnu en ML/data engineering | ❌ |
| Vanilla JS | Aucune dépendance | Très verbeux pour la complexité UI requise | ❌ |

**Justification :**
- **Cytoscape.js** dispose d'un wrapper React officiel (`react-cytoscapejs`) → graphe argumentatif natif
- **WaveSurfer.js** s'intègre proprement en React → waveform audio interactive pour le mode fichier
- **Web Audio API** est accessible depuis n'importe quel framework JS → capture microphone
- **Tailwind CSS** → liberté totale sur l'UI/UX, vibe-codable
- Build statique via `vite build` → déploiement trivial (Nginx, GitHub Pages, etc.)
- Reconnaissance immédiate sur un portfolio GitHub

### 3.4 Stack technique complète

| Composant | Technologie | Justification |
|-----------|-------------|---------------|
| **STT (local)** | `faster-whisper` `large-v3-turbo` | WER 4.8%, 375–442x speed factor, CTranslate2 optimisé |
| **STT + Diarization (fichier)** | WhisperX | Pipeline unifié, réconciliation timestamps automatique |
| **Diarization** | `pyannote/speaker-diarization-community-1` | Meilleur open-source 2025, outperforme 3.1 |
| **LLM principal** | Claude API (`claude-opus-4` ou `claude-sonnet-4`) | Extraction de claims, inférence de relations, structured outputs |
| **Classifieur fallacies** | Modèle fine-tuné (~120M params) sur corpus LOGIC | Classifieur rapide, ne déclenche LLM que sur anomalie |
| **Graph store** | NetworkX (in-memory) → Neo4j (persistance v2) | NetworkX suffit pour un débat unitaire |
| **Fact-checking** | Agent LangGraph + web search API (Tavily ou SerpAPI) | Workflow agentic découplé (async) |
| **Analyse prosodique** | Empath + réseaux acoustiques custom | Phase 4 uniquement |
| **Backend** | FastAPI + WebSocket natif | Endpoints REST + streaming temps réel vers le front |
| **Message broker** | Redis Streams (v0) → Kafka (v2) | Léger pour le proto, scalable pour la prod |
| **Frontend** | React + Vite + TypeScript + Tailwind | Standard industrie, liberté UI/UX, vibe-coding |
| **Graphe 2D** | Cytoscape.js (`react-cytoscapejs`) | Graphe interactif, force-directed, bien documenté |
| **Waveform audio** | WaveSurfer.js | Visualisation de la piste audio pour le mode fichier |
| **Capture microphone** | Web Audio API natif | Chunks streaming vers le backend via WebSocket |
| **Graphe 3D (v2)** | Three.js / Cosmograph | Phase visualisation avancée |
| **Transport** | WebSocket natif | Event-driven, mise à jour dynamique du graphe |

---

## 4. Features Détaillées

### 4.1 Détection de fallacies

La littérature montre que les LLMs standard performent de manière médiocre sur la classification de fallacies (scores micro-F1 entre 8,62% et 53,31% sur le benchmark LOGIC). Notre approche combine un classifieur rapide spécialisé avec un LLM génératif contextuel pour maximiser le compromis latence/précision.

**Méthode de distillation structurelle :** suivant les modèles structure-aware de la littérature, l'Agent Sceptique identifie les segments sémantiquement similaires dans un argument, les masque, puis transmet ces instances masquées au classifieur. Cela force le modèle à se concentrer sur le pattern de raisonnement sous-jacent plutôt que sur les mots-clés de surface.

| Fallacie | Mécanisme de détection | Difficulté algorithmique |
|----------|----------------------|--------------------------|
| **Strawman** | Comparaison d'embeddings entre le claim original (Speaker A) et la reformulation par Speaker B. Score cosinus faible + intent réfutatif = flag. | **Élevée.** Nécessite un historique parfait de la prémisse originale + mesure de divergence sémantique + détermination d'intentionnalité. |
| **Goal-post Moving** | Tracking temporel des win conditions par speaker et par topic. Détection de redéfinition des critères après satisfaction. | **Élevée.** Distinction entre argument multi-propositionnel légitime et fuite discursive ad hoc. |
| **Raisonnement circulaire** | Détection de cycles dans le graphe orienté (DFS). Mapping prémisses/conclusion dans un même espace vectoriel pour vérifier la présupposition mutuelle. | **Moyenne.** La détection de cycle est triviale algorithmiquement (O(V+E)) ; l'interprétation sémantique ne l'est pas. |
| **Ad Hominem** | Classification NER + détection d'attaque dirigée vers une personne plutôt que vers un argument. | **Faible à moyenne.** Pattern lexical relativement stable. |
| **Slippery Slope** | Détection de chaînes causales non justifiées : A → B → C → catastrophe, où les liens intermédiaires manquent de support factuel. | **Moyenne.** Requiert l'évaluation de la force de chaque lien causal de la chaîne. |
| **Appeal to Emotion** | Corrélation entre l'analyse prosodique (Agent Prosodique) et l'absence de support factuel. Cadrage émotionnel sans substance logique. | **Élevée.** Le cadrage émotionnel réduit de 14,5% la capacité humaine à détecter les fallacies (littérature). |
| **False Dilemma** | Détection de structure binaire artificielle ("soit A, soit B") quand le LLM identifie des alternatives viables non mentionnées. | **Moyenne.** Nécessite des connaissances du domaine pour identifier les alternatives. |

### 4.2 Fact-checking asynchrone

L'Agent Chercheur opère de manière découplée du pipeline principal pour ne pas bloquer le temps réel. Les résultats apparaissent progressivement sur le graphe (badges vert/rouge/gris par nœud).

**Workflow :**

1. L'Agent Ontologique tag chaque claim comme factuel ou d'opinion.
2. Pour chaque claim factuel, l'Agent Chercheur reformule en query vérifiable.
3. Recherche via web search API (sources prioritaires : articles scientifiques, sites institutionnels, bases de données officielles).
4. Retourne un verdict structuré : `{ verdict, confidence, sources[], contradicting_evidence[] }`.
5. Le verdict est injecté comme annotation sur le nœud correspondant du graphe.

**Verdicts possibles :** `supported` | `refuted` | `unverifiable` | `partially_true`

**Inspiration CaptainFact :** en plus du fact-checking automatisé, le système pourrait exposer une API permettant à des utilisateurs humains de sourcer, confirmer ou réfuter des claims, créant un modèle hybride human-in-the-loop. Cette couche collaborative est optionnelle mais renforce la confiance dans les verdicts.

### 4.3 Détection de strawman

Quand Speaker B "répond" à Speaker A, le système vérifie que B répond réellement à ce que A a dit. La littérature définit le strawman par la présence simultanée de deux dimensions : *misrepresentation aspect* (déformation du contenu) et *refutational aspect* (utilisation de cette déformation comme base d'attaque).

**Implémentation technique :** on compare l'embedding du claim original de A avec la reformulation implicite que B en fait. Un score de similarité cosinus inférieur à un seuil calibré (typiquement 0.7–0.8 selon le domaine), combiné à la détection d'intent réfutatif, déclenche un flag strawman que le LLM confirme ou infirme par analyse contextuelle.

### 4.4 Détection de goal-post moving

Le système track les claims d'un même speaker sur un même topic au fil du temps. Si la thèse initiale mute silencieusement (les critères de succès changent sans acknowledgment), le système le flag. C'est du tracking de drift sémantique par topic et par speaker.

**Formellement :** le système cartographie les win conditions initiales du débat. Si un nœud de réfutation logique est validé par les preuves apportées, mais que le débatteur génère un nouveau nœud de conditionnalité (Issue B, puis Issue C) sans jamais concéder le nœud précédent, le glissement ad hoc est identifié.

### 4.5 Détection de cycles et circularité

Détection algorithmique directe : recherche de cycles dans le graphe orienté par DFS standard (complexité O(V+E)). La vraie valeur est dans l'interprétation : quand un cycle A → B → C → A est détecté, le LLM explique en langage naturel pourquoi c'est circulaire et quel nœud nécessite une justification externe pour "casser" le cycle.

**Connexion théorique :** la littérature sur le model checking (algorithmes Assume-Guarantee, règle CIRC-AG) fournit un cadre formel pour traiter le raisonnement circulaire. L'algorithme ACR génère itérativement des contraintes d'appartenance en utilisant des solveurs SAT pour affiner les hypothèses. Ce cadre peut être adapté pour la vérification formelle des chaînes argumentatives.

### 4.6 Score de rigueur par participant

Un score composite affiché en temps réel, basé sur :

- Ratio claims supportés / non-supportés
- Nombre de fallacies détectées (pondéré par gravité)
- Taux de fact-check positif
- Cohérence interne (contradictions entre ses propres claims)
- Taux de réponse directe aux arguments adverses vs esquive
- Score prosodique (ratio factuel/émotionnel) — Phase 4

### 4.7 Analyse prosodique et multimodalité *(Phase 4)*

La majorité des systèmes d'analyse discursive se limitent au texte transcrit. Or, une proportion significative du discours fallacieux repose sur des signaux para-verbaux : modulations tonales, micro-hésitations, expressions de sarcasme, variations de débit. La littérature montre que le cadrage émotionnel généré par l'IA réduit la capacité humaine de détection de 14,5%.

L'Agent Prosodique extrait directement du signal audio (pas du texte) des features émotionnelles via des embeddings acoustiques. La bibliothèque Empath (200+ catégories) et des réseaux de neurones acoustiques modélisent les niveaux de colère, peur, tentative de tromperie. Ces tenseurs sont fusionnés avec les représentations nodales du graphe pour produire un score de crédibilité asymétrique par claim.

**Use case clé :** corréler l'apparition d'un pic émotionnel (détecté par l'audio) avec un claim sans support factuel (détecté par le graphe) pour flagger un Appeal to Emotion.

### 4.8 Mode modérateur

Le système génère en temps réel des suggestions pour un modérateur humain :

- "Speaker A n'a pas répondu au point X de Speaker B (posé à 12:32)"
- "Le claim Y de Speaker B n'a pas été sourcé et contredit le consensus scientifique sur Z"
- "Contradiction détectée entre ce que Speaker A a dit à 5:32 et ce qu'il affirme maintenant"
- "Le débat a dévié du sujet initial depuis 3 minutes. Sujet courant : X. Sujet original : Y"

### 4.9 Co-pilote épistémique : l'inoculation psychologique

L'écueil des outils de fact-checking actuels est leur posture punitive : ils signalent "faux" ou "illogique", déclenchant une dissonance cognitive chez l'utilisateur. En s'appuyant sur la théorie de l'inoculation (Inoculation Theory, illustrée par des projets comme Bad News ou FallacyCheck), DebateGraph adopte une posture socratique.

**Concrètement :** lorsqu'une fallacie de type Slippery Slope est détectée, au lieu d'afficher *"Fallacie détectée : pente glissante"*, le système formule une question contextuelle : *"Les données présentées permettent-elles d'établir un lien de causalité inévitable entre A et Z, ou d'autres variables peuvent-elles intervenir ?"*

L'utilisateur peut choisir entre le mode **"juge"** (alertes directes) et le mode **"socratique"** (questions guidées).

### 4.10 Résumé structuré post-débat

Un rapport auto-généré exportable en PDF/Markdown contenant : thèse de chaque camp, meilleurs arguments de chaque côté, points non résolus, fact-checks, fallacies détectées, score de rigueur final, et la structure complète du graphe argumentatif.

---

## 5. Visualisation Dynamique

### 5.1 Modèle de graphe

Le graphe suit la sémantique colorimétrique d'Argdown adaptée :

| Type d'arête | Couleur | Sémantique |
|--------------|---------|-----------|
| Soutien | 🟩 Vert | A fournit une évidence ou un raisonnement qui renforce B |
| Attaque | 🟥 Rouge | A contredit directement B ou présente une évidence inverse |
| Sape (Undercut) | 🟪 Violet | A conteste le lien logique entre B et C (pas B lui-même) |
| Reformulation | ⬜ Gris | A et B expriment la même idée différemment (classe d'équivalence) |
| Implication | 🟦 Bleu | A implique logiquement B (conséquence nécessaire) |

Chaque nœud porte des annotations visuelles :

- **Badge fact-check :** ✓ (vert) | ✗ (rouge) | ? (gris = en cours / unverifiable)
- **Halo de fallacie :** bordure rouge clignotante avec label
- **Indicateur de speaker :** couleur de fond distincte par participant
- **Score de confiance :** opacité du nœud proportionnelle au score de confiance du claim

### 5.2 Mode fichier : waveform synchronisée

Quand l'utilisateur importe un fichier audio/vidéo, le frontend affiche une waveform interactive (WaveSurfer.js) synchronisée avec le graphe. La lecture audio avance en temps réel et le graphe s'anime au rythme de la transcription originale (replay pas-à-pas). On peut cliquer sur n'importe quel nœud du graphe pour sauter à l'instant correspondant dans l'audio, et vice-versa.

### 5.3 Interaction et édition

Contrairement aux systèmes passifs (OVA, Rationale), DebateGraph permet l'édition à la volée :

- Cliquer sur un nœud pour réviser l'interprétation de l'IA via un prompt local
- Générer un sous-arbre conditionnel ("que se passerait-il si cette prémisse était fausse ?")
- Forcer une reclassification asynchrone du graphe complet (Collective Classification)
- Annoter manuellement un nœud (ajout de contexte, sources, commentaires)

### 5.4 Roadmap de visualisation

| Version | Rendu | Tech |
|---------|-------|------|
| v0 | Graphe 2D force-directed, interactif + waveform synchronisée (fichier) | React + Cytoscape.js + WaveSurfer.js + WebSocket |
| v1 | + Timeline synchronisée avec l'audio, replay pas-à-pas, mode modérateur UI | + D3.js pour la timeline, synchro audio HTML5 |
| v2 | Graphe 3D immersif, clustering spatial, rendu WebGL | Three.js / Cosmograph / Neo4j NVL |

---

## 6. Stratégie de Développement

### 6.1 Approche incrémentale

**Principe clé :** commencer par une v0 offline (upload d'un audio/vidéo, analyse après coup) avant de s'attaquer au temps réel. Le streaming ajoute énormément de complexité (buffering, latence, synchronisation front/back) et ne change rien à la qualité de l'analyse.

---

**Phase 1 — MVP offline (4–6 semaines)**

- Upload audio/vidéo → WhisperX (diarization + transcription) → extraction de claims → construction du graphe
- Visualisation statique du graphe (Cytoscape.js) + waveform synchronisée (WaveSurfer.js)
- Détection de fallacies basique (classifieur + LLM)
- Pas de fact-checking, pas de prosodique

---

**Phase 2 — Analyse enrichie (4–6 semaines)**

- Ajout du fact-checking asynchrone (Agent Chercheur + Tavily/SerpAPI)
- Détection de cycles, strawman, goal-post moving
- Score de rigueur par participant
- Export du rapport post-débat (PDF/Markdown)
- Mode socratique vs. mode juge

---

**Phase 3 — Temps réel (6–8 semaines)**

- Streaming microphone → Web Audio API → WebSocket → pipeline complet en temps réel
- faster-whisper chunking (fenêtres 5s, overlap 1s)
- WebSocket pour la mise à jour dynamique du graphe
- Mode modérateur
- Gestion de la latence et buffering intelligent

---

**Phase 4 — Multimodalité et scaling (8+ semaines)**

- Agent Prosodique (Empath + réseaux acoustiques)
- Graphe 3D (Three.js/WebGL)
- Persistance Neo4j pour l'analyse multi-débats
- API publique et couche collaborative (CaptainFact-like)

### 6.2 Structure du projet

```
debategraph/
├── backend/
│   ├── main.py                  # FastAPI entrypoint
│   ├── api/
│   │   ├── routes/
│   │   │   ├── upload.py        # Endpoint upload fichier
│   │   │   └── ws.py            # WebSocket handler (temps réel)
│   │   └── models/              # Pydantic schemas
│   ├── pipeline/
│   │   ├── transcription.py     # WhisperX / faster-whisper
│   │   ├── diarization.py       # pyannote community-1
│   │   └── chunker.py           # Streaming audio chunking
│   ├── agents/
│   │   ├── orchestrator.py      # Routeur d'intention central
│   │   ├── ontological.py       # Agent Ontologique
│   │   ├── skeptic.py           # Agent Sceptique (fallacies)
│   │   ├── researcher.py        # Agent Chercheur (fact-check)
│   │   └── prosodic.py          # Agent Prosodique (Phase 4)
│   ├── graph/
│   │   ├── store.py             # NetworkX graph store
│   │   └── algorithms.py        # DFS cycles, strawman, drift
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── GraphView.tsx    # Cytoscape.js graph
│   │   │   ├── WaveformView.tsx # WaveSurfer.js audio
│   │   │   ├── FallacyPanel.tsx # Détails fallacies
│   │   │   ├── FactCheckBadge.tsx
│   │   │   └── RigorScore.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   └── useAudioCapture.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── .env.example
├── docker-compose.yml           # Redis + backend + frontend
└── README.md
```

### 6.3 Débats de test

Pour la validation, privilégier des débats où la vérité terrain est facilement établissable :

- **Débats présidentiels US/FR :** 2 speakers bien distincts, beaucoup de fallacies, fact-checks existants pour validation croisée.
- **Débats Oxford Union :** format structuré, arguments plus rigoureux, bon test pour la détection fine.
- **Podcasts débat (Lex Fridman, Intelligence Squared) :** conversations longues, multi-topics, bon stress-test pour le tracking de drift.

---

## 7. Différenciation et Positionnement

| Dimension | État de l'art | DebateGraph |
|-----------|--------------|-------------|
| **Architecture** | Pipeline séquentiel ou LLM monolithique | Multi-agents spécialisés + routeur d'intention |
| **Analyse** | Texte seul (post-transcription) | Multimodal : texte + prosodie + émotion audio |
| **Fallacies** | Classification simple, scores F1 faibles | Classifieur rapide + LLM contextuel + distillation structurelle |
| **Visualisation** | Post-hoc, statique (OVA, Rationale) | Temps réel, interactif, éditable, 2D/3D + waveform synchronisée |
| **Fact-checking** | Séparé de l'analyse argumentative | Intégré au graphe, asynchrone, avec verdicts par nœud |
| **UX** | Posture punitive ("faux" / "illogique") | Co-pilote épistémique socratique (inoculation) |
| **Scope** | Outils fragmentés en silos | Pipeline unifié speech-to-graph + analyse + fact-check |

**Le vrai différenciateur pour le portfolio** n'est pas la techno (Whisper + LLM, tout le monde peut le faire), c'est la profondeur de l'analyse argumentative. La construction d'un vrai graphe avec détection de patterns logiques (cycles, contradictions, strawmen, drift sémantique) démontre une compréhension à la fois du NLP, de la logique formelle, et du software engineering.

---

## 8. Configuration et Secrets

Toutes les clés et variables d'environnement sont centralisées dans un fichier `.env` (non commité). Le fichier `.env.example` est commité pour documenter les variables attendues.

```bash
# .env.example

# ─── LLM (Claude API) ───────────────────────────────────────
ANTHROPIC_API_KEY=

# ─── Speaker Diarization (pyannote) ─────────────────────────
# Créer un token en lecture sur https://huggingface.co/settings/tokens
# Accepter les conditions d'utilisation sur :
# https://huggingface.co/pyannote/speaker-diarization-community-1
HUGGINGFACE_TOKEN=

# ─── Fact-Checking ──────────────────────────────────────────
# Option A : Tavily (recommandé, gratuit jusqu'à 1000 req/mois)
TAVILY_API_KEY=
# Option B : SerpAPI (alternative)
# SERPAPI_API_KEY=

# ─── Redis (message broker) ─────────────────────────────────
REDIS_URL=redis://localhost:6379

# ─── Backend ────────────────────────────────────────────────
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
CORS_ORIGINS=http://localhost:5173

# ─── Whisper ────────────────────────────────────────────────
# Modèle : tiny | base | small | medium | large-v3 | large-v3-turbo
# Recommandé pour dev CPU : medium
# Recommandé pour GPU : large-v3-turbo
WHISPER_MODEL=large-v3-turbo
# Device : cuda | cpu | auto
WHISPER_DEVICE=auto
# Compute type : float16 (GPU) | int8 (CPU)
WHISPER_COMPUTE_TYPE=float16

# ─── Analyse ─────────────────────────────────────────────────
# Seuil similarité cosinus pour la détection strawman (0.0–1.0)
STRAWMAN_SIMILARITY_THRESHOLD=0.75
# Mode UI par défaut : judge | socratic
DEFAULT_UI_MODE=socratic
```

---

## 9. Extensions Futures

- **Reconstruction logique formelle :** transformer les arguments en logique propositionnelle/premier ordre et vérifier la validité formelle des raisonnements.

- **Détection de provenance IA :** intégrer une couche de détection de contenu généré par IA (architecture type Pangram) pour certifier l'authenticité des interlocuteurs dans un contexte de débat en ligne.

- **Multilingue :** le pipeline est language-agnostic si le STT et le LLM supportent la langue cible. Le corpus TALN (1600+ articles, 5,8M mots) est une ressource pour le français.

- **API publique :** exposer le pipeline comme un service : envoyer un audio, recevoir un graphe structuré + annotations. Permet l'intégration dans des apps tierces (médias, éducation, juridique).

- **Gamification éducative :** inspiré de Bad News (jeu d'inoculation), créer un mode où l'utilisateur doit identifier les fallacies avant le système. Score d'apprentissage progressif.

- **Key Point Analysis :** dérivé d'IBM Project Debater, résumer un débat en un ensemble de points clés pondérés par fréquence de mention. Utile pour l'analyse de débats publics massifs (réseaux sociaux, consultations citoyennes).
