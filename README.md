# Paramétrage automatique des Sophos XGS

Cet outil configure un pare-feu **Sophos XGS** à partir d'un **fichier Excel** rempli pour chaque client.
Plus besoin de tout cliquer dans l'interface web : on remplit le tableau, on branche le PC, on lance une commande.

```
 Fichier Excel du client  ──►  script  ──►  API du XGS (port 4444)  ──►  rapport
```

## Ce que l'outil configure

| Onglet Excel | Ce que ça crée sur le XGS | Où le voir dans l'interface |
|---|---|---|
| Général | Nom d'hôte du pare-feu | Administration > Paramètres d'administration |
| Zones | Zones personnalisées (ex. SERVEURS, INVITES) | Réseau > Zones |
| VLAN | Sous-interfaces VLAN avec leur IP | Réseau > Interfaces |
| Hôtes | Objets IP, réseau, plage d'IP, FQDN | Hôtes et services |
| Groupes | Groupes d'hôtes IP | Hôtes et services > Groupe d'hôtes IP |
| Services | Services TCP/UDP personnalisés | Hôtes et services > Services |
| Règles | Règles de pare-feu, dans l'ordre du tableau | Règles et stratégies |

Le reste (DHCP, NAT, VPN, filtrage web, etc.) pourra être ajouté ensuite.

---

## Installation (une seule fois sur le PC)

1. Installez **Python 3.10 ou plus récent** depuis <https://www.python.org/downloads/>.
   Sous Windows, **cochez « Add Python to PATH »** pendant l'installation.
2. Téléchargez ce dossier sur le PC (bouton *Code > Download ZIP* sur GitHub, puis décompressez).
3. Ouvrez une invite de commandes **dans ce dossier**. Sous Windows : clic droit dans le dossier > *Ouvrir dans le terminal*.
4. Installez les dépendances :
   ```
   pip install -r requirements.txt
   ```

## Préparer le XGS (à chaque boîtier neuf, environ 5 minutes)

1. Branchez le PC sur le **Port1** du XGS. Le PC reçoit une IP en 172.16.16.x.
2. Ouvrez `https://172.16.16.16:4444` et faites l'**assistant de démarrage** comme d'habitude : mot de passe admin, enregistrement, licence.
3. Activez l'API : **Sauvegarde et firmware > API**
   - cochez **Configuration de l'API** (*API configuration*) ;
   - dans **Adresses IP autorisées**, ajoutez l'IP de votre PC. Pour la connaître : commande `ipconfig`, ligne *Adresse IPv4* ;
   - cliquez sur **Appliquer**.

## Utilisation (pour chaque client)

1. **Copiez** `modele_client.xlsx` sous un nouveau nom, par exemple `clients/dupont.xlsx`.
2. **Remplissez-le.** Les lignes **jaunes** sont des exemples : modifiez-les, supprimez-les, ou mettez `Non` dans la colonne *Actif*.
   Survolez un en-tête de colonne pour afficher l'aide.
3. **Vérifiez** le fichier sans rien envoyer au pare-feu :
   ```
   python -m sophos_auto.deployer clients/dupont.xlsx --simulation
   ```
   Les erreurs (IP invalide, masque faux, nom en double…) s'affichent en rouge, avec l'onglet et le numéro de ligne.
4. **Appliquez** la configuration :
   ```
   python -m sophos_auto.deployer clients/dupont.xlsx
   ```
   Le mot de passe admin est demandé à ce moment-là. Il n'est **jamais** enregistré.
5. Un **rapport** est créé dans le dossier `rapports/`.

Sous Windows, vous pouvez aussi **glisser le fichier Excel sur `lancer.bat`**.

### Bon à savoir

- **On peut relancer sans risque.** Si un objet existe déjà, il est **mis à jour** et non recréé en double.
  Vous pouvez donc corriger le fichier Excel puis relancer.
- **Les objets d'origine du XGS n'ont pas besoin d'être créés.** Par exemple les zones `LAN`, `WAN`, `DMZ`, ou les services `HTTP`, `HTTPS`, `DNS`, `NTP`.
  Si une règle les utilise, l'outil affiche simplement un avertissement jaune.
- **Un « modèle maison »** : mettez vos standards (objets, services, règles) dans `modele_client.xlsx`.
  Chaque nouveau client part de cette base, et il ne reste qu'à adapter ses spécificités.
- **Voir ce qui existe déjà** sur un boîtier, par exemple pour comprendre un format :
  ```
  python -m sophos_auto.deployer --lire FirewallRule --ip 172.16.16.16
  ```
  Types utiles : `IPHost`, `Services`, `Zone`, `VLAN`, `Interface`, `FirewallRule`, `DHCPServer`.

### Premier essai conseillé

Faites le premier essai sur un **XGS de test ou de stock**, pas chez un client.
Vérifiez ensuite dans l'interface web que tout est correct, notamment les **VLAN**. Ce format n'a pas encore été validé sur un vrai boîtier.
Si une ligne échoue, le rapport donne le message exact renvoyé par le pare-feu.

## Messages d'erreur fréquents

| Message | Solution |
|---|---|
| Pare-feu injoignable | Vérifiez le câble, l'IP, et que `https://IP:4444` s'ouvre dans le navigateur |
| L'API n'est pas activée | Sauvegarde et firmware > API > cocher *Configuration de l'API* |
| L'adresse IP de ce PC n'est pas autorisée | Ajoutez l'IP du PC dans *Adresses IP autorisées* (même page) |
| Identifiant ou mot de passe incorrect | Vérifiez le compte admin |
| `... absent du fichier : il doit déjà exister` (jaune) | Normal pour LAN, WAN, HTTPS… Sinon, vérifiez l'orthographe du nom |

## Pour les curieux : organisation du code

- `sophos_auto/api.py` : envoi des requêtes XML à l'API du XGS.
- `sophos_auto/modele.py` : description des onglets Excel, contrôles et conversion en XML Sophos.
- `sophos_auto/creer_modele.py` : génère `modele_client.xlsx` (`python -m sophos_auto.creer_modele`).
- `sophos_auto/deployer.py` : le programme principal.
- `tests/` : tests sur un faux pare-feu (`pip install pytest`, puis `python -m pytest`).
