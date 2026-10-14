---
name: vedana-brolls-setup
description: Instala as dependências do Vedana B-Rolls na pasta do plugin e reporta o veredito do doctor.
---

# Configurar o Vedana B-Rolls

Prepare a instalação do plugin nesta máquina e devolva um veredito curto ao usuário. Execute os comandos na ordem abaixo, um de cada vez, e pare no primeiro que falhar, mostrando a saída real.

**Escolha a coluna do sistema antes de começar.** No Windows, use sempre os comandos marcados como Windows — também no Git Bash: lá `python3` costuma ser o atalho da Microsoft Store e o `install.sh` recusa rodar. No macOS/Linux, use os comandos `bash`/`python3`.

1. Confira os pré-requisitos sem instalar nada.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/scripts/install.ps1" -Check
```

macOS/Linux:

```sh
bash "${CLAUDE_PLUGIN_ROOT}/scripts/install.sh" --check
```

Se algum executável estiver ausente (`MISSING:`), peça ao usuário que o instale pelo gerenciador oficial do sistema conforme `${CLAUDE_PLUGIN_ROOT}/docs/GUIDE.md` e repita esta etapa. No Windows, um programa recém-instalado pelo winget só entra no `PATH` de uma sessão nova do Claude Code.

2. Rode o instalador completo do sistema operacional.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/scripts/install.ps1"
```

macOS/Linux:

```sh
bash "${CLAUDE_PLUGIN_ROOT}/scripts/install.sh"
```

Ele cria `.venv/` e `.tools/` dentro da pasta do plugin, obtém yt-dlp/EJS e o Playwright CLI e não altera instalações globais.

3. Diagnostique o resultado.

Windows:

```powershell
python "${CLAUDE_PLUGIN_ROOT}/scripts/gb.py" doctor
```

macOS/Linux:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gb.py" doctor
```

4. Leia o objeto `summary` do JSON e responda ao usuário em **uma linha**: quantas capacidades estão em `ok`, o que aparece em `missing` com o comando que resolve cada item e o que é apenas `optional` (por exemplo `PEXELS_API_KEY` ausente). Não invente resultados: cite apenas o que o `doctor` devolveu.

Lembre o usuário de repetir `/vedana-brolls-setup` após cada `/plugin update`, porque as dependências vivem na pasta versionada do plugin. Chaves opcionais de Pexels/Pixabay ficam no ambiente ou em um `.env` fora dessa pasta, apontado na raiz do parser: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gb.py" --env-file CAMINHO <subcomando> …` (no Windows, `python`).
