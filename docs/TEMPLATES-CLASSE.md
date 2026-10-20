# Personagens novos: nível 100, skills e set Nirvana ★★

Aplicado em 25/09/2026. Todo personagem criado a partir de agora nasce com:

- **Nível 100**, pontos já distribuídos para usar o set (sobra em vitalidade);
  HP/MP base recalculados pelas mesmas fórmulas do `gs` (LevelUp/UpdateBasic).
- **2 chi** (chi máximo 200; cada fagulha custa 100). Adicionado em 25/09/2026,
  backup em `backups/class-templates/20260925-201414/`.
- **Todas as skills normais da classe** no nível máximo (10, ou o máximo da
  skill quando é menor).
- **Cultivo Demônio 3** (`level2` = 32) e **todas as skills evil (狂)** que os
  NPCs ensinam à classe (ranks 30/31/32, 27–46 por classe), no nível máximo.
  A skill normal fica na lista junto da versão evil, como o jogo faz ao aprender
  (o `gs` marca a normal como substituída ao carregar). Desde 27/09/2026, backup
  em `backups/class-templates/20260927-001857/`. Versões Sábio (真) ficam de fora.
- **Set Nirvana ★★ (grau 15) equipado, +12, com pedras**: arma com 2 Devil Stone
  (ATK LV +3) e 6 peças de armadura com 4 Serenity Stone (DEF LV +3) cada.
  As peças vêm sem adicionais aleatórios; o bônus do conjunto de 6 peças vale.
- **Moedas e teleporte** (desde 27/09/2026): 200.000.000 de moedas (o limite do
  `gs`; com mais que isso o gs01 cai ao criar/operar clã: assert em
  `playertrade.cpp:902`, `FactionTradeComplete`), 100 de
  cada Teleport Stone (Etherblade, Plume, Lost City, Archosaur, Dreamweaver Port,
  Thousand Streams; IDs 12860–12865) e 999 Teleport Incense (2100). Para dar o
  mesmo aos personagens já existentes: `python stock_roles.py [--apply]`.
- **Inventário**: Ruby Guardian Charm (amuleto, 12 milhões de HP) e Ruby Spirit
  Charm (hierograma, 18 milhões de MP).

| Classe | Arma | Armadura | For/Des/Mag/Vit |
|---|---|---|---|
| Blademaster | ★★Unicorn's Tragedy (machados) | Cascade Glow (pesada) | 287/54/5/169 |
| Barbarian | ★★Resonance of Pride (martelos) | Cascade Glow | 303/54/5/153 |
| Seeker | ★★Autumn Cresent (espada) | Cascade Glow | 252/146/5/112 |
| Wizard | ★★Glaive of Nirvana | Dragon Rise (arcana) | 54/5/297/159 |
| Psychic | ★★Buddha's Hatred (esfera) | Dragon Rise | 54/5/304/152 |
| Venomancer | ★★Glaive of Nirvana | Dragon Rise | 54/5/297/159 |
| Cleric | ★★Sandy World (espada mágica) | Dragon Rise | 54/5/285/171 |
| Mystic | ★★Foundation of World (varinha) | Dragon Rise | 54/5/289/167 |
| Stormbringer | ★★Dent of Destiny (foice) | Dragon Rise | 54/5/289/167 |
| Assassin | ★★Netherworld Guidance (adagas) | Myriad Blossom (leve) | 104/302/5/104 |
| Archer | ★★Jaden Emperor's Defiance (arco) | Myriad Blossom | 104/287/5/119 |
| Duskblade | ★★Streak of Sorrow (sabre) | Myriad Blossom | 104/302/5/104 |

Personagens já existentes não mudam.

## Local de nascimento

Desde 27/09/2026 todos nascem no ponto de renascimento da **Cidade das Feras**
(City of the Lost), mundo `gs01`: `(-1551.16, 261.37, 978.18)`, no mapa ≈ 245 648.
Antes era a zona inicial `is61` (worldtag 161), que não sobe mais (ver
`configs/gamed/start.sh`). Só `posx/posy/posz/worldtag` dos modelos mudam:

```powershell
cd 'D:\PW SERVER\perfectworld\tools\item-edit'
python set_spawn.py --scratch   # testa numa cópia descartável
python set_spawn.py --apply     # para glinkd/gamed/gamedbd, faz backup em backups/spawn/ e aplica
```

Para outro local, edite `WORLDTAG` e `POSITION` no topo de `set_spawn.py`.

Personagens já existentes fora do `gs01` são levados ao mesmo ponto com
`python move_roles.py` (prévia) / `python move_roles.py --apply`. Em 27/09/2026
foram movidos EP (1042) e DASDAS (1043); backup em `backups/move-roles/20260927-001739/`.

## Como funciona

O gamedbd copia os personagens-modelo 16–31 (tabela `clsconfig`) ao criar um
personagem. Os 12 modelos reais foram editados; os 4 vazios (gênero sem uso)
não. Na inicialização o gamedbd copia `/home/clsconfig` sobre a tabela, por isso
o script mantém as duas cópias iguais.

`exportrole` nativo falha nos modelos (não têm registro em `task`). A exportação
usa uma cópia do gamedbd com esse passo pulado
(`runtime/inspect/gamedbd-export-templates`, gerada pelo script e nunca usada
pelo servidor). Importação e `exportclsconfig` usam o binário original, e cada
modelo importado é reexportado e comparado campo a campo.

```powershell
cd 'D:\PW SERVER\perfectworld\tools\item-edit'
python inspect_class_data.py            # dados de skills/amuletos -> runtime/inspect
python edit_class_templates.py --scratch  # testa numa cópia descartável do volume
python edit_class_templates.py --apply    # para glinkd/gamed/gamedbd, faz backup e aplica
```

Para trocar itens, pedras ou nível, edite as constantes no topo de
`edit_class_templates.py`. O script recusa modelos que já não estejam no nível 1;
para refazer, restaure primeiro o backup.

## Backup e restauração

`backups/class-templates/20260925-150033/` contém a cópia integral de
`/home/dbhomewdb` e de `/home/clsconfig` anteriores, os XML antes/depois de cada
modelo e `loadout.json`. Para voltar ao original, com o gamedbd parado:

```powershell
docker compose stop perfectworld-glinkd perfectworld-gamed perfectworld-gamedbd
$c = docker compose ps -aq perfectworld-gamedbd
docker cp 'backups\class-templates\20260925-150033\clsconfig' "${c}:/home/clsconfig"
docker compose start perfectworld-gamedbd; docker compose start perfectworld-gamed perfectworld-glinkd
```

Só o `clsconfig` já basta para novos personagens voltarem ao padrão. Restaurar
`dbhomewdb` inteiro desfaz também tudo o que aconteceu no jogo depois do backup.

**Ainda não validado no cliente:** criação de um personagem de cada classe,
aparência dos itens e funcionamento das skills e dos amuletos.

## Gold (cash) das contas

Contas novas do registro recebem `USER_GOLD` = 100.000.000 (1.000.000 de gold) em
`docker-compose.yaml`. Para creditar uma conta existente:

```sql
CALL usecash(<userid>,1,0,1,0,<quantia>,1,@e);  -- @e = -8 é normal; o authd processa em segundos
SELECT * FROM usecashlog WHERE userid=<userid>;  -- status 4 = entregue
```
