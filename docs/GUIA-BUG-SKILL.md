# Guia técnico: restaurar o “bug de skill” em servidores Perfect World

Este documento descreve como reproduzir, em uma build autorizada de Perfect
World, o comportamento antigo conhecido como “bug de skill”: durante a barra
de conjuração de uma skill de ataque que também concede um buff, o jogador
troca para uma arma incompatível. O ataque é interrompido, mas o buff é
aplicado e o Chi não é consumido.

O método é aplicável a várias versões, mas os endereços e bytes nunca devem ser
copiados cegamente entre builds. Cada `gs` precisa ser analisado e validado.

## 1. Comportamento que precisa ser reproduzido

O fluxo relevante fica em `PlayerWrapper::SetPerform`, e não na implementação
individual de uma classe.

Fluxo antigo, observado no servidor 1.3.6:

```text
Pray/conjuração
    -> troca para arma incompatível
    -> ataque fica com success = false
    -> se a skill possui DoBless, executa BlessMe mesmo assim
    -> como success = false, não confirma ataque, custo de Chi ou cooldown
```

Pseudocódigo simplificado da versão antiga:

```cpp
if (skill->DoBless())
    skill->BlessMe();

if (inform != 0 && success != 0)
    CommitCooldownAndAP();
```

Em builds modernas, normalmente existem duas proteções adicionais:

```cpp
if (skill->DoBless() && success != 0)
    skill->BlessMe();

if (inform != 0 && (success != 0 || bless_applied != 0))
    CommitCooldownAndAP();
```

Para restaurar o comportamento antigo, é necessário remover as duas condições
modernas:

1. Permitir `BlessMe` mesmo quando `success` já ficou falso.
2. Não confirmar cooldown/Chi somente porque `BlessMe` foi executado.

Alterar apenas o segundo ponto faz o cliente mostrar `Interrupt`, mas nenhum
buff é recebido. Esse é um teste útil para identificar um patch incompleto.

## 2. Alcance do patch

O ajuste em `SetPerform` é global. Ele vale para todas as classes e todas as
skills marcadas internamente com `DoBless = true`.

Isso normalmente cobre skills de ataque com buff próprio. Não cobre
automaticamente skills cujo efeito foi implementado por outro caminho, como:

- `StateAttack`/`DoEnchant`, normalmente usado para efeitos no alvo;
- filtros adicionados diretamente por uma implementação especial;
- skills novas com lógica incorporada fora de `SetPerform`;
- efeitos implementados por Lua ou por outro módulo da distribuição.

Se uma skill específica não funcionar, compare o construtor e os métodos
`BlessMe`, `StateAttack` e `TakeEffect` dela com os de uma skill confirmada.

## 3. Arquivos e ferramentas

Arquivos comuns:

- servidor: `gs`;
- cliente: `element/elementskill.dll`;
- efeitos visuais: arquivos `.sgc` dentro dos pacotes do cliente;
- opcionalmente uma build antiga como referência.

Ferramentas recomendadas:

- Ghidra para fluxo, referências e decompilação;
- `readelf`, `objdump` ou equivalentes para ELF;
- `nm -C` quando o binário ainda contém símbolos;
- Python com `pyelftools` para mapear endereço virtual para offset;
- Capstone para validar as instruções alteradas;
- SHA-256 para fixar exatamente a build suportada.

Sempre trabalhe em cópias. Preserve o binário original fora do diretório que o
container ou servidor utiliza.

## 4. Identificar a build antes da análise

No Linux:

```bash
sha256sum gs
file gs
readelf -h gs
readelf -l gs
```

No PowerShell:

```powershell
Get-FileHash .\gs -Algorithm SHA256
```

Registre pelo menos:

- SHA-256;
- arquitetura, geralmente ELF x86 de 32 bits;
- versão do servidor;
- origem do binário;
- configuração e `elements.data` usados no teste.

O script de patch deve abortar se o hash não for exatamente o esperado.

## 5. Encontrar `SetPerform` em outra versão

Quando existem símbolos, procure por:

```bash
nm -C gs | grep -E 'PlayerWrapper::SetPerform|Skill::BlessMe|DoBless'
```

Em um binário sem símbolos:

1. Importe o `gs` no Ghidra como x86 little-endian.
2. Execute a análise completa.
3. Localize chamadas para a rotina virtual de `DoBless` e, em seguida, para
   `Skill::BlessMe`.
4. Localize a rotina que confirma AP/Chi, cooldown e resultado da skill.
5. Use as referências dos construtores de skills conhecidas para confirmar o
   fluxo.

Uma build antiga ajuda muito: exporte a decompilação de `SetPerform` nas duas
versões e compare os blocos de controle, não os endereços.

Skills de referência úteis nesta análise:

| ID | Skill | Característica |
|---:|---|---|
| 62 | Nuvens Dissipadas | Ataque com `DoBless`, sem custo de Chi |
| 63 | Skill 59 de fogo do punho | Ataque com `DoBless`, custo de 200 Chi |
| 67 | Skill 59 de lança | Usa outro caminho de efeito em algumas builds |

Nos construtores, confirme também `restrict_weapons`, `apcost`, `dobless` e
`doenchant`. Os IDs ou implementações podem mudar em servidores customizados.

## 6. Reconhecer as duas condições no assembly

O formato exato varia com compilador e otimização. Um padrão comum é:

```asm
call DoBless
test al, al
je   skip_bless

cmp  byte ptr [success], 0
je   skip_bless          ; proteção moderna a remover

call BlessMe
```

Mais adiante:

```asm
cmp  [inform], 0
je   finish
cmp  byte ptr [success], 0
jne  commit
cmp  byte ptr [bless_applied], 0
jne  commit              ; proteção moderna a remover
jmp  finish
```

O objetivo é neutralizar somente os saltos marcados. Em x86 isso normalmente é
feito com `NOP`, preservando o tamanho original da função.

Não procure apenas uma sequência fixa de bytes. Compiladores diferentes podem
usar `je`, `jne`, registradores distintos, blocos invertidos ou instruções
curtas/longas.

## 7. Converter endereço virtual em offset de arquivo

Para um ELF, o endereço exibido pelo disassembler não é necessariamente o
offset dentro do arquivo. Localize o segmento `PT_LOAD` que contém o endereço:

```text
file_offset = p_offset + virtual_address - p_vaddr
```

Exemplo em Python:

```python
from elftools.elf.elffile import ELFFile

def file_offset(elf, address):
    for segment in elf.iter_segments():
        if segment["p_type"] != "PT_LOAD":
            continue
        start = segment["p_vaddr"]
        end = start + segment["p_filesz"]
        if start <= address < end:
            return segment["p_offset"] + address - start
    raise ValueError("endereço fora dos segmentos do arquivo")
```

Antes de escrever, confira se os bytes encontrados no offset são exatamente os
que foram vistos no disassembler.

## 8. Requisitos de um patch seguro

Um patch reproduzível deve:

1. validar o SHA-256 do original;
2. validar os bytes originais em cada endereço;
3. escrever em um arquivo novo;
4. verificar que somente os offsets declarados mudaram;
5. desassemblar os bytes modificados para validar as instruções;
6. salvar o original e um manifesto JSON;
7. recusar qualquer build desconhecida.

Evite editar o binário diretamente com um editor hexadecimal sem essas
validações. Um deslocamento errado pode iniciar normalmente e corromper o
estado apenas quando determinada skill for usada.

Neste repositório, a implementação de referência está em:

- `tools/patch-skill-cancel-bug.py`;
- saída em `runtime/patches-skill-cancel/gs`;
- manifesto em `runtime/patches-skill-cancel/manifest.json`.

Para adaptar a outra build, altere somente depois da análise:

- `EXPECTED_SHA256`;
- endereços virtuais;
- bytes esperados;
- bytes substitutos.

## 9. Endereços desta build 1.5.5

Estes dados servem apenas para o `gs` original com SHA-256:

```text
b745760ae80370a0e47ad6e38796c56f020454c6a51345b395c62fdf62237dae
```

| Endereço virtual | Offset | Original | Patch | Função |
|---|---|---|---|---|
| `0x0857E7EC` | `0x5367EC` | `0F 84 97 00 00 00` | seis `90` | Executar `BlessMe` com ataque interrompido |
| `0x0857FC02` | `0x537C02` | `75 05` | `90 90` | Não confirmar Chi/cooldown só pelo buff |

O hash do `gs` com o bug e a troca visual descrita abaixo é:

```text
0ab826d48edc921a20fc1348ebff98307f8f18b2ed924b862adaeb93fa08ca08
```

Esses offsets não são universais.

## 10. Implantação com Docker

Uma forma segura é montar o binário como somente leitura:

```yaml
services:
  perfectworld-gamed:
    volumes:
      - type: bind
        source: ./runtime/patches-skill-cancel/gs
        target: /home/gs
        read_only: true
        bind:
          create_host_path: false
```

Depois:

```bash
docker compose stop perfectworld-gamed
python tools/patch-skill-cancel-bug.py
docker compose up -d --no-deps --force-recreate perfectworld-gamed
docker compose exec -T perfectworld-gamed sha256sum /home/gs
docker inspect perfectworld-perfectworld-gamed-1 --format '{{.State.Status}} {{.RestartCount}}'
```

Recrie apenas o serviço `gamed`; não é necessário reiniciar banco, autenticação
ou delivery para esse patch.

Confirme nos logs que todos os mundos esperados iniciaram:

```bash
docker compose logs --no-color perfectworld-gamed | grep 'Starting world'
```

## 11. Plano de testes

Teste primeiro em ambiente local, com personagem descartável.

| Cenário | Resultado esperado |
|---|---|
| Usar a skill normalmente | Dano, buff, custo e cooldown normais |
| Trocar para arma incompatível durante a barra | `Interrupt`, sem dano, com buff |
| Skill com custo de Chi cancelada durante a barra | Buff aplicado e Chi preservado |
| Trocar a arma depois da barra | Comportamento normal da build |
| Cancelar por movimento, stun ou morte | Não deve criar efeitos inesperados |
| Repetir em PvE e PvP | Mesmo fluxo lógico, respeitando regras do mapa |

Depois teste pelo menos uma skill `DoBless` de cada classe disponível. Observe:

- HP/MP/Chi antes e depois;
- cooldown da skill;
- buff e duração;
- dano no alvo;
- logs e reinicializações do `gs`;
- comportamento normal sem cancelamento.

Não declare compatibilidade geral apenas porque uma skill funcionou.

## 12. Skills que não usam `DoBless`

Para uma skill que falhou no teste:

1. encontre `Skill<ID>Stub` no `gs`;
2. verifique `dobless` e `doenchant` no construtor;
3. decompile `BlessMe`, `StateAttack` e `TakeEffect`;
4. compare com a versão antiga;
5. descubra se o efeito é próprio, no alvo ou ambos;
6. altere o ponto comum somente se a semântica for realmente equivalente.

Não force globalmente `StateAttack` em ataques interrompidos sem estudar o
efeito. Esse caminho pode aplicar stun, redução de defesa ou debuffs no alvo e
criar um resultado muito diferente do bug antigo.

## 13. Trocar o efeito visual da skill 63

Essa alteração é independente da mecânica de cancelamento.

Nesta build:

- skill 63: `云龙九现.sgc`;
- Nuvens Dissipadas: `风卷残云.sgc`.

As strings têm o mesmo tamanho em GB18030, permitindo substituição sem mover a
estrutura do binário. A referência foi alterada no `gs` e as três ocorrências
da skill 63 em `elementskill.dll` foram substituídas.

Locais específicos desta build:

| Arquivo | Local | Conteúdo original |
|---|---|---|
| `gs` | VA `0x08E854C6`, offset `0xE3D4C6` | `云龙九现.sgc` |
| `elementskill.dll` | offsets `0x392C04`, `0x394DA9`, `0x394E89` | `云龙九现.sgc` |

Esses locais também precisam ser redescobertos em qualquer outro cliente ou
servidor.

Script de referência:

```powershell
python .\tools\patch-fist-fire-animation.py
```

Hashes do cliente desta instalação:

```text
elementskill.dll original:
57a3095fbb55c6725186e6fdb52a0e3f8bd5a3b739a0f3b12e1bd5482077e707

elementskill.dll alterada:
3ca00553eb8ac1a09a1e5c57b64719b7b93e9a20be15db4a091d7792d66069d2
```

O cliente precisa estar fechado para substituir uma DLL carregada. Todos os
jogadores que devam ver o novo efeito precisam receber o arquivo alterado.

Importante: `.sgc` controla o efeito visual da skill. O movimento corporal do
personagem pode ser controlado por outra tabela do cliente. Se a intenção for
trocar o movimento corporal, identifique essa tabela separadamente em vez de
alterar bytes não relacionados em `elementskill.dll`.

Se os nomes tiverem tamanhos diferentes, não sobrescreva a string no lugar. É
necessário adicionar a nova string em espaço apropriado e corrigir ponteiros ou
recompilar os arquivos de skill.

## 14. Rollback

Servidor:

1. pare somente `perfectworld-gamed`;
2. remova ou comente o bind mount de `/home/gs`;
3. recrie o serviço;
4. confira o hash carregado.

Cliente desta instalação:

```powershell
Copy-Item `
  "D:\PW SERVER\perfectworld\backups\skill-animation\elementskill.dll" `
  "D:\Perfect World International 155 v159\element\elementskill.dll" `
  -Force
```

O cliente deve estar fechado durante o rollback.

## 15. Checklist para portar a outra versão

- [ ] Tenho autorização e backup dos binários.
- [ ] Registrei o SHA-256 da build.
- [ ] Confirmei os IDs das skills nessa distribuição.
- [ ] Encontrei `SetPerform`, `DoBless` e `BlessMe` semanticamente.
- [ ] Comparei o fluxo com uma build antiga ou fonte equivalente.
- [ ] Identifiquei as duas proteções modernas.
- [ ] Converti endereço virtual para offset corretamente.
- [ ] Validei bytes originais e instruções do patch.
- [ ] O script recusa hashes desconhecidos.
- [ ] O original e o manifesto foram preservados.
- [ ] Testei uso normal e cancelamento durante a barra.
- [ ] Testei uma skill com custo de Chi.
- [ ] Testei exceções que não usam `DoBless`.
- [ ] Confirmei logs, mapas e contador de reinicializações.

O princípio portátil é a diferença de fluxo em `SetPerform`. Endereços, bytes,
IDs, offsets e strings visuais pertencem a uma build específica e sempre devem
ser redescobertos.
