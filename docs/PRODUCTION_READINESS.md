# Évaluation de production & feuille de route

> **Objet :** statuer sur l'aptitude du système à un usage **en entreprise** (au-delà du PFE) et tracer la trajectoire prototype → production.
> **Date :** 2026-06-05 · **Version :** 1.0 · **Périmètre évalué :** run 6 (167 260 actifs)

---

## 1. Résumé exécutif

Le système est un **prototype solide et honnête** : architecture en couches reproductible, pipeline idempotent et tracé, classification ML versionnée avec parité train/inférence, moteur de règles piloté par le domaine, et une évaluation déjà lucide sur ses propres limites. C'est un **excellent socle**.

Il **n'est pas, en l'état, apte à prendre seul des décisions d'archivage en production** sur des données d'entreprise. La raison n'est pas la performance du modèle (~75 %) mais l'**absence de l'enveloppe de sûreté et de conformité** qu'exige un outil qui peut, à terme, déplacer ou purger de la donnée réglementée.

**Verdict :**

| Usage | Aptitude |
|---|---|
| Outil d'**analyse / recommandation** (cartographie, KPI, candidats d'archivage) avec humain dans la boucle | 🟢 **Apte** — fail-safe, approval queue et audit trail en place (Phase 0) |
| **Test interactif du modèle** (dashboard Streamlit — saisie libre de métadonnées) | 🟢 **Apte** — page dédiée XLM-R v3 intégrée |
| Outil de **décision/action d'archivage automatique** sur donnée réglementée | 🟡 **Partiel** — Phase 0/1 implémentées mais réversibilité non prouvée, Finance rappel < SLA, CI/CD absent |

> **Principe directeur :** on peut industrialiser un modèle à 75 % **à condition** qu'il n'agisse jamais seul sur de la donnée réglementée ou incertaine, et que **chaque action soit approuvée, auditée et réversible**. La valeur entreprise est dans la **gouvernance de la décision**, pas seulement dans la métrique ML.

---

## 2. Périmètre & usage visé

- **Entrée :** métadonnées Oracle PeopleSoft EP92U038 (records logiques + tables physiques).
- **Traitement :** classification par domaine métier → moteur de règles d'archivage (volume, âge, sensibilité, dépendances, références, rétention légale par domaine) → KPI coût/ROI.
- **Décision pilotée :** stratégie d'archivage par **table physique** (~16 800), avec rétention légale différenciée par domaine.
- **Partie prenante du risque :** la décision touche la **conformité légale** (Code de commerce, RGPD, Code du travail) et l'**intégrité du SI** (archiver un pilier structurel casse des dépendances).

---

## 3. Échelle de maturité

| Niveau | Nom | Définition |
|---|---|---|
| **N1** | Initial / Prototype | Fonctionne en démo, dépend d'un opérateur, pas de garde-fou |
| **N2** | Reproductible | Déterministe, versionné, rejouable |
| **N3** | Géré | Tracé, testé, paramétrable, erreurs gérées |
| **N4** | Industrialisé | CI/CD, monitoring, sûreté, audit, SLA |
| **N5** | Optimisé | Amélioration continue, auto-réentraînement gouverné |

---

## 4. Scorecard de maturité (11 dimensions)

| # | Dimension | Niveau | Cible | État actuel (preuves) |
|---|---|:--:|:--:|---|
| 1 | **Architecture & données** | 🟢 N3 | N4 | Médaillon `raw→processed→serving`, idempotence DELETE+INSERT par `run_id`, hash SHA-256, `admin.pipeline_run`. Écart : contrats de qualité de données / validation de schéma. |
| 2 | **Pipeline & orchestration** | 🟡 N2-3 | N4 | Flows Prefect (`flow_full_pipeline`), resume Oracle, tolérance par préfixe. Écart : serveur Prefect prod, infra-as-code, secrets gérés. |
| 3 | **Classification ML** | 🟢 N3 | N4 | 2 passes prod (mots-clés + LinearSVC+Platt) + **XLM-R v3 ONNX** (feature gating, Focal Loss, ECE 0,011, SLA offsets). Interface de test Streamlit intégrée. Écart : **Finance rappel 0,84 < SLA 0,90**, non prouvé sur le physique. |
| 4 | **Moteur de règles & décision** | 🟢 N3 | N4 | Data-driven, **domaine = input** (`CONSERVATION_REGLEMENTAIRE`), 6 dimensions NULL-safe. Écart : rétention = **défauts FR codés, non validés juridiquement**. |
| 5 | **Sûreté de décision** | 🟡 N3 | N4 | **Phase 0 implémentée** : fail-safe `confidence < 0,60 → A_EVALUER`, approval queue, audit trail en base, masquage PII. Offsets SLA per-classe (Phase 1). Écart : réversibilité prouvée, gate d'approbation humaine non encore wired E2E. |
| 6 | **Conformité & auditabilité** | 🟡 N2 | N4 | Audit trail décisionnel en base (`serving`), masquage PII dans les exports, rétention versionnée (Phase 0). Écart : approbateur humain non wired, rétention non validée juridiquement. |
| 7 | **Sécurité & PII** | 🟢 N3 | N4 | `.env` gitignoré, **masquage PII** (Phase 0), **chiffrement au repos des PII** (`pgcrypto`, schéma `security`), **moindre privilège** (comptes `pfe_reader`/`pfe_writer`, écriture refusée en lecture seule). Écart : vault à secrets, RBAC applicatif, enrichissement « observed » encore présent. |
| 8 | **Tests & qualité logicielle** | 🟡 N2 | N4 | **61 tests unitaires** (parité, features, loader, Monte-Carlo, calibration, SLA rappel, drift). Écart : **0 test d'intégration/E2E**, pas de data-quality checks. |
| 9 | **Observabilité & exploitation** | 🟡 N2-3 | N4 | Logs structurés (loguru), `pipeline_run`, `drift_report.json`, **`ModelReliabilityMonitor`** (calibration + SLA + drift — Phase 1). Écart : alerting opérationnel, SLO, runbooks. |
| 10 | **CI/CD & infrastructure** | 🔴 N1 | N3-4 | Aucun pipeline CI/CD ni IaC visible. Écart : CI (tests+lint), CD modèle, infra reproductible. |
| 11 | **Documentation & gouvernance modèle** | 🟢 N3 | N4 | Docs A→E + `production_model_card.md` + XLM-R v3 README + `PRODUCTION_READINESS.md`. Écart : registry de modèles, runbooks, ownership/SLA. |

**Synthèse :** **5 dimensions au vert** (architecture, ML, règles, **sécurité & PII**, doc), 4 en jaune (pipeline, conformité, tests, observabilité), **1 au rouge** (CI/CD). Phase 0 (sûreté) et Phase 1 (fiabilité modèle) sont implémentées — passées de N1 à N3. La sécurité passe au vert avec le **chiffrement des PII au repos** et le **moindre privilège DB** ; le vault à secrets reste le principal écart.

---

## 5. Forces déjà au niveau entreprise

Ces acquis sont rares dans un prototype et constituent un **vrai différenciateur** :

- **Reproductibilité de bout en bout** : idempotence par `run_id`, parité train/inférence garantie *par construction* (le trainer réutilise les builders du scoring), modèle versionné et tracé.
- **Honnêteté analytique** : justesse réelle mesurée à la main (≠ accord LLM), proxys nommés, portée assumée. Une revue d'architecture d'entreprise valorise cette lucidité.
- **Décision déjà pilotée par le métier** : recentrage sur les tables physiques + rétention légale différenciée par domaine.
- **N-1 réelle (snapshots) + ROI Monte-Carlo** avec intervalles — méthodologie de niveau pro, pas un chiffre unique trompeur.

---

## 6. Registre des risques

| ID | Risque | Gravité | Prob. | État actuel | Action requise |
|---|---|:--:|:--:|---|---|
| **R1** | Mauvaise classification → archivage/purge de donnée **réglementée** dans sa fenêtre légale | 🔴 Critique | Moyenne | Modèle 75 % décide via règles, sans garde-fou | Fail-safe (conserver si doute) + **approbation humaine** + SLA de **rappel** par domaine réglementé |
| **R2** | Impossible de **prouver la conformité** d'une décision (pas d'audit trail) | 🔴 Critique | Élevée | Aucun journal décisionnel | Audit trail **immuable** : recommandation, décision, approbateur, horodatage, version du modèle |
| **R3** | Confiance **non calibrée** / qualité physique non mesurée → seuils de revue non fiables | 🟠 Élevé | Élevée | Calibration Platt mais non validée sur le physique (n=12) | Calibration vérifiée + gold humain physique **puissant** |
| **R4** | **Fuite PII** par l'outil de gouvernance lui-même (valeurs réelles dans les exports) | 🟠 Élevé | Moyenne | `observed enrichment` lit emails/identités → CSV | Masquage/pseudonymisation, chiffrement, accès restreint, désactivation par défaut |
| **R5** | Rétention = **défauts FR codés**, non validés ni versionnés par juridiction | 🟠 Élevé | Élevée | `dim_domain_retention` valeurs par défaut | Table versionnée, datée, **validée par le juridique**, multi-juridiction |
| **R6** | Régression silencieuse sur la couche serving/règles | 🟡 Moyen | Moyenne | 0 test d'intégration | Tests d'intégration DB + data-quality assertions en CI |
| **R7** | Secrets en `.env` (pas de vault) | 🟡 Moyen | Moyenne | `.env` local ; **moindre privilège DB traité** : comptes `pfe_reader` (SELECT) / `pfe_writer` (CRUD) créés et vérifiés | Vault à secrets (les mots de passe restent en clair dans la configuration) |
| **R8** | Pas de **réversibilité** prouvée d'un archivage | 🟡 Moyen | Moyenne | Couche d'action absente | Dry-run + restore testé avant toute exécution réelle |
| **R9** | Échecs/dérives non détectés en prod | 🟡 Moyen | Moyenne | Pas de monitoring/alerting | SLO + alerting sur statut de run et drift |
| **R10** | Double comptage `ps_record`/`oracle_table` fausse les volumes | 🟢 Faible | Faible | Connu, documenté | Déduplication par fichier physique |

---

## 7. Critères Go / No-Go (gates P0 — bloquants avant tout usage *actif*)

Aucune mise en production qui **agit** sur la donnée ne doit avoir lieu avant que **tous** ces critères soient remplis :

- [x] **Fail-safe** : `confidence < 0,60 → A_EVALUER → approval queue` — implémenté (Phase 0).
- [x] **Gate d'approbation humaine** : queue en base, masquage PII, audit trail — implémenté (Phase 0).
- [x] **Audit trail** de chaque recommandation + version de modèle — implémenté (Phase 0).
- [ ] **Approbateur humain wired E2E** : la queue existe mais le workflow de validation n'est pas encore branché à une interface opérationnelle.
- [ ] **Rétention validée juridiquement**, datée, versionnée, paramétrable par juridiction.
- [ ] **Finance rappel ≥ 0,90** (SLA) : actuellement 0,84 — seul levier : annotations humaines supplémentaires via la queue.
- [x] **PII masquée** dans les exports (Phase 0) et **chiffrée au repos** (`pgcrypto`). Secrets `.env` gitignorés. **Moindre privilège DB en place** (`pfe_reader`/`pfe_writer`). Écart : vault à secrets, RBAC applicatif.
- [ ] **Réversibilité prouvée** : restauration d'archive testée de bout en bout.

> Tant que ces gates ne sont pas verts, l'usage recommandé est **« analyse + recommandation avec validation humaine »** — ce qui est déjà livrable après le durcissement de la Phase 0.

---

## 8. Feuille de route priorisée

Effort indicatif : **S** (jours) · **M** (1-3 sem) · **L** (1-2 mois). Impact : **H/M/L**.

### ✅ Phase 0 — Sûreté & conformité *(implémentée)*
| Action | Statut |
|---|:--:|
| Fail-safe `confidence < 0,60 → A_EVALUER → approval queue` | ✅ |
| Audit trail décisionnel en base (asset, reco, modèle, ts) | ✅ |
| Workflow d'approbation humaine (queue en base) | ✅ (workflow E2E opérateur non wired) |
| Rétention versionnée + datée (multi-juridiction + revue juridique) | ⏳ |
| Masquage PII par défaut dans les exports/labeling | ✅ |

### ✅ Phase 1 — Fiabilité du modèle *(implémentée)*
| Action | Statut |
|---|:--:|
| XLM-R v3 : feature gating, Focal Loss, per-class calibration (ECE 0,011) | ✅ |
| Decision offsets SLA per-classe (Finance +2,26 ; RH +4,42 ; Ventes +5,42) | ✅ |
| `ModelReliabilityMonitor` : calibration + SLA rappel + drift monitoring | ✅ |
| Gold humain physique stratifié + boucle apprentissage actif | ⏳ (Finance rappel 0,84 — annotations requises) |
| Interface de test interactif (dashboard Streamlit « 🤖 Test du modèle ») | ✅ |

### Phase 2 — Industrialisation *(lève R6/R7/R9)*
| Action | Effort | Impact |
|---|:--:|:--:|
| Tests d'intégration/E2E (couche serving, règles, vues) + data-quality checks | M | H |
| CI (tests + lint + type-check) et CD du modèle (registry, promotion gouvernée) | M | M |
| Vault pour secrets (comptes DB à moindre privilège : ✅ fait) | S | M |
| Observabilité : SLO, monitoring, alerting, runbooks | M | M |
| Infra-as-code + orchestration Prefect serveur | M | M |

### Phase 3 — Action & échelle *(lève R8/R10)*
| Action | Effort | Impact |
|---|:--:|:--:|
| Couche d'**exécution** d'archivage : dry-run → exécution → vérification → rollback | L | H |
| Test de restauration (réversibilité prouvée) | M | H |
| Tests de charge (passage démo ~8 Go → volumes prod) + déduplication physique | M | M |
| Réentraînement périodique gouverné (auto-promotion sous conditions) | M | M |

---

## 9. Recommandation immédiate

1. ~~**Démarrer par la Phase 0**~~ — **Phase 0 implémentée** (fail-safe, approval queue, audit trail, masquage PII). Le système est livrable comme outil d'aide à la décision auditée.
2. ~~**Enchaîner la Phase 1**~~ — **Phase 1 implémentée** (XLM-R v3 ONNX, calibration per-classe, SLA offsets, drift monitoring, interface de test Streamlit).
3. **Priorité suivante — annotations Finance/RH** : le seul levier restant pour franchir le SLA rappel 0,90 sur Finance (actuellement 0,84) est d'alimenter la queue d'approbation avec des étiquettes humaines.
4. **Phase 2** (CI/CD, tests E2E, vault) avant tout déploiement qui **agit** réellement sur la donnée.

> **En une phrase pour un comité projet :** « Le socle est sain, honnête et maintenant sécurisé (Phase 0) avec un modèle deep learning calibré (Phase 1) ; le workflow opérateur et le CI/CD sont le prochain palier avant une action autonome sur la donnée. »
