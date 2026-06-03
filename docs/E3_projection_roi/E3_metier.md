# E3 — Projection ROI multi-années : Fiche Métier

> **Statut :** ✅ Complet (modèle statistique) · **Devise :** USD · **Horizon :** 5 ans

---

## Qu'est-ce qu'on fait dans cette section ?

On projette sur **5 ans** le coût de stockage dans deux scénarios — **sans archivage** vs **avec archivage** — pour mesurer le retour sur investissement (ROI). Mais comme **personne ne connaît la croissance future**, on ne donne pas un chiffre unique : on donne une **fourchette honnête**.

---

## La nouveauté : on assume l'incertitude

Plutôt que d'affirmer « on économisera exactement X $ », on simule **2000 futurs possibles** (méthode de Monte-Carlo) où la croissance varie autour de 15 %/an. On obtient alors, pour chaque année :

- un scénario **médian** (P50) : le plus probable,
- une **fourchette basse → haute** (P10 → P90) : le réaliste pessimiste et optimiste,
- une **probabilité de rentabilité**.

> C'est la différence entre « je vous promets 13,62 $ » et « dans 8 cas sur 10, on économise entre 11 et 16 $, et c'est rentable à coup sûr ». La seconde phrase est crédible.

---

## Résultat réel — run 6

| Année | Coût cumulé sans archivage | Coût cumulé avec archivage | Économie nette (médiane) | Fourchette réaliste |
|---|---|---|---|---|
| Aujourd'hui | 2,16 $ | 0,66 $ | 1,51 $ | 1,51 $ |
| Dans 3 ans | 10,78 $ | 3,11 $ | 7,67 $ | 6,9 – 8,5 $ |
| Dans 5 ans | **18,88 $** | **5,26 $** | **13,62 $** | **11,3 – 16,1 $** |

**Sans rien faire, le coût cumulé est multiplié par ~9 en 5 ans** (effet de la croissance composée). Avec archivage, il reste **~3,6× plus bas**. La rentabilité est **certaine** sur la démo (P = 100 %), car le tiering cloud ne coûte quasiment rien à mettre en place.

---

## Le point d'honnêteté qui fait la différence

La croissance « 15 %/an » est une **hypothèse assumée**, pas une mesure. Pourquoi ? Parce que notre historique réel (cf. E2) est encore trop court et **non concluant** (le volume a même baissé entre les deux runs). Le modèle le **détecte tout seul** et refuse d'inventer une tendance :

> « Tant que l'historique réel n'est pas un signal fiable, on travaille sur une hypothèse prudente et **on l'affiche clairement**. Dès que les runs s'accumuleront, le modèle basculera automatiquement sur la croissance réellement observée. »

---

## Transposition à la production

Sur une vraie base d'entreprise, il y aurait un coût de mise en place. Le modèle répond alors directement à la question du décideur :

> « Quelle est la **probabilité** que ce projet d'archivage soit rentable d'ici 2 ans ? » — et non plus un chiffre unique trop beau pour être vrai.

---

## Ce que ça apporte au PFE

C'est l'**argument économique central, rendu défendable** :

> « L'archivage casse la courbe de coût liée à la croissance des données. Nous ne le promettons pas avec une fausse précision : nous le quantifions avec une fourchette et une probabilité, à partir d'un modèle reproductible. »
