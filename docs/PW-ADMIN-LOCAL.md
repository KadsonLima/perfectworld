# PW Admin local e TW de teste

O painel roda no Windows e administra o Compose deste diretório. Não é uma
instalação do pwAdmin JSP: a integração foi implementada especificamente para os
containers e a imagem 1.5.5 fixada neste projeto.

## Abrir

```powershell
cd 'D:\PW SERVER\perfectworld'
.\start-admin.ps1
```

Abra http://127.0.0.1:8090. O painel aceita acesso somente nesta máquina, valida
Host e exige token CSRF nas alterações. Python e Docker são os únicos requisitos
no host. O protocolo interno é enviado por PHP no container de cadastro, sem
publicar as portas internas ou montar o socket Docker em um painel web.

## Controle manual de lances

Na seção **Lances de Guerra Territorial**, use **Abrir lances**, **Fechar lances**
ou **Voltar à agenda automática**. A confirmação pode levar até 80 segundos.
O estado usa eventos `beginbid`/`endbid` do BattleManager desde a inicialização
atual do delivery. `CountryBattle` pertence a outro sistema e não é usado.

O protocolo 873, tag 1, chama `BattleManager::SetForgedTime(long)` nesta versão:
`327601` fixa o horário dentro da janela de lances; `416521` o fixa depois do
limite máximo acrescido de 120 segundos; `0` restaura o relógio normal.
Os valores representam segundos desde o domingo, não timestamps Unix.
O binário é verificado por SHA-256 antes de enviar esses comandos.

**Agendamento de cinco minutos (19/09/2026):** o delivery local agenda as TW
selecionadas pela rotina nativa para o horário real do encerramento + 300 segundos.
O início é verificado pelo timer nativo a cada 60 segundos, portanto pode haver
até um ciclo de atraso. A regra vale para novos agendamentos; horários já
persistidos não são reescritos retroativamente.

O horário simulado continua controlando os lances, mas a progressão das batalhas,
o timeout de início e os registros de início/fim usam o horário real. Não é mais
necessário voltar ao automático para a batalha começar. Voltar ao automático
durante a janela semanal pode reabrir os lances. Reiniciar o delivery restaura o
horário normal de lances; reiniciar somente o painel não altera o modo manual.
Fechar uma rodada não cancela seus lances: o servidor processa os resultados.
Reabrir é recusado quando existe disputa registrada ou reserva de TW de teste.

As ações exigem CSRF e acesso local, são serializadas e registradas em
`runtime/admin/actions.jsonl`. Timeout significa resultado não confirmado,
nunca sucesso presumido. Consulte o estado antes de repetir.

Validação automatizada: `python tools/admin/test_bids.py` verifica transições,
timeout, retomada automática, rejeição de ações inválidas e disputas existentes
sem alterar territórios. `check_admin.py` verifica as rotas do painel em execução.
A aceitação de um lance no cliente ainda precisa de validação dentro do jogo.

### Binário e teste do agendamento

Compose monta `runtime/patches-tw6/gdeliveryd`. Reproduzir com
`python tools/patch-tw-local.py --output runtime/patches-tw6` com o arquivo de
destino fora de uso. Os originais conferidos por SHA-256 ficam em
`backups/tw-binaries-original`; as versões anteriores ficam em `runtime/patches`
e `runtime/patches-tw5` (esta com o defeito descrito abaixo).
O manifesto do novo diretório registra o hash e os pontos alterados.

O patch preserva a seleção nativa de disputas e a persistência/notificação
executadas por EndChallenge. Altera a gravação de `battle_time` em ArrangeBattle,
remove a correção para a próxima semana, passa tempo real para UpdateBattle e
OnBattleStart/OnBattleEnd e permite início quando `agora == battle_time`.

`python tools/test-tw-five-minutes.py [runtime/patches-tw6]` executa as instruções x86 em Unicorn para
verificar +300 segundos, preservação da pilha/flags, ausência de correção semanal,
relógio real, os limites de 299/300/301 segundos, a duração da TW de teste e que o
gancho do TestBattle não altera o estado global da TW.

### Correção de 27/09/2026: TW parava de funcionar depois do TW Teste

O gancho do `TestBattle` em `patches-tw5` gravava `(flags & ~1) | 0xa` em
`BattleManager+0x18`, que guarda o estado global da TW (`1` inicializado,
`2` lances abertos, `8` mapa carregado, `0x10` bônus, `0x20` agendamento).
Efeitos, todos até reiniciar o delivery:

- sem o bit `1`, o estado do mapa enviado ao cliente (`SendMap`, `flags & 3`)
  deixava de indicar TW ativa: NPC não deixava entrar e os lances não funcionavam;
- com o bit `2`, o `UpdateBattle` parava e, no minuto seguinte, o `UpdateBid`
  fazia um `endbid` falso: `DBBattleLoad` → `SyncChallenge` (log
  `challenger not equal X != 0`) apagava o atacante e `EndChallenge` encerrava a rodada;
- a TW de teste durava 24 h no gs, mas o delivery cancela uma cidade em luta 4 h
  depois do início (`OnBattleStart`: agora + 14400); o fim da batalha deixava de contar.

`patches-tw6` não mexe nesses bits e usa 3 horas (`TEST_BATTLE_SECONDS`, abaixo das 4 h).
A reserva do painel dura a batalha + 10 minutos, não mais 24 horas.

Dependência de teste isolada:
`python -m pip install --target runtime/test-deps unicorn`.

## Testar a catapulta

1. Crie um clã no jogo com seu personagem.
2. Crie um segundo personagem e outro clã para o lado adversário.
3. Atualize os dados no painel e escolha território, atacante e defensor.
4. Marque a atribuição do território ao defensor e clique em criar TW de teste.
5. A TW de teste começa 3 minutos depois do clique (`TEST_TW_DELAY` em
   `tools/admin/pw_admin.py`); o território é atribuído na hora. O painel precisa
   continuar rodando; se for reiniciado nesse intervalo, o agendamento é retomado.
   O resultado aparece em `runtime/admin/actions.jsonl` (`tw_result`) e nos logs.
   Aguarde a confirmação da batalha. Entre pelo NPC de Guerra Territorial com um
   personagem de um dos clãs.
6. Teste item de catapulta, vínculo ao puxador, movimento, distância máxima,
   ataque às estruturas, dano e perda do vínculo quando o puxador morre.

A função local usa 3 horas. A atribuição do território modifica seu dono e
permanece se a batalha falhar. O painel salva o estado anterior em
`runtime/admin/territory-*.json` e registra resultados em `actions.jsonl`.
Esses registros não substituem um backup completo do banco.

O painel exige dois clãs existentes e distintos. Nenhum clã, personagem ou
permissão GM é criado automaticamente. O nome/ID do território não é a tag do mapa.
Não há necessidade de jogadores online dos dois lados para enviar o comando,
mas entrada e uso da catapulta dependem das regras efetivas do cliente/servidor.

Se houver timeout após o envio, o painel não informa sucesso nem permite repetir
o pedido para o mesmo território até o fim previsto da batalha. Consulte os logs. Não há botão
para cancelar a guerra nem restauração automática do dono anterior.

## Protocolo e evidência

A integração foi derivada do próprio ELF `gdeliveryd` em execução, com leitura da
tabela de símbolos e das instruções, sem alterar executáveis.

- `GNET::DebugCommand` tem tipo 873 (`0x369`), corpo uint32 sender, int32 tag e
  Octets com comprimento compacto; chega pelo GProviderServer, porta 29300.
- A tag 5 interpreta `territorio-defensor` com `%d-%d` e chama
  `GNET::BattleManager::SetOwner(int,int)` (`0x08344110`).
- A tag 4 interpreta `territorio-atacante` com `%d-%d` e chama
  `GNET::BattleManager::TestBattle(int,int)` (`0x083442d8`).
- TestBattle usa o dono atual como defensor, resolve o mapa pelo nível territorial
  e adiciona 10800 segundos (3 h, via patch) ao horário de término. Por isso o dono é atribuído e
  confirmado no banco antes da solicitação de TW PvP.
- Sucesso exige `BattleStart_Re: retcode=0 battle_id=<territorio>.` nos logs do
  delivery. Apenas enviar bytes ou ver o processo bg ativo não indica sucesso.
- O comando de teste altera também estado em memória; a tabela persistida pode
  ainda parecer livre. O painel mantém uma reserva local enquanto a batalha dura.

O PHP usa somente três ações fixas: probe sem alteração (tag desconhecida 999),
atribuir dono e iniciar teste. Não oferece execução arbitrária de comandos.
O backend Python verifica IDs, existência dos clãs/território, disputa persistida,
imagem gamed esperada e serviços ativos antes de modificar um território.

## Validação em 18/09/2026

Painel iniciado e consultado: 11 serviços ativos, 52 territórios, um personagem e
nenhum clã. O delivery confirmou a probe do protocolo interno. Pedidos com clãs
inexistentes, IDs iguais, serviço inválido, Host externo ou sem CSRF foram
recusados. Nenhum território foi alterado durante essas verificações.

**A criação de uma TW real, a entrada no campo de batalha e a catapulta ainda não
foram validadas. Dependem da criação dos dois clãs e do teste no cliente.**

```powershell
python tools\admin\check_admin.py
```

Os logs do painel ficam em `runtime/admin/stdout.log` e `stderr.log`. Para parar o
painel, confira o PID em `runtime/admin/pid.txt` e encerre esse processo Python.
O painel não inicia automaticamente com o Windows.
