# Equipamento local para KakA

Personagem KakA, ID 1024, guerreiro humano. O script
`tools/item-edit/edit_nirvana.py` prepara a edição sem gravar; `--apply` aplica
com desconexão dos clientes e banco de personagens offline. Não altera GM,
clã, territórios, habilidades, aparência ou os outros personagens.

| Posição | Item | ID | Refino | Pedras |
|---|---|---|---|---|
| Punho | ★Peak of Clouds | 34778 | +12 | 2 Drakeflame, ataque físico +100 cada |
| Elmo | ★Awakened Ancestral Divine Helm | 33308 | +12 | 4 Serenity, DEF LV +3 cada |
| Capa | ★Awakened Demon Obscure Robe | 34758 | +12 | 4 Serenity |
| Peitoral | ★Awakened Lionheart Armor | 32525 | +12 | 4 Serenity |
| Calças | ★Awakened Lionheart Cuisses | 32519 | +12 | 4 Serenity |
| Botas | ★Awakened Lionheart Greaves | 32531 | +12 | 4 Serenity |
| Braceletes | ★Awakened Lionheart Vambraces | 32513 | +12 | 4 Serenity |
| Colar | ★★Puzzle Cube Badge·Broken | 23614 | +12 | — |
| Cinto | ★★Warsong Lock·Naught | 24686 | +12 | — |
| Dois anéis | ★★Sky Cover | 26388 | +12 | — |

Punho: ATK LV +40, destreza +19, crítico +2%, intervalo −0,10 s.
Braceletes e capa também recebem intervalo −0,10 s. Os outros adicionais
são força, destreza e vitalidade; anéis também recebem crítico +4%.
Inventário: 64 espaços. Equipamentos substituídos são movidos para espaços
livres do inventário; voo e demais posições são preservados.

Os pontos disponíveis são distribuídos mantendo o total original. No nível
105: força 252, destreza 188, vitalidade 95, magia 5. Isso atende aos
requisitos do set pesado e do punho sem depender dos adicionais do próprio
equipamento.

Cada aplicação guarda em `backups/characters/KakA-1024-nirvana-<data>/`:
XML original, XML editado, XML exportado depois da importação, descrição dos
itens, log e cópia integral de `/home/dbhomewdb`. A verificação compara todos
os campos das seções principais do personagem, incluindo os itens antigos.
Em caso de falha de importação ou diferença, tenta restaurar o XML original
antes de reiniciar os serviços. Para restaurar manualmente, use a ferramenta
nativa `gamedbd gamesys.conf importrole <before.xml>` com o personagem e o
banco offline; nunca importe uma cópia enquanto o personagem estiver online.

Os catálogos locais do servidor (elements v156) e cliente (elements v159)
foram extraídos por `inspect_elements.py`; os campos numéricos dos itens,
pedras e adicionais escolhidos coincidem. O formato dos itens foi conferido
com o editor aberto [shadowvzs/pwAdmin](https://github.com/shadowvzs/pwAdmin)
e com os manipuladores de adicionais do binário local `gs`. A importação e
exportação verificam os dados persistidos; a aparência e o funcionamento em
combate ainda precisam ser conferidos dentro do cliente.
