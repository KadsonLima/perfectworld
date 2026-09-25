# Gameservers, mapas e TW: evidências da imagem

## Escopo e estado

Inspeção em 18/09/2026, sem alterar a configuração operacional nem iniciar batalhas.
Imagem gamed fixada em sha256:702e8e2da7816e73528d444af0ef7248e7f13a5e46e10a58207c72299ceadb25.
Foi lido por streaming o tar da camada de dados indicada pelo manifest, sem executar binários.
Os arquivos centrais foram extraídos após transferir 1.201.080.320 bytes comprimidos.
O streaming foi interrompido após encontrar ambos os arquivos: o digest da camada inteira
não foi recalculado. Arquivos são evidência estática, não prova de funcionamento.
Docker continua indisponível. Nenhum mapa, login ou TW foi validado em execução.

## Cadeia de inicialização

Compose seleciona perfectworld-gamed. A imagem tem ENTRYPOINT `sh /home/entrypoint.sh`.
O entrypoint gera gmserver.conf via envsubst do template e executa o CMD.
No Compose local, CMD é `sh /home/start.sh`. O script muda para /home e executa gs em foreground.
O original executava gs em background e mantinha o container com tail /dev/null.

O comando real tem a estrutura:

```text
./gs gs01 gs.conf gmserver.conf gsalias.conf is01 ... is83 bg01 bg02 bg03 bg04 bg05 bg06 arena01 arena02 arena03 arena04 rand03 rand04
```

As reticências resumem a lista; não são argumentos executáveis.
A lista exata está em configs/gamed/start.sh. Um único processo gs recebe todos esses nomes.
gs01 consta em world_servers e possui World_gs01 com index=1, tag=1 e base_path=world/.
gs.conf tem World_gs02__, Terrain_gs02__ e receivers gs02__, mas esse nome não aparece
em world_servers nem no script. Não foi encontrado gs03 nos arquivos centrais ou scripts.
Não há serviços Compose gs02/gs03 ou um container por mapa.

## Arquivos que controlam os mapas

| Arquivo em execução | Cópia disponível no workspace | Papel |
| --- | --- | --- |
| /home/start.sh | configs/gamed/start.sh | Lista explícita passada ao processo gs |
| /home/gs.conf | audit/images/gamed/stream-files/home/gs.conf | Listas world_servers/instance_servers, definições de mundo/instância, terreno, limites e receivers |
| /home/gsalias.conf | audit/images/gamed/stream-files/home/gsalias.conf | Aliases de endereço de mundos/instâncias |
| /home/gmserver.conf | gerado de configs/gamed/gmserver.conf.tmpl | Conexões com delivery, faction, glink, gamedbd e logservice |
| /home/config/ | dados da imagem; configs auxiliares extraídas em audit/images/gamed/stream-files/home/config/ | Assets, terreno, NPCs, rotas, tasks e elements |
| /home/gamesys.conf no delivery | gerado de configs/gdeliveryd/gamesys.conf.tmpl | battlefield, battle_time_mode, BattleBonus e outros eventos |

gs.conf e gsalias.conf do audit são cópias para investigação; não foram montados pelo Compose.
Os arquivos reais usados pelo container permanecem no volume pw-gamed-home.

## Campos de batalha encontrados

| Instância | index | tag | Pasta de assets | Objetivo configurado | Alias TCP | Socket UNIX |
| --- | --- | --- | --- | --- | --- | --- |
| bg01 | 60 | 230 | /home/config/b30/ | destroy_key_building | BATTLEGROUND01:10961 → game3 | /tmp/gssock_bg01 |
| bg02 | 61 | 231 | /home/config/b31/ | kill_all_mobs | BATTLEGROUND02:10962 → game2 | /tmp/gssock_bg02 |
| bg03 | 62 | 232 | /home/config/b32/ | destroy_key_building | BATTLEGROUND03:10963 → game2 | /tmp/gssock_bg03 |

As três têm battleground_server=1, battle_player_count=80 e instance_capacity=20.
bg04–bg06 também têm battleground_server=1 e constam no comando de inicialização.
O objetivo está escrito `battle_destionation` no arquivo original; não corrigir a grafia
sem verificar o parser do binário.

Os diretórios b30/b31/b32 foram encontrados na camada e contêm configs de movimento,
água e espaço aéreo. Isso não prova que todos os assets sejam válidos.
Os aliases game1/game2/game3 aparecem em gsalias.conf; Compose e entrypoints não os definem.
Pode haver necessidade de resolução/ajuste de aliases, mas falha de bind não foi observada
em execução. Verificar `getent hosts game1 game2 game3` dentro do container após subir Docker.
Não mapear esses nomes a hosts arbitrários sem conferir os receivers e logs.

## TW desativada por padrão?

Não há evidência de desativação das instâncias bg: estão em instance_servers, no script
e com battleground_server=1. Delivery tem battlefield=1 e battle_time_mode=0.
O significado exato do modo 0 não está documentado no projeto, que não fornece o código
do delivery. Não é possível afirmar que modo 0 desliga TW, nem recomendar modo 1 sem verificação.

Carregar o servidor de campo de batalha não é o mesmo que criar uma batalha ativa para
um território. Não foi encontrado comando administrativo documentado para forçar uma TW.
COUNTRYBATTLE, TANKBATTLE, FACTIONRESOURCEBATTLE e MNFBATTLE têm configurações próprias;
não usar seus flags/horários como prova do agendamento da TW territorial comum.

## Serviços e início manual

Para o fluxo completo de login e batalha, manter gamed (processo gs), gamedbd,
gdeliveryd, gfactiond, glinkd, authd, uniquenamed, gacd, logservice e MySQL.
O cadastro web não participa da execução de mapas.
gmserver.conf mostra conexões diretas do gs ao delivery, faction, glink, gamedbd e logservice.
As dependências de Compose indicam ordem de início, sem provar prontidão de cada daemon.

Com Docker funcionando, na pasta perfectworld:

```powershell
# Inicia o gameserver e dependências; a lista já inclui bg01-bg06.
docker compose up -d perfectworld-gamed
# Reinicia o mesmo processo com a lista atual.
docker compose restart perfectworld-gamed
# Confere argumentos e processos.
docker compose top perfectworld-gamed
```

Para diagnóstico manual em foreground com mundo principal e apenas bg01–bg03,
deixe os demais subsistemas rodando e pare o gs existente primeiro:

```powershell
docker compose stop perfectworld-gamed
docker compose run --rm --no-deps perfectworld-gamed /home/gs gs01 /home/gs.conf /home/gmserver.conf /home/gsalias.conf bg01 bg02 bg03
```

O one-off passa pelo entrypoint da imagem, que gera gmserver.conf. Esse comando foi
derivado da invocação real do script, mas ainda não foi testado por indisponibilidade do motor.
Ele omite as demais instâncias durante o diagnóstico e não dispara uma batalha TW.
Não execute em paralelo ao gamed normal: IDs, sockets e volumes são compartilhados.
Após encerrar o diagnóstico, restaure o serviço normal com `docker compose up -d perfectworld-gamed`.

## Logs e evidências de carregamento

```powershell
docker compose ps -a
docker compose top perfectworld-gamed
docker compose logs -f --tail=200 perfectworld-gamed perfectworld-gdeliveryd perfectworld-gamedbd perfectworld-gfactiond perfectworld-glinkd perfectworld-logservice
docker compose exec perfectworld-gamed sh -c 'ls -l /tmp/gssock_bg01 /tmp/gssock_bg02 /tmp/gssock_bg03'
docker compose exec perfectworld-gamed getent hosts game1 game2 game3
```

gs stdout/stderr mostra carregamento/erros locais; delivery deve ser observado para
coordenação das batalhas; gamedbd para persistência; faction para estado de facções;
glink para a sessão/entrada do jogador. logservice usa /dev/stdout em fd_err, fd_log,
fd_trace e demais saídas, então seus logs Docker incluem logs recebidos dos subsistemas.
Não foi comprovado que exista world2.err ou outro arquivo de log tradicional nesta imagem.
Sockets presentes e processo vivo são sinais auxiliares; arquivos de socket podem ficar
obsoletos e não demonstram que uma batalha ativa foi criada.
Procure mensagens relativas a bg01-bg03, tags 230–232, battle, city, territory, failures
de assets, registro de provider, conexão ao delivery/banco e falhas de resolução/bind.
Não foi encontrado um texto exato de sucesso para usar como critério automático.

## Validação dentro do jogo

Ainda não foi feita; exige cliente compatível 1.5.5/2567 e cenário válido de batalha.
Critério proposto: usar o fluxo de inscrição/entrada de guerra territorial do cliente,
com facção/personagem elegível e batalha agendada/ativa, entrar no campo de batalha e
confirmar movimentação, NPCs/objetivos e, em PvP, jogadores dos dois lados na mesma batalha.
Correlacionar horário, personagem e batalha com os logs do delivery/gs.
Se o cliente ou logs exibirem map/world tag, comparar com 230/231/232 para bg01/bg02/bg03;
o número de território não deve ser tratado automaticamente como esse tag.
Sem observar essa identificação, entrada em um campo de batalha valida aquele cenário,
mas não comprova qual nome bg corresponde a ele. Testar bg01 não valida bg02/bg03.

Login no mundo principal ou botão de território habilitado não comprova carregamento de bg.
Falha de entrada também pode ser causada por agenda/elegibilidade/estado territorial,
sem implicar que o servidor de instância está desligado. Não foi encontrado neste projeto
um comando GM de teleporte/criação de batalha que possa ser recomendado com segurança técnica.

## Protocolo de debug do delivery (packet 873): mapeado e testado em 18-19/09/2026

`tools/admin/rpc.php` já usava esse protocolo (tags 4, 5 e 999) sem documentação do
significado de cada tag. Investigação feita via `strings`, `nm -C`, `objdump -d -C`
e `readelf` dentro do container `perfectworld-gdeliveryd` (binário não stripado),
sem alterar o binário, e confirmada com testes reais (não é só leitura estática).

### Como o dispatcher funciona

`GNET::DebugCommand::Process(GNET::Protocol::Manager*, unsigned int)` (endereço
0x081fba02 no binário testado) valida `tag <= 0x140` (320) e usa uma jump table de
321 ponteiros em 0x084b0894 (`tag * 4` como índice) para saltar direto ao case.
Índice N da tabela = tag N (confirmado batendo índice 4 com `BattleManager::TestBattle`
e índice 5 com `BattleManager::SetOwner`, os dois já usados e validados por este projeto).
Cada case lê o payload em texto (formato varia por case, geralmente `%d-%d...` via
`sscanf`) e chama um método de alguma classe singleton (`GetInstance()->Metodo(...)`).

### Tags confirmadas por uso real (já existentes em rpc.php)

| tag | classe/método | payload | efeito confirmado |
| --- | --- | --- | --- |
| 4 | `BattleManager::TestBattle(int,int)` | `cidade-atacante` | dispara `BattleStart_Re` (aceita batalha na memória do delivery); não abre janela de arrecadação |
| 5 | `BattleManager::SetOwner(int,int)` | `cidade-dono` | grava `owner` na tabela `city` (reflete em `listcity`/UI do cliente), com até ~60s de atraso pelo timer interno |
| 999 | não mapeado na jump table (>320, cai no default) | qualquer | só confirma que o delivery recebeu o pacote; não executa nada |

### Tag nova testada: 312 (CDS_MNFactionBattleMan::SetDomainInfo) — não serve para isto

Índice 312 da jump table (endereço 0x081fec91) chama
`GNET::CDS_MNFactionBattleMan::SetDomainInfo(int domain_id, unsigned int attacker_fid, int attacker_zoneid, unsigned int defender_fid, int defender_zoneid)`,
com payload em texto `"%d-%d-%d-%d-%d"` (formato extraído do binário em 0x084b05d7).
Teste real enviado (`4-1-1-2-1`, território 4, atacante fid 1, defensor fid 2) foi
recebido e processado exatamente como esperado — log confirma
`SetDomainInfo() domain_id=4, attacker_fid=1,attacker_zoneid=1,defender_fid=2,defender_zoneid=1`.
Porém, mais de 60s depois, `listcity` continuava com `challenger=0` para o território 4:
**`CDS_MNFactionBattleMan` é um subsistema separado do `BattleManager`, com seu próprio
mapa de domínios em memória, não sincronizado com a tabela `city` que `listcity` e o
cliente leem.** Ou seja, essa tag existe e funciona, mas não é o sistema de território
que a UI do cliente (painel "Held by/Attacker/Time/Max Refund") usa.

### Não existe tag de debug que declare guerra no BattleManager

`BattleManager` tem os métodos `Challenge(Protocol const&, Protocol&)`,
`ChallengeMap(int,int)`, `BeginChallenge()` e `EndChallenge()` — candidatos óbvios para
"declarar guerra de verdade" (preencher `challenger`/`deposit`/`cutoff_time`). Mapeando
os 49 endereços únicos alcançáveis pela jump table do `DebugCommand::Process`
(todos os índices não-default, comparados via `objdump -d -C`), **nenhum deles chama
qualquer um desses quatro métodos**. `BattleManager::Challenge` só é acionado a partir
de um `GNET::Protocol` real (pacote de rede do cliente do jogo), não pelo protocolo de
debug interno (packet 873).

**Conclusão:** não existe atalho de servidor (debug/SQL/RPC) para declarar guerra
territorial de verdade neste binário. O campo `challenger` da tabela `city` só pode ser
preenchido passando pelo fluxo real do NPC de guerra territorial no cliente do jogo.
Isso deixa de ser uma lacuna de documentação e passa a ser um fato confirmado pelo
binário: não adianta procurar mais nenhum comando de servidor para isso.
