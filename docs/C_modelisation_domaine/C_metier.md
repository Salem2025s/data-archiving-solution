# C — Modélisation logique par objet métier : Fiche Métier

> **Statut :** ✅ Complet  
> **Public cible :** Chef de projet, jury PFE, non-technicien

---

## Qu'est-ce qu'on fait dans cette section ?

À partir de la classification (section B), on **organise les données par domaine métier** et on **cartographie les clés métier partagées entre ces domaines**.

Concrètement : on sait maintenant que Finance a 74 401 tables, et que certains champs-clés (comme `SETID`, `BUSINESS_UNIT`) sont employés à la fois par Finance et Achats — un **couplage de vocabulaire à examiner** avant d'archiver (sans présumer pour autant d'une dépendance technique entre les deux).

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

### 3. La carte des **clés métier partagées** entre domaines (`mv_domain_dependency`)

> ⚠️ **Ce qu'elle est (et n'est pas).** PeopleSoft ne déclare pas de clés étrangères. Cette carte repère les domaines qui **utilisent le même nom de champ-clé** (ex. `SETID`, `BUSINESS_UNIT`). C'est un indicateur de **vocabulaire commun / couplage potentiel**, **pas** une dépendance référentielle prouvée : partager le nom `SETID` ne signifie pas qu'archiver un domaine casse l'autre.

**531 liens de clés partagées** identifiés entre les 7 domaines.

Exemple de ce qu'on découvre :
- Finance et Achats partagent **SETID** et **BUSINESS_UNIT** → vocabulaire de paramétrage commun
- Finance et RH partagent **DESCR** et **SETID** → champs transverses, à interpréter avec prudence

Utilité : **signaler les couplages à examiner** avant d'archiver (un même identifiant peut être utilisé de part et d'autre), sans surinterpréter ces liens comme des dépendances dures.

### 4. Le classement des candidats par domaine (`v_archivability_by_domain`)

Pour chaque domaine, les **20 meilleures tables à archiver en premier**, classées par score d'archivabilité. Permet de prendre des décisions concrètes et ciblées par équipe métier.

---

## Ce que ça change concrètement

### Avant la modélisation

> « On a 87 000 tables dans Oracle. On ne sait pas lesquelles archiver, ni si ça impacte quelque chose. »

### Après la modélisation

> « Finance a 74 401 tables pour 535 Mo. Les 20 meilleures candidates à l'archivage dans ce domaine sont listées. Finance utilise des champs-clés communs avec Achats (`SETID`) et RH (`DESCR`) — couplages de vocabulaire à vérifier, sans dépendance technique présumée. »

---

## Comment lire l'export Excel (`domain_model_run5.xlsx`)

| Feuille | Utilisation |
|---|---|
| **Domain Profile** | Vue d'ensemble : quel domaine est le plus volumineux, lequel a le plus de candidats ? |
| **Domain Shared Keys** | Quelles paires de domaines partagent un même champ-clé (vocabulaire commun) ? |
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

> Ici, « dépendances sortantes » = la **hiérarchie de records PeopleSoft** (`parentrecname`, record parent→enfant) — un lien structurel réel, à ne pas confondre avec le **graphe de clés partagées** ci-dessus (simple vocabulaire commun). C'est aussi cette hiérarchie, et non un vrai lignage de flux de données, que matérialise `fact_lineage_edge`.

---

## Limites connues

- **`archival_candidates = 0`** sur run_id=5 : les scores d'archivabilité sont bridés par l'absence de données MongoDB (`purge_event_count = 0`, `term_count = 0`). Ce sera corrigé en section D lors de l'activation des données d'archivage réelles.
- **Dépendances via SETID/DESCR** : ces champs sont des clés de paramétrage transverses, pas des clés métier directes. Les vraies dépendances métier (VOUCHER_ID ↔ Finance/Achats) seront mieux quantifiées en section D.
