# Bloc 2 · C2.1.4 — Tests d'hypothèses (run 9)

Seuil de signification : **α = 0,05**. Données réelles de la couche serving.

## H1 — La complexité structurelle (nombre de colonnes) diffère-t-elle selon le domaine métier ?

- **H0** : Les distributions du nombre de colonnes sont identiques entre domaines.
- **H1** : Au moins un domaine a une distribution différente.
- **Test** : Kruskal-Wallis (non paramétrique, 7 domaines, n = 60284)
- **Résultat** : H = 12783.3 · epsilon² = 0.212 (fort)
- **Décision** : p < 0,001 < 0,05  →  on REJETTE H0
- **Interprétation** : Médianes de colonnes par domaine : Finance & Contrôle 17 · Ventes & Clients 16 · Supply Chain / Logistique / Production 14 · Achats & Fournisseurs 10 · RH 8 · IT & Sécurité 7 · Other 4. Les tables Finance sont structurellement plus riches que celles d'IT/Other, ce qui oriente la modélisation métier et la priorisation de la documentation.

## H2 — La taille d'une table est-elle corrélée à son nombre de colonnes ?

- **H0** : Il n'existe pas de corrélation monotone (rho = 0).
- **H1** : Il existe une corrélation monotone (rho ≠ 0).
- **Test** : Corrélation de Spearman (n = 15854)
- **Résultat** : rho = 0.368 · corrélation modérée
- **Décision** : p < 0,001 < 0,05  →  on REJETTE H0
- **Interprétation** : Spearman choisi car les tailles suivent une loi très asymétrique (quelques très grosses tables) — un test de Pearson serait tiré par les valeurs extrêmes.

## H3 — L'absence de description dépend-elle du domaine métier ?

- **H0** : La présence d'une description est indépendante du domaine.
- **H1** : La présence d'une description dépend du domaine.
- **Test** : Test du χ² d'indépendance (ddl = 6, n = 167260)
- **Résultat** : χ² = 3681.5 · V de Cramér = 0.148 (faible)
- **Décision** : p < 0,001 < 0,05  →  on REJETTE H0
- **Interprétation** : Enjeu gouvernance : une documentation inégale entre domaines cible les efforts de complétion des métadonnées.

## H4 — La confiance des règles mots-clés diffère-t-elle de celle du modèle ML ?

- **H0** : Les deux méthodes produisent des confiances de même distribution.
- **H1** : Les distributions de confiance diffèrent.
- **Test** : Mann-Whitney U (keyword n = 44568, ML n = 122692)
- **Résultat** : U = 4577750135 · rang-bisérial = -0.674
- **Décision** : p < 0,001 < 0,05  →  on REJETTE H0
- **Interprétation** : Médianes : keyword 0.833 · ML 0.680. Confirme que les deux passes ne sont pas interchangeables (calibrage distinct).
