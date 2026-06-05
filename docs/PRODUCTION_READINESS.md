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
| Outil d'**analyse / recommandation** (cartographie, KPI, candidats d'archivage) avec humain dans la boucle | 🟢 **Apte** (après durcissement léger) |
| Outil de **décision/action d'archivage automatique** sur donnée réglementée | 🔴 **Non apte** tant que les blocages P0 (§7) ne sont pas levés |

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
| 3 | **Classification ML** | 🟡 N2 | N4 | 2 passes (mots-clés + LinearSVC+Platt), modèle versionné, **parité train/inférence garantie**. Écart : **~75 % global, non prouvé sur le physique (n=12)**, plafond du LLM-annotateur. |
| 4 | **Moteur de règles & décision** | 🟢 N3 | N4 | Data-driven, **domaine = input** (`CONSERVATION_REGLEMENTAIRE`), 6 dimensions NULL-safe. Écart : rétention = **défauts FR codés, non validés juridiquement**. |
| 5 | **Sûreté de décision** | 🔴 N1 | N4 | Recommandations *only*. **Aucun** fail-safe, gate d'approbation, ni réversibilité. ⟵ **écart majeur** |
| 6 | **Conformité & auditabilité** | 🔴 N1 | N4 | Pas d'**audit trail décisionnel** (qui/quoi/quand/approbateur), rétention non datée ni versionnée par juridiction. ⟵ **écart majeur** |
| 7 | **Sécurité & PII** | 🟡 N2 | N4 | `.env` gitignoré, détection PII. **Mais** l'enrichissement « observed » **extrait de vraies valeurs (PII)** dans des CSV non chiffrés. Écart : vault, masquage, RBAC, moindre privilège. |
| 8 | **Tests & qualité logicielle** | 🟡 N2 | N4 | 46 tests unitaires (parité, features, loader, Monte-Carlo). Écart : **0 test d'intégration/E2E**, pas de data-quality checks. |
| 9 | **Observabilité & exploitation** | 🟡 N2 | N4 | Logs structurés (loguru), `pipeline_run`, `drift_report.json`. Écart : monitoring/alerting, SLO, runbooks. |
| 10 | **CI/CD & infrastructure** | 🔴 N1 | N3-4 | Aucun pipeline CI/CD ni IaC visible. Écart : CI (tests+lint), CD modèle, infra reproductible. |
| 11 | **Documentation & gouvernance modèle** | 🟢 N3 | N4 | Docs A→E excellentes, `production_model_card.md`, récit honnête. Écart : registry de modèles, runbooks, ownership/SLA. |

**Synthèse :** 3 dimensions au vert (architecture, règles, doc), 5 en jaune (pipeline, ML, sécurité, tests, observabilité), **3 au rouge — toutes sur l'axe décision/conformité** (sûreté, audit, CI/CD).

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
| **R7** | Secrets en `.env`, pas de moindre privilège DB | 🟡 Moyen | Moyenne | `.env` local | Vault, comptes à privilèges séparés (lecture Oracle ≠ écriture PG) |
| **R8** | Pas de **réversibilité** prouvée d'un archivage | 🟡 Moyen | Moyenne | Couche d'action absente | Dry-run + restore testé avant toute exécution réelle |
| **R9** | Échecs/dérives non détectés en prod | 🟡 Moyen | Moyenne | Pas de monitoring/alerting | SLO + alerting sur statut de run et drift |
| **R10** | Double comptage `ps_record`/`oracle_table` fausse les volumes | 🟢 Faible | Faible | Connu, documenté | Déduplication par fichier physique |

---

## 7. Critères Go / No-Go (gates P0 — bloquants avant tout usage *actif*)

Aucune mise en production qui **agit** sur la donnée ne doit avoir lieu avant que **tous** ces critères soient remplis :

- [ ] **Fail-safe** : toute incertitude / faible confiance / domaine réglementé dans sa fenêtre → **CONSERVATION** (jamais d'archivage automatique).
- [ ] **Gate d'approbation humaine** obligatoire avant archivage d'un domaine réglementé ou d'une prédiction sous le seuil de confiance.
- [ ] **Audit trail immuable** de chaque recommandation + décision + approbateur + version de modèle.
- [ ] **Rétention validée juridiquement**, datée, versionnée, paramétrable par juridiction.
- [ ] **Gold humain physique** à puissance statistique suffisante (cible : intervalle de confiance serré, plus n=12) et **SLA de rappel** par domaine réglementé atteint (ex. rappel ≥ 0,95 sur Finance/RH avant d'autoriser tout archivage les concernant).
- [ ] **PII masquée** dans tous les exports/logs ; secrets en **vault**.
- [ ] **Réversibilité prouvée** : restauration d'archive testée de bout en bout.

> Tant que ces gates ne sont pas verts, l'usage recommandé est **« analyse + recommandation avec validation humaine »** — ce qui est déjà livrable après le durcissement de la Phase 0.

---

## 8. Feuille de route priorisée

Effort indicatif : **S** (jours) · **M** (1-3 sem) · **L** (1-2 mois). Impact : **H/M/L**.

### Phase 0 — Sûreté & conformité *(bloquant, lève R1/R2/R5 + une partie de R4)*
| Action | Effort | Impact |
|---|:--:|:--:|
| Fail-safe sur incertitude (CONSERVATION par défaut si confiance < seuil ou domaine réglementé dans fenêtre) | S | H |
| Audit trail décisionnel immuable (table `serving.archiving_decision_log` : asset, reco, décision, approbateur, modèle, ts) | M | H |
| Workflow d'approbation humaine (queue de validation avant action) | M | H |
| Rétention versionnée + datée + multi-juridiction (+ revue juridique) | M | H |
| Masquage PII par défaut dans les exports/labeling | S | H |

### Phase 1 — Fiabilité du modèle *(lève R3 + le plafond de qualité)*
| Action | Effort | Impact |
|---|:--:|:--:|
| Gold humain **physique** stratifié, multi-annotateurs, accord inter-annotateurs (κ) | M | H |
| Boucle d'apprentissage actif : la queue de revue alimente le gold humain | M | H |
| Validation de calibration (fiabilité de `confidence`) + SLA de rappel par domaine | S | H |
| Drift monitoring opérationnalisé (alerting sur `drift_report`) | S | M |

### Phase 2 — Industrialisation *(lève R6/R7/R9)*
| Action | Effort | Impact |
|---|:--:|:--:|
| Tests d'intégration/E2E (couche serving, règles, vues) + data-quality checks | M | H |
| CI (tests + lint + type-check) et CD du modèle (registry, promotion gouvernée) | M | M |
| Vault pour secrets + comptes DB à moindre privilège | S | M |
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

1. **Démarrer par la Phase 0** : c'est le strict nécessaire pour un usage entreprise *sans risque de conformité*, et c'est rapide (essentiellement S/M). À l'issue, le système est livrable comme **outil d'aide à la décision auditée**.
2. **Enchaîner la Phase 1** (qualité modèle) en parallèle : l'expérience récente l'a prouvé — ajouter du volume LLM **n'améliore pas** la surface physique ; le levier est la **vérité-terrain humaine**. Investir là, pas dans plus d'annotation LLM.
3. **Phases 2-3** avant tout déploiement qui **agit** réellement sur la donnée.

> **En une phrase pour un comité projet :** « Le socle est sain et honnête ; il manque l'enveloppe de gouvernance (sûreté, audit, conformité) avant qu'il puisse décider seul. Cette enveloppe — Phase 0 — est courte et débloque immédiatement un usage entreprise en mode recommandation auditée. »
