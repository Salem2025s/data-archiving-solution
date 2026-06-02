# E3 — Projection ROI multi-années : Fiche Métier

> **Statut :** ✅ Complet · **Devise :** USD · **Horizon :** 5 ans

---

## Qu'est-ce qu'on fait dans cette section ?

On projette sur **5 ans** deux scénarios pour mesurer le retour sur investissement (ROI) de l'archivage :
1. **Sans archivage** : la base grossit de 15 %/an, le coût grimpe
2. **Avec archivage** : les données anciennes passent en stockage froid, le coût est maîtrisé

---

## Résultat run_id=5

| Année | Sans archivage | Avec archivage | Économie cumulée |
|---|---|---|---|
| Aujourd'hui | 2,16 $/an | 0,41 $/an | 1,75 $ |
| Dans 1 an | 2,49 $/an | 0,45 $/an | 3,79 $ |
| Dans 3 ans | 3,29 $/an | 0,53 $/an | 8,92 $ |
| Dans 5 ans | **4,35 $/an** | **0,62 $/an** | **15,86 $** |

**Sans rien faire, le coût double en 5 ans** (effet de la croissance composée). Avec archivage, il reste quasi stable.

---

## Rentabilité immédiate

Comme on utilise du **tiering cloud** (déplacer S3 → Glacier), il n'y a quasiment **aucun coût de mise en place** : le projet est rentable dès le premier jour. Chaque dollar dépensé en stockage actif évité est un dollar économisé.

---

## Transposition à la production

Sur une vraie base d'entreprise, il y aurait un coût de mise en place (projet, outillage). Le ROI se mesurerait alors en délai d'amortissement :

> Exemple : 10 To à archiver → 2 335 $/an économisés. Un projet d'archivage à 5 000 $ serait **remboursé en ~2 ans**, puis génèrerait 2 335 $/an d'économie nette.

---

## Ce que ça apporte au PFE

C'est l'**argument économique central** :

> « L'archivage intelligent casse la courbe de coût liée à la croissance des données. Sur la démo, il réduit le coût de 80 % dès la première année. À l'échelle production, il s'amortit en ~2 ans et génère des économies récurrentes. »
