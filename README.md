# Paramétrage automatique des Sophos XGS

Un outil pour configurer un pare-feu **Sophos XGS**, **même sans être expert** :

1. **L'assistant** vous pose des questions simples sur le client. Il les explique toutes : tapez `?` à n'importe quelle question.
2. Il prépare toute la configuration dans un **fichier Excel**, que vous pouvez relire et modifier.
3. Il produit une **fiche récapitulative** : ce qui est configuré, ce qui reste à faire à la main, ce qu'il faut transmettre au client.
4. Le script **envoie la configuration au XGS** par son API, puis écrit un rapport.

```
 Assistant (questions)  ──►  clients/dupont.xlsx  ──►  script  ──►  XGS (API, port 4444)  ──►  rapport
                         └─►  clients/dupont_fiche.txt
```

---

## 1. Installation (une seule fois sur le PC)

**Le plus simple — sans rien installer :**
1. Téléchargez **SophosXGS.exe** depuis la page **Releases** du dépôt GitHub (dernière version, adresse fixe).
2. Rangez-le dans un dossier à lui, par exemple `Documents\SophosXGS`, puis double-cliquez dessus. Une **fenêtre** s'ouvre : les actions sont à gauche, et vous répondez aux questions en bas (zone de saisie ou boutons Oui / Non / Valeur proposée / Aide). Le programme crée ses dossiers (`clients`, `rapports`, `sauvegardes`) à côté de lui.
3. Il **se met à jour tout seul** : à chaque démarrage, il vérifie sur GitHub si une nouvelle version existe.
   - Si oui, il la télécharge et contrôle son empreinte SHA-256 par rapport à celle publiée par GitHub.
   - Il garde l'ancienne version en secours (`SophosXGS.ancien.exe`), installe la nouvelle et redémarre dessus.
   - Si une action est en cours, il attend qu'elle se termine.
   - Le fichier n'est jamais installé s'il est incomplet ou si son empreinte ne correspond pas.
   - Vous pouvez désactiver l'installation automatique dans « Mes paramètres » : le programme vous prévient alors seulement.
   - Sans Internet, rien ne change : le programme démarre normalement.

`SophosXGS-console.exe` est le même outil en mode texte.

**Ou avec Python :**

1. Installez **Python 3.10 ou plus récent** depuis <https://www.python.org/downloads/>.
   Sous Windows, **cochez « Add Python to PATH »** pendant l'installation.
2. Téléchargez ce dossier (bouton *Code > Download ZIP* sur GitHub), puis décompressez-le.
3. Double-cliquez sur **`installer.bat`**.
   Sinon, ouvrez un terminal dans le dossier et tapez `pip install -r requirements.txt`.

## Le menu principal

Double-cliquez sur **SophosXGS.exe**, ou sur `demarrer.bat`, ou tapez `python -m sophos_auto`. Tapez `q` pour quitter.

| N° | Fonction |
|---|---|
| 1 | Nouveau client, ou reprendre une configuration en cours (assistant) |
| 2 | Nouveau client à partir d'un client existant (mêmes objets et règles, infos client effacées) |
| 3 | **Diagnostic de connexion** : câble, adresse, API, IP autorisée, mot de passe — avec la solution |
| 4 | Appliquer un fichier client (simulation, puis envoi ; mode prudent ; seulement certains onglets) |
| 5 | Contrôle de sécurité, avec une **note sur 100** et un rapport HTML pour le client |
| 6 | Conformité : le pare-feu correspond-il toujours à son fichier ? (rapport HTML) |
| 7 | Revenir en arrière : annuler une application |
| 8 | Sophos Central : liste, inventaire Excel, sauvegarde d'un ou de **tous** les pare-feux, copie d'un modèle |
| 9 | **Dossier technique** du client (page HTML imprimable, sans mot de passe) |
| 10 | Liste des informations à demander au client |
| 11 | Voir les objets d'un pare-feu |
| 12 | Fichier Excel vierge |
| 13 | **Mes paramètres** : nom de votre société (affiché dans les rapports), e-mail du support, valeurs par défaut |
| 14 | Glossaire : les termes techniques expliqués |
| 15 | Mise à jour du programme |

## 2. Préparer le XGS (à chaque boîtier neuf)

**Avec Sophos Central — le plus rapide, sans assistant de démarrage en local :**
répondez « oui » à la question Zero Touch de l'assistant. La fiche du client contient alors la liste exacte des valeurs à saisir dans Central : n° de série, WAN, LAN, DHCP, fuseau, DNS.
- Saisissez-les dans **Central > Pare-feux > Ajouter > Zero Touch**.
- Branchez le port WAN sur Internet et allumez : le boîtier récupère seul sa configuration de base.
- Il ne reste qu'à activer l'API, puis à lancer le script pour tout le reste.

**Sans Zero Touch, en local (environ 5 minutes) :**

1. Branchez le PC sur le **Port1** du XGS. Le PC reçoit une adresse en 172.16.16.x.
2. Ouvrez `https://172.16.16.16:4444`, puis faites l'**assistant de démarrage Sophos** : mot de passe admin, enregistrement, licence.
3. Activez l'API : **Sauvegarde et firmware > API**
   - cochez **Configuration de l'API** ;
   - dans **Adresses IP autorisées**, ajoutez l'IP de votre PC. Pour la connaître : commande `ipconfig`, ligne « Adresse IPv4 » ;
   - si l'assistant vous indique une 2ᵉ adresse (cas où l'IP du LAN change), ajoutez-la aussi ;
   - cliquez sur **Appliquer**.

## 3. Lancer l'assistant

Menu 1, ou double-clic sur **`assistant.bat`**.

L'assistant commence par vous demander à quelle **situation** ressemble le client :

| Situation | Exemples |
|---|---|
| Petit bureau / commerce | Boulangerie, cabinet, agence : Internet + quelques PC |
| PME avec serveur(s) | Active Directory, serveur de fichiers, logiciel métier, télétravail |
| Multi-sites | Un siège et des agences à relier par VPN |
| Remplacement | On remplace un ancien pare-feu ou routeur en gardant les adresses |
| Je ne sais pas | Toutes les questions, sans présupposé |

La situation ne sert qu'à **proposer les bonnes réponses par défaut**. Ensuite, l'assistant aborde dans l'ordre :

| Étape | Ce qu'il demande |
|---|---|
| Internet | Port, type de connexion (box / IP fixe / PPPoE), IP publique, 2ᵉ accès en secours |
| Réseau local | Adresse du pare-feu, garder le plan d'adressage existant ou en créer un |
| Serveurs | Active Directory (avec liaison au pare-feu), NAS, NVR, IPBX, serveurs métier… |
| DHCP | Qui distribue les adresses, plage, réservations (imprimantes…) |
| VLAN | Téléphonie, caméras, serveurs, invités… avec les règles entre réseaux |
| Wi-Fi | Bornes Sophos : Wi-Fi salariés et Wi-Fi invités isolé |
| Protections | Accès Internet, filtrage web, IPS, contrôle d'applications, antivirus |
| Accès depuis Internet | Redirections de ports, avec mise en garde (RDP…) et filtrage par IP source |
| VPN entre sites | Tunnels IPsec, clé générée, consignes pour l'autre site |
| Télétravail | VPN SSL, comptes des utilisateurs, réseaux accessibles |
| Administration | Fuseau, DNS, compte admin nominatif, alertes e-mail, sauvegardes, SNMP |

Pendant l'assistant :
- `<` recommence l'étape en cours, `<<` revient à l'étape précédente ;
- vos réponses sont **enregistrées après chaque étape** (jamais les mots de passe). En cas de coupure, relancez l'assistant et choisissez « Reprendre ».

À la fin, l'assistant :
- crée `clients/<client>.xlsx` (la configuration) et `clients/<client>_fiche.txt` (le récapitulatif) ;
- **affiche les mots de passe générés une seule fois** : notez-les dans votre coffre-fort ;
- propose d'appliquer tout de suite : d'abord une **simulation**, puis l'envoi réel.

> La liste des informations à demander au client **avant** l'intervention est disponible dès la première question de l'assistant.
> Elle est aussi enregistrée dans `fiche_collecte.txt`.

## 4. Appliquer (ou ré-appliquer) un fichier Excel

```
python -m sophos_auto.deployer clients/dupont.xlsx --simulation    # vérifie, n'envoie rien
python -m sophos_auto.deployer clients/dupont.xlsx                 # applique
```

Vous pouvez aussi glisser le fichier Excel sur **`lancer.bat`**.

Avant d'envoyer quoi que ce soit, le script :
- **contrôle le fichier** : IP, masques, MAC, ports, doublons. Chaque erreur est affichée avec l'onglet et la ligne ;
- **vérifie sur le pare-feu** que les noms utilisés existent : zones, services, stratégies web/IPS, profils VPN… Sinon, il affiche ceux qui sont disponibles ;
- **demande les mots de passe** marqués `*demander*`. Ils ne sont jamais écrits dans les rapports.

Pendant l'application, le script :
- enregistre d'abord **l'état actuel** du pare-feu (`rapports/<client>_<date>_avant.json`), pour comparer ou revenir en arrière ;
- **relit ensuite le pare-feu** pour vérifier que chaque objet créé est bien présent ;
- lance enfin automatiquement le **contrôle de sécurité**.

Si l'adresse du pare-feu sur le LAN change, ce changement est fait **en dernier**. Le script vous demande alors de passer votre PC sur le nouveau réseau, se reconnecte, puis termine (par exemple le DHCP du LAN).

On peut **relancer sans risque** : ce qui existe déjà est mis à jour, rien n'est créé en double.

### Revenir en arrière (menu « Revenir en arrière »)

Choisissez l'application à annuler, d'après les fichiers `*_avant.json` du dossier `rapports`.
- Les objets créés depuis sont **supprimés**.
- Les réglages modifiés sont **remis comme avant**.

Le plan s'affiche d'abord et une confirmation est demandée. En ligne de commande : `python -m sophos_auto.restaurer rapports/<fichier>_avant.json --ip <IP>`.

### Conformité (menu « Vérifier qu'un pare-feu correspond toujours à son fichier »)

Compare un pare-feu à son fichier client, en lecture seule. C'est utile après le passage de quelqu'un d'autre, ou plusieurs mois plus tard : l'outil liste ce qui **manque** et ce qui a été **modifié**. Pour remettre en conformité, il suffit de ré-appliquer le fichier.

### Ce qui est maintenant automatique
- **Activation des tunnels IPsec** juste après leur création.
- **Inscription dans Sophos Central**, avec l'envoi des sauvegardes dans Central (question de l'assistant). Si Central refuse, par exemple à cause de la double authentification, l'outil l'indique comme « À FAIRE » avec la marche à suivre, sans bloquer le reste.

## 5. Contrôle de sécurité

Menu « Contrôle de sécurité », ou `python -m sophos_auto.audit --ip 192.168.1.254 --client "Dupont"`. Il fonctionne sur **n'importe quel XGS, même ancien ou configuré par quelqu'un d'autre**, en lecture seule.

Il signale notamment :
- l'administration ouverte sur Internet ;
- le bureau à distance (RDP), le partage de fichiers (SMB) ou une base de données publiés sur Internet ;
- les règles « tout autoriser » ;
- les accès Internet sans filtrage web, IPS ou antivirus ;
- l'absence de sauvegarde automatique ou d'alertes ;
- une communauté SNMP « public » ;
- un compte « admin » utilisé seul.

Le rapport HTML (`rapports/securite_*.html`) est **lisible par le client** : niveau de gravité, explication et marche à suivre.

## 6. Sophos Central

Il vous faut des **identifiants API** : dans Central, *Paramètres globaux > Identifiants API > Ajouter*, rôle **Service Principal Firewall**. Ils sont demandés à chaque utilisation et ne sont jamais enregistrés. Vous pouvez aussi les mettre dans les variables `SOPHOS_CENTRAL_ID` et `SOPHOS_CENTRAL_SECRET`.

Les comptes partenaire (MSP) sont pris en charge : l'outil vous demande de choisir le client.

| Fonction | Utilité |
|---|---|
| Voir mes pare-feux | Modèle, firmware, connecté ou non, IP publique |
| Sauvegarder un pare-feu | Télécharge sa configuration (`sauvegardes/*.tar`) à distance |
| Copier un pare-feu « modèle » | Vous configurez une fois un XGS de référence avec vos standards ; ses objets et règles sont copiés sur 1 à 25 pare-feux. Une sauvegarde de chaque cible est faite avant |
| Envoyer un fichier .tar | Restaurer ou déployer une configuration exportée |

Conditions fixées par Sophos pour l'export / import :
- **SFOS 22.0 MR2 ou plus récent** ;
- pare-feux gérés par Central ;
- abonnement payant ou contrat de support actif ;
- firmware des cibles **égal ou plus récent** que celui du fichier.

Sans la clé maître de stockage sécurisé (SSMK), les mots de passe et données sensibles ne sont pas copiés. Un import « réussi » signifie que Central l'a traité : vérifiez toujours le résultat sur le pare-feu.

**Méthode conseillée avec Central :**
1. Zero Touch pour la base.
2. « Copier le pare-feu modèle » pour vos standards.
3. L'assistant pour les spécificités du client.

## Nouveautés de la version 5

| Fonction | Où | Ce que ça fait |
|---|---|---|
| Fenêtre Windows | SophosXGS.exe | Boutons, couleurs et zone de réponse, à la place du terminal |
| Blocage par pays | Assistant « Sécurité avancée », onglet Général | Accès depuis Internet limités à la France, aux pays voisins ou à l'UE ; blocage complet de certains pays |
| Double authentification | Assistant « Télétravail » et « Sécurité avancée » | Code sur téléphone pour le VPN, et pour les administrateurs (appliqué en tout dernier) |
| Inspection HTTPS | Assistant « Sécurité avancée » | Règle de déchiffrement des postes du LAN. Les banques et sites de santé sont exclus par Sophos. Rappel pour installer le certificat sur les postes |
| Haute disponibilité | Assistant « Haute disponibilité » | Ce pare-feu en principal, plus un fichier `_secondaire.xlsx` à appliquer sur le second |
| SD-WAN | Onglet SD-WAN | Téléphonie sur le lien principal, bascule automatique sur le lien de secours |
| Priorité de débit | Onglet Priorités, colonne « Priorité (QoS) » des règles | Débit réservé à la téléphonie et à la visio |
| Boîtiers RED | Onglet RED, assistant « Agences RED » | Agences reliées par un RED, avec les règles siège ⇄ agence |
| Contrôles de sécurité | Menu Contrôle de sécurité | Profils VPN dépassés (DES, 3DES, MD5, DH 1/2/5) ; VPN et administration sans double authentification |
| Modèles par métier | Assistant, question « Secteur d'activité » | Santé, cabinet, commerce, école, industrie : VLAN conseillés, réglages par défaut et points de vigilance dans la fiche |
| Coffre KeePass | Fin de l'assistant | Tous les mots de passe du client dans un fichier `.kdbx` chiffré (KeePass ou KeePassXC) |
| Glossaire | Menu, ou `?? mot` à n'importe quelle question | 48 termes expliqués simplement |
| Mise à jour automatique | Au démarrage, et menu « Mise à jour du programme » | Vérifie GitHub, télécharge, contrôle l'empreinte SHA-256, garde l'ancienne version en secours, installe et redémarre |

Remarques :
- **Licences** : l'API locale du pare-feu ne donne pas leur date d'expiration. Consultez-la dans Sophos Central.
- **Noms de pays** : en anglais, comme dans le pare-feu (Hôtes et services > Groupes de pays).
- **À vérifier lors du premier essai sur un vrai boîtier** : les nouvelles fonctions (HA, RED, SD-WAN, inspection HTTPS) utilisent le format de la documentation officielle de l'API v21.

## Nouveautés de la version 4

**Contrôles du fichier, avant tout envoi :**
- réseaux qui se chevauchent : LAN, VLAN, Wi-Fi, réseaux distants des VPN, plage du VPN télétravail ;
- plage DHCP en dehors du réseau ou qui contient l'adresse du pare-feu ; réservations en double ;
- deux objets pour la même adresse. Un objet déjà déclaré est **réutilisé** au lieu d'être recréé ;
- **redirection dangereuse** (bureau à distance, partage de fichiers, base de données…) ouverte à tout Internet.

**Application :**
- nouvelles tentatives automatiques en cas de micro-coupure réseau ;
- progression affichée (`[12/47]`) et résumé de ce qui va être fait ;
- **mode prudent** (`--prudent`) : rien de ce qui existe n'est modifié, idéal sur un pare-feu déjà en production ;
- **application partielle** (`--seulement Règles,Hôtes`) ;
- **journal technique** (`--debug`), mots de passe masqués ;
- **rapport HTML** à remettre au client, au nom de votre société.

**Assistant :**
- fuseau horaire choisi dans une liste (France, Belgique, Suisse, DOM-TOM, Québec…) ;
- plage du VPN télétravail choisie automatiquement pour ne chevaucher aucun réseau ;
- **fiche « autre site »** pour chaque VPN, avec les réglages en miroir à transmettre à qui gère l'autre pare-feu ;
- **une fiche d'installation par télétravailleur** (sans mot de passe) ;
- dossier technique généré automatiquement à la fin.

**Contrôle de sécurité :**
- note sur 100 ;
- règles en double ;
- ping ouvert sur Internet ;
- export JSON pour suivre l'évolution d'un client.

**Sophos Central :**
- sauvegarde de tous les pare-feux en une fois ;
- inventaire Excel ;
- vérification du firmware avant export/import : SFOS 22.0 MR2 minimum, cibles au moins au niveau du modèle ;
- nouvelles tentatives automatiques si Central est surchargé.

## 7. Le fichier Excel

L'assistant le remplit pour vous, mais vous pouvez aussi l'écrire ou le corriger à la main. Partez de `modele_client.xlsx` ; ses lignes jaunes sont des exemples.

| Onglet | Contenu |
|---|---|
| Général | Nom, heure/NTP, DNS, alertes e-mail, sauvegardes, SNMP, VPN télétravail, Active Directory, lien de secours |
| Interfaces | Ports WAN/LAN : IP fixe, DHCP ou PPPoE |
| Zones, VLAN, Routes | Découpage du réseau et routes statiques |
| Wi-Fi | Réseaux Wi-Fi des bornes Sophos |
| Hôtes, Groupes, Services | Objets réutilisables |
| DHCP, Réservations DHCP | Distribution d'adresses |
| Comptes | Administrateurs et utilisateurs (avec accès VPN télétravail) |
| VPN sites | Tunnels IPsec site à site (les règles de pare-feu sont créées automatiquement) |
| Redirections | Accès depuis Internet (règle NAT + règle de pare-feu créées automatiquement) |
| Règles | Règles de pare-feu, avec filtrage web / IPS / contrôle d'applications / antivirus |

Astuces :
- Partout où un objet réseau est attendu, on peut écrire directement une adresse : `192.168.1.10`, `192.168.1.0/24` ou `192.168.1.10-192.168.1.20`. L'objet est créé automatiquement. Même chose pour les services : `TCP 8443`, `UDP 1194`.
- La colonne **Actif = Non** ignore une ligne sans la supprimer : pratique pour un « modèle maison » réutilisé d'un client à l'autre.
- Pour **voir ce qui existe déjà** sur un boîtier : `python -m sophos_auto.deployer --lire FirewallRule --ip 172.16.16.16`.

## ⚠️ Avant la première utilisation chez un client

Le format de chaque requête vient de la **documentation officielle de l'API Sophos Firewall (v21)**. L'outil a été testé sur un **pare-feu simulé**, mais **pas encore sur un vrai XGS**.

**Faites un premier essai complet sur un XGS de test ou de stock**, puis vérifiez le résultat dans l'interface web. Si une ligne échoue, le rapport (`rapports/`) donne le message exact du pare-feu.

Points à vérifier en priorité lors de ce premier essai :
- noms des stratégies d'origine : `Default Workplace Policy`, `lantowan_general`, `Block generally unwanted apps` et le profil IPsec `IKEv2`. Le script les vérifie et affiche les noms disponibles ;
- passerelle de secours (nommée `PortX_GW`) ;
- interfaces Wi-Fi (`wlnet1`, `wlnet2`…) ;
- activation automatique des tunnels IPsec et inscription dans Central : en cas d'échec, l'outil indique quoi faire à la main ;
- suppression d'un compte utilisateur lors d'un retour en arrière (format de suppression peu clair dans la documentation Sophos) ;
- export / import par Sophos Central : l'API est récente, faites un premier essai sur deux pare-feux de test.

Restent **manuels**, et sont rappelés dans la fiche :
- assistant de démarrage (ou Zero Touch dans Central), activation de l'API, licences, mise à jour du firmware ;
- configuration des switchs (VLAN) et validation des bornes Wi-Fi ;
- configuration du pare-feu d'en face pour les VPN entre sites.

## Messages d'erreur fréquents

| Message | Solution |
|---|---|
| Pare-feu injoignable | Vérifiez le câble, l'IP, et que `https://IP:4444` s'ouvre dans le navigateur |
| L'API n'est pas activée | Sauvegarde et firmware > API > cocher *Configuration de l'API* |
| L'adresse IP de ce PC n'est pas autorisée | Ajoutez l'IP du PC dans *Adresses IP autorisées* (même page) |
| Identifiant ou mot de passe incorrect | Vérifiez le compte admin |
| « … n'existe pas sur le pare-feu. Disponibles : … » | Remplacez le nom dans le fichier Excel par un des noms proposés |

## Organisation du code

| Fichier | Rôle |
|---|---|
| `sophos_auto/__main__.py` | Le menu principal |
| `sophos_auto/fenetre.py` | La fenêtre Windows |
| `sophos_auto/metiers.py`, `glossaire.py` | Modèles par métier, glossaire |
| `sophos_auto/coffre.py`, `mise_a_jour.py` | Coffre KeePass, mise à jour automatique |
| `sophos_auto/assistant.py` | L'assistant pas à pas |
| `sophos_auto/audit.py` | Contrôle de sécurité et rapport HTML |
| `sophos_auto/diagnostic.py` | Diagnostic de connexion |
| `sophos_auto/documentation.py` | Dossier technique HTML du client |
| `sophos_auto/parametres.py` | Vos paramètres (parametres.json) |
| `sophos_auto/restaurer.py` | Revenir en arrière à partir de l'état enregistré |
| `sophos_auto/conformite.py` | Comparaison pare-feu / fichier client |
| `.github/workflows/windows.yml` | Tests automatiques et construction de SophosXGS.exe |
| `sophos_auto/central.py` | Client de l'API Sophos Central (pare-feux, export, import) |
| `sophos_auto/schema.py` | Description des onglets et colonnes du fichier Excel |
| `sophos_auto/modele.py` | Contrôles et conversion Excel → requêtes Sophos |
| `sophos_auto/deployer.py` | Vérifications, envoi au pare-feu, rapport |
| `sophos_auto/api.py` | Client de l'API XML Sophos |
| `sophos_auto/classeur.py`, `creer_modele.py` | Écriture du fichier Excel / du modèle |
| `tests/` | Tests sur un faux XGS (`pip install pytest`, puis `python -m pytest`) |
