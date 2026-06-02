# C — Modélisation logique par objet métier : Fiche Métier

> **Statut :** ✅ Complet  
> **Public cible :** Chef de projet, jury PFE, non-technicien

---

## Qu'est-ce qu'on fait dans cette section ?

À partir de la classification (section B), on **organise les données par domaine métier** et on **cartographie les relations entre ces domaines**.

Concrètement : on sait maintenant que Finance a 74 401 tables, que ces tables partagent des clés avec Achats, et qu'archiver Finance sans tenir compte d'Achats pourrait casser des relations importantes.

---

## Les 4 livrables de cette section

### 1. Le catalogue des domaines (`dim_domain`)

Une table de référence qui décrit chaque domaine :
- Nom, description métier
- Exemples d'objets typiques (ex. : Finance → VOUCHER, LEDGER, BUDGET)
- Clés bridge typiques (ex. : Finance → VOUCHER_ID, PROJECT_ID)

C'est le **dictionnaire officiel des domaines** du projet.

### 2. Le profil de chaque domaine (`mv_domain_profile`)

Pour chaque domaine, on calcule :

| Indicateur | Ce que ça mesure |
|---|---|
| Nombre d'assets | Combien de tables appartiennent à ce domaine |
| Volume total (Mo) | Combien d'espace physique occupe ce domaine |
| Candidats à l'archivage | Combien de tables ont un score d'archivage > 60 |
| Gain estimé (Mo) | Combien d'espace on pourrait récupérer |
| Ratio de colonnes nullables | Indicateur de qualité des données |
| Assets sans description | Indicateur de gouvernance |
| Niveau de risque | HIGH / MEDIUM / LOW selon les dépendances |

### 3. La carte des dépendances inter-domaines (`mv_domain_dependency`)

**531 relations identifiées** entre les 7 domaines, via les champs partagés en clé primaire.

Exemple de ce qu'on découvre :
- Finance et Achats partagent **SETID** (432 records) et **BUSINESS_UNIT** → ces deux domaines sont fortement couplés
- Finance et RH partagent **DESCR** et **SETID** → il faut coordonner leur archivage

Cette carte est essentielle pour **définir l'ordre sécurisé d'archivage** : on n'archive pas un domaine sans vérifier que ses dépendants ne seront pas cassés.

### 4. Le classement des candidats par domaine (`v_archivability_by_domain`)

Pour chaque domaine, les **20 meilleures tables à archiver en premier**, classées par score d'archivabilité. Permet de prendre des décisions concrètes et ciblées par équipe métier.

---

## Ce que ça change concrètement

### Avant la modélisation

> « On a 87 000 tables dans Oracle. On ne sait pas lesquelles archiver, ni si ça impacte quelque chose. »

### Après la modélisation

> « Finance a 74 401 tables pour 535 Mo. Les 20 meilleures candidates à l'archivage dans ce domaine sont listées. Avant d'archiver Finance, il faut noter que ce domaine est lié à Achats (via SETID, 432 records partagés) et à RH (via DESCR). »

---

## Comment lire l'export Excel (`domain_model_run5.xlsx`)

| Feuille | Utilisation |
|---|---|
| **Domain Profile** | Vue d'ensemble : quel domaine est le plus volumineux, lequel a le plus de candidats ? |
| **Domain Dependencies** | Quelles paires de domaines sont liées et par quel champ ? |
| **Top Archival Candidates** | Quelles tables précises archiver en priorité dans chaque domaine ? |
| **Metadata** | Date de génération, run_id, compteurs de contrôle |

---

## Le niveau de risque d'archivage

| Niveau | Critère | Signification |
|---|---|---|
| **HIGH** | ≥ 10 dépendances sortantes en moyenne | Ce domaine est très référencé — archiver avec grande précaution |
| **MEDIUM** | 3–9 dépendances sortantes | Archivage possible avec vérification des impacts |
| **LOW** | < 3 dépendances sortantes | Archivage plus sûr — peu de tables dépendantes |

Sur le run_id=5, tous les domaines sont en **LOW** car la majorité des assets sont des "feuilles" dans la hiérarchie PeopleSoft (peu de dépendants directs en moyenne).

---

## Limites connues

- **`archival_candidates = 0`** sur run_id=5 : les scores d'archivabilité sont bridés par l'absence de données MongoDB (`purge_event_count = 0`, `term_count = 0`). Ce sera corrigé en section D lors de l'activation des données d'archivage réelles.
- **Dépendances via SETID/DESCR** : ces champs sont des clés de paramétrage transverses, pas des clés métier directes. Les vraies dépendances métier (VOUCHER_ID ↔ Finance/Achats) seront mieux quantifiées en section D.
