# Comandos locais

Execute na pasta `D:\PW SERVER\perfectworld`. Docker Desktop deve estar funcionando.

```powershell
# Iniciar todos os serviços
.\start-pw.ps1
# Alternativa direta
docker compose up -d
# Parar preservando os volumes
.\stop-pw.ps1
docker compose down
# Estado, portas, memória, banco e últimos erros
.\status-pw.ps1
# Incluir containers parados
docker compose ps -a
# Logs de todos os serviços
docker compose logs --tail=200
docker compose logs -f
# Logs e processo do gameserver
docker compose logs -f perfectworld-gamed
docker compose top perfectworld-gamed
# Reiniciar somente gameserver
docker compose restart perfectworld-gamed
# MySQL: informe a senha de .env no prompt
docker compose exec perfectworld-db mysql -u root -p pw
# Shell do gameserver
docker compose exec perfectworld-gamed sh
# Validar configuração sem mostrar senha
docker compose config --quiet
```

No Linux/WSL, use `sh start-pw.sh`, `sh stop-pw.sh` e `sh status-pw.sh`.
`docker compose ps -a` mostra as portas publicadas; `docker stats` mostra memória e CPU.
O relatório filtra mensagens de erro, mas não comprova login, disponibilidade de mapas ou funcionamento da TW.

## GM no console MySQL

O `zoneid` dos templates inspecionados de delivery e banco é `1`.

```sql
SELECT ID, name FROM users;
-- Use o ID de uma conta existente; 1024 é apenas exemplo.
SELECT * FROM auth WHERE userid = 1024 AND zoneid = 1;
CALL addGM(1024, 1);
SELECT * FROM auth WHERE userid = 1024 AND zoneid = 1;
-- Conceder um único privilégio, somente se ausente:
CALL addUserPriv(1024, 1, 0);
-- Remover todos os privilégios de uma conta nesta zona:
CALL delUserPriv(1024, 1, 0, 1);
```

As procedures usam INSERT simples e falham quando a chave já existe. Não repita `addGM` indiscriminadamente.
Não existe procedure `delGM` no SQL original. `delUserPriv` com `deltype=0` remove um rid,
`1` remove a zona indicada e `2` remove todas as zonas da conta.
Nenhuma conta ou permissão GM foi criada automaticamente.

## Instâncias

O gameserver é um único serviço. A lista de mapas está em `configs/gamed/start.sh`,
copiada dos argumentos reais do script da imagem. Inclui `bg01 bg02 bg03`.
Antes de editar esse arquivo, copie-o para `backups/`.
Após editar a lista, execute `docker compose restart perfectworld-gamed`.
Isso reinicia TODOS os mapas desse processo. Não foi encontrado comando validado
para parar/iniciar uma única instância em execução.

## Persistência e cuidados com comandos

`down` preserva os dados. Não use `down -v`: ele apaga os volumes do ambiente.
Não reaplique o SQL original salvo em backups: ele contém `DROP DATABASE IF EXISTS pw`.
Os backups de arquivos feitos nesta preparação não são backups do banco em execução.
Faça backup consistente dos bancos antes de migrar, atualizar imagens ou alterar dados.
