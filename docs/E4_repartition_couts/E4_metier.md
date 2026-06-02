# E4 — Répartition des coûts par objet métier : Fiche Métier

> **Statut :** ✅ Complet · **Devise :** USD

---

## Qu'est-ce qu'on fait dans cette section ?

On calcule **combien coûte chaque domaine métier** et on identifie où concentrer l'effort d'archivage grâce à une analyse de Pareto.

---

## Résultat run_id=5

| Domaine | Coût annuel | Part du coût total |
|---|---|---|
| **IT & Sécurité** | 1,68 $ | **77,8 %** |
| Other | 0,32 $ | 14,8 % |
| Finance & Contrôle | 0,14 $ | 6,5 % |
| Supply Chain | 0,01 $ | 0,5 % |
| Achats, Ventes, RH | < 0,01 $ | < 1 % |

---

## L'analyse de Pareto (la règle du 80/20)

> **IT & Sécurité représente à lui seul 77,8 % du coût de stockage.**
> **IT + Other = 92,6 %** du coût total.

Conclusion claire : **2 domaines sur 7 concentrent l'essentiel du coût**. Pour maximiser l'impact de l'archivage, on commence par **IT & Sécurité**, puis **Other**. Les 5 autres domaines sont négligeables en coût.

---

## Pourquoi IT & Sécurité domine-t-il ?

Ce domaine contient les grosses tables techniques de PeopleSoft (logs, programmes, métadonnées système comme PTIACPTMPLTFQUS à 2,2 Go). Ce sont précisément des données techniques anciennes, idéales pour l'archivage à froid.

---

## Ce que ça apporte au projet

- **Priorisation immédiate** : on sait par quel domaine commencer (IT & Sécurité)
- **Effort ciblé** : inutile de traiter les 7 domaines — 2 suffisent pour 92 % du gain
- **Visualisation** : la colonne de coût cumulé permet de tracer une courbe de Pareto dans le rapport Excel
- **Discours décisionnel** : « Concentrons-nous sur IT & Sécurité : c'est 78 % du coût et le plus gros gisement d'archivage. »

---

## Note de lecture

Sur cette instance démo, le « potentiel d'optimisation » est *Très élevé* pour tous les domaines (car ~98 % des données sont anciennes et donc archivables). Le vrai discriminant est donc le **classement par coût** (Pareto), qui pointe sans ambiguïté vers IT & Sécurité.
