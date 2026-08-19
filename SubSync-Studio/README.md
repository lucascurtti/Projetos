# SubSync Studio 0.5.0

Aplicativo desktop para Windows focado em três tarefas:

1. sincronizar legendas `.srt` com vídeo;
2. traduzir legendas em inglês para português de forma local/offline;
3. fazer uma revisão rápida sem processar o filme inteiro com um LLM.

## O que mudou nesta versão

A revisão completa com Qwen foi removida do fluxo principal porque exigia dezenas de chamadas sequenciais e deixava o processo pesado.

Agora a arquitetura é:

- **FFsubsync** para sincronização;
- **Argos Translate** para tradução offline EN → PT;
- regras locais rápidas para detectar problemas objetivos na legenda;
- **Ollama opcional apenas para um trecho selecionado**, nunca para revisar o filme inteiro automaticamente.

## Instalação no Windows

Pré-requisitos já usados pelas versões anteriores:

- Python 3.12;
- FFmpeg no `PATH`.

Execute:

```bat
setup_windows.bat
```

Depois abra normalmente por:

```text
SubSync Studio.vbs
```

Isso abre somente a janela gráfica, sem manter o CMD aberto.

## Tradução offline

Na primeira utilização da aba **Traduzir EN → PT-BR**, clique em **Instalar modelo EN → PT**.

O pacote de tradução é baixado somente uma vez. Depois disso a tradução funciona localmente.

Fluxo:

```text
Legenda EN
   ↓
Sincronização opcional com o vídeo
   ↓
Argos Translate local
   ↓
Ajustes leves de vocabulário PT-BR
   ↓
Legenda .pt-BR.srt
```

Os timestamps são preservados durante a tradução.

> Observação: o modelo do Argos trabalha com português (`pt`) e pode misturar escolhas regionais. O SubSync Studio aplica apenas algumas normalizações conservadoras para PT-BR. Para frases que ainda ficarem estranhas, use a revisão pontual com IA local.

## Revisão rápida

A aba **Revisão rápida** não chama IA automaticamente.

Ela procura localmente por:

- possível trecho em inglês não traduzido;
- caracteres corrompidos;
- palavras repetidas;
- pontuação/espaçamento estranho;
- linhas muito longas;
- velocidade de leitura elevada;
- tags de formatação desequilibradas.

O botão **Aplicar correções seguras** altera apenas espaços e pontuação que podem ser corrigidos sem interpretação semântica.

## Revisão pontual com Ollama

O Ollama é opcional nessa versão.

Se houver um modelo local instalado, selecione uma linha da tabela e clique em **Revisar trecho selecionado**. O aplicativo envia apenas:

- a fala selecionada;
- a fala anterior;
- a fala seguinte;
- o inglês correspondente, quando fornecido.

A sugestão só é aplicada depois da confirmação do usuário.

O aplicativo usa qualquer modelo local detectado e dá preferência a modelos Qwen menores quando disponíveis. Se você já possui `qwen3.5:9b`, ele pode continuar sendo usado — como agora é apenas uma chamada pontual, não há necessidade de baixar outro modelo obrigatoriamente.

## Player integrado

O botão **Testar no vídeo** abre um player dentro do SubSync Studio com:

- Play/Pause;
- barra de tempo;
- voltar/avançar 10 segundos;
- campo `MM:SS` ou `HH:MM:SS`;
- atalhos para início, 25%, 50%, 75% e 90%;
- exibição da legenda externa durante o teste.

## Estrutura

```text
SubSync-Studio/
├── app.py
├── core/
│   ├── argos_engine.py
│   ├── ollama_engine.py
│   ├── subtitles.py
│   └── sync_engine.py
├── tests/
│   └── test_subtitles.py
├── requirements.txt
├── setup_windows.bat
├── run_windows.bat
├── run_windows_debug.bat
└── SubSync Studio.vbs
```

## Filosofia desta versão

A função principal deve continuar rápida e simples. IA pesada fica disponível somente quando realmente acrescenta valor a um trecho específico.
