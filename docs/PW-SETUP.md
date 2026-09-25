# Perfect World local: análise e preparação

## Estado da validação em 18/09/2026

Docker CLI 29.7.2, Compose v5.5.0 e Git 2.55.0 instalados.
Repositório clonado neste workspace: https://github.com/oss-perfectworld/perfectworld
Commit analisado: `d507418bc195a5f6c3db551d3bf48e3977a30a12`, de 26/02/2022.
Todos os quatro arquivos originais foram lidos: README, Compose, Makefile e SQL.
Não há AGENTS.md, Dockerfiles ou fonte do servidor neste checkout.
O README declara 1.5.5 build 2567; isso ainda não foi confirmado pelo binário em execução.

O motor Docker não inicia. O WSL 2.7.14 foi instalado, mas `wsl --status` retorna
`WSL_E_WSL_OPTIONAL_COMPONENT_REQUIRED` e pede reinicialização.
Os recursos Microsoft-Windows-Subsystem-Linux e VirtualMachinePlatform aparecem Enabled.
O Windows ainda não foi reiniciado após a instalação. Reinicialização do Docker Desktop
não resolveu o bloqueio. Não há confirmação de MySQL, auth, delivery, banco de personagens,
glink ou gameserver em funcionamento. Logs dos containers e estado dos mapas dependem do motor.

## Procedência e limites

As imagens são as indicadas pelo projeto, hospedadas em `ossperfectworld` no Docker Hub.
Metadados, manifests, scripts e templates de camadas pequenas foram baixados sem executar código,
via `tools/inspect-images.py`. Evidências estão em `audit/images/`.
O script verifica SHA-256 das camadas lidas; digests fixados estão em `images.lock.json`.
Camadas maiores que 100 KB são omitidas: essa inspeção não equivale a uma auditoria completa
dos binários, bibliotecas ou dados. As imagens PW são Linux 32 bits (386).

Este projeto é um orquestrador público, mas não fornece Dockerfiles nem fonte que permita
reconstruir seus servidores. O checkout também não inclui licença. Portanto, não foi confirmado
como uma distribuição inteiramente open-source ou reproduzível a partir de código.
Pesquisa por alternativas encontrou `PerfectWorldReference/pw-docker`, que apresenta a mesma
base antiga, e `halysondev/docker-perfectworld-compilation`, que exige uma fonte externa do PW.
Nenhuma alternativa pronta, documentada e comprovadamente compatível com 1.5.5/2567 foi validada.
Não foram baixados executáveis de fóruns ou instalados esses projetos alternativos.

Fontes: [projeto](https://github.com/oss-perfectworld/perfectworld),
[imagens oficiais do projeto](https://hub.docker.com/u/ossperfectworld),
[alternativa de compilação](https://github.com/halysondev/docker-perfectworld-compilation),
[comandos WSL](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).

## Arquitetura e portas

Papéis abaixo seguem os nomes e conexões dos templates; protocolo funcional ainda não foi testado.

| Serviço Compose | Função | Portas internas |
| --- | --- | --- |
| perfectworld-db | MySQL de contas, privilégios e cash | 3306/TCP |
| perfectworld-authd | Autenticação e privilégios; conecta ao MySQL | 29200/TCP |
| perfectworld-gamedbd | Persistência de personagens/mundo, separada do MySQL | 29400/TCP |
| perfectworld-gdeliveryd | Coordena sessões e conexões aos demais subsistemas | 29100/TCP, 29300/TCP (providers) |
| perfectworld-gfactiond | Facções e provider | 29500/TCP, 29600/TCP |
| perfectworld-glinkd | Entrada dos clientes e conexão aos gameservers | 29000–29006/TCP; 29301–29307/TCP para delivery/providers |
| perfectworld-gacd | Anti-cheat e controle | 29702/TCP, 29712/TCP |
| perfectworld-uniquenamed | Nomes únicos de personagens/facções | 29401/TCP |
| perfectworld-logservice | Recebe logs centralizados | 11100/UDP, 11101/TCP |
| perfectworld-gamed | Executa `/home/gs` com mundo e instâncias | Não publica porta no host; conecta aos providers |
| perfectworld-website-register | Cadastro web | 80/TCP |

Somente `127.0.0.1:29000` (jogo) e `127.0.0.1:8080` (cadastro) são publicados.
MySQL não tem publicação no host. Use `docker compose exec` para administração.
Portas listadas são declarações de Compose/templates, não uma varredura de sockets em execução.
A rede estática original `172.30.0.0/16` foi mantida por compatibilidade entre serviços.
Confirme ausência de conflito com VPN/rede local após iniciar Docker.

## Configuração local e persistência

`.env` contém IP local, portas, timezone e senha MySQL aleatória. Ele é ignorado pelo Git.
O nome do banco permanece `pw`, conforme SQL e auth. Senha compartilhada entre auth,
cadastro e MySQL substitui `root`. Os serviços ainda usam root, preservando compatibilidade
com o auth legado; isolamento local não resolve os limites desse modelo de acesso.

`configs/<serviço>/` contém entrypoints corrigidos e templates extraídos.
Templates são montados somente para leitura; entrypoints geram `.conf`/XML dentro de `/home`.
Volumes nomeados em `/home` preservam o conteúdo inicial das imagens, configs geradas,
dados e logs localizados nesse diretório. Não são binds de uma pasta vazia sobre os binários.
MySQL persiste em `/var/lib/mysql`. Gamedbd também preserva `/home/dbhomewdb` e `/home/backup`.
O backupdir real do template era `/home/backup`; o Compose original montava `/home/backupwdb`.
Uniquenamed recebe persistência de seu `/home`, evitando perder dados de nomes nesse diretório.
Logs stdout/stderr usam json-file com rotação de 10 MB × 3 por container.
Caminhos de logs fora de `/home` ainda precisam ser inventariados após baixar as imagens completas.
Não altere o nome do projeto/volumes durante a operação: isso pode selecionar um banco vazio.

Backups dos arquivos originais ficam em `backups/<data-hora>/`, antes das alterações.
O Compose gerado usa sintaxe JSON, válida como YAML, para preservar estruturas sem depender de biblioteca extra.
`tools/configure-local.py` é ferramenta de preparação; não execute novamente sobre um ambiente já configurado.

## Correções preparadas

- Credenciais e portas parametrizadas; MySQL interno, cadastro em 8080 local.
- MySQL com healthcheck que verifica a tabela users; serviços aguardam banco inicializado.
- Scripts shell tinham `RUN ln ...`, comando inválido fora de Dockerfile; corrigido.
- Removido chmod recursivo em `/home` do gameserver, incompatível com mounts somente para leitura.
- Gameserver executa `gs` em foreground com os argumentos originais; falha do processo encerra container.
- SQL não apaga mais o banco e permite banco já criado pelo entrypoint MySQL.
- Corrigidos erros SQL encontrados: gmroleid1 em addForbid, coluna enable em setiplimit,
  e birthday1 em updateUserInfo. Execução dessas procedures ainda não foi validada.

MySQL 5.7 foi mantido para compatibilidade com schema/auth antigos. Não é uma atualização
de plataforma nem uma configuração pronta para exposição pública/VPS.

## Contas e GM

O projeto fornece cadastro web em `http://127.0.0.1:8080` após iniciar.
A camada do cadastro foi posteriormente inspecionada: `register.php` usa
`base64_encode(md5($Login.$Pass, true))`, após trim e conversão de login/senha para minúsculas.
O formulário exige login e senha de 4 a 10 caracteres, com letras, números, `_` e `-`.
Use `http://127.0.0.1:8080/register.php`; a imagem não garante um index na raiz.
Foram corrigidos o teste de aspas/e-mail, a consulta de e-mail que usava a coluna name,
o escape do e-mail na inserção e a data vazia (agora NULL, compatível com MySQL estrito).
Arquivo original salvo em backups; versão local em configs/website-register/register.php.
Não foi criado usuário automaticamente; PHP/MySQL ainda não puderam executar a alteração.
O SQL tem adduser com 17 parâmetros, ID calculado como MAX(id)+16 (primeiro 1024),
campos pessoais e passwd/passwd2. A procedure por si só não calcula hash.

addGM(userid, zoneid) insere 52 permissões: rid 0–11, 100–105, 200–214 e 500–518.
addUserPriv(userid, zoneid, rid) insere uma permissão. Ambas usam INSERT sem proteção contra duplicidade.
delGM não existe neste arquivo. delUserPriv implementa revogação por rid/zona/conta.
Os exemplos administrativos estão em COMANDOS.md. Usar ID da conta, não ID do personagem.

## Mapas, instâncias e investigação de TW

Não há referência a bg01/bg02/bg03/territory/battle/instance nos arquivos originais do checkout.
A busca continuou nas imagens e encontrou `/home/start.sh` do gamed:
um único comando `./gs gs01 gs.conf gmserver.conf gsalias.conf` recebe a lista completa
de `isNN`, `bg01`–`bg06`, arenas e mapas rand. Isso confirma que os nomes bg já estão na
inicialização da imagem; não confirma que seus assets/configurações carregam ou que uma TW ocorre.

A versão local conserva esses argumentos em `configs/gamed/start.sh`.
Não há ativação adicional de bg01–bg03 a fazer na lista de inicialização.
gs.conf e gsalias.conf pertencem à camada grande de assets não inspecionada nesta etapa.
É necessário verificar suas seções de bg, IDs, limites, caminhos de mapas, aliases e tipos
de mundo para estabelecer a correspondência exata com Territory War.
Também é necessário verificar agendamento e estado territorial no delivery/gamedbd.
Não foi identificado comando validado para disparar uma batalha TW manualmente.

Após Docker funcionar, inspecione sem alterar dados:

```powershell
docker compose exec perfectworld-gamed sh -c 'cat /home/gs.conf; cat /home/gsalias.conf'
docker compose exec perfectworld-gamed sh -c 'grep -nEi "bg01|bg02|bg03|territory|battle|instance|world" /home/gs.conf /home/gsalias.conf /home/gmserver.conf'
docker compose logs --tail=200 perfectworld-gamed perfectworld-gdeliveryd perfectworld-gamedbd
docker compose top perfectworld-gamed
```

Para mudar quais instâncias o processo recebe, faça backup de configs/gamed/start.sh,
edite a lista e reinicie o serviço gamed. Essa operação afeta o processo completo.
Não execute outro gs01 em paralelo com o mesmo ID/configuração sem análise de conflitos.

## Próxima validação obrigatória

Reinicie Windows e abra Docker Desktop. Execute `.\start-pw.ps1` nesta pasta.
O primeiro up baixa as imagens completas (gamed sozinho tem cerca de 1,5 GB comprimido).
Verifique `docker compose ps -a`, `docker compose logs --tail=200` e `.\status-pw.ps1`.
Investigue exited/restarting/unhealthy antes de considerar o servidor pronto.
Valide cadastro, login com cliente compatível 1.5.5/2567, mapas e TW; nenhum desses testes ocorreu ainda.
Migração para VPS exige revisão própria de portas, credenciais, backups, licença/procedência e versões.
