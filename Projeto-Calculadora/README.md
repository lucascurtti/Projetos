# Projeto Calculadora

Projeto desenvolvido para praticar conceitos básicos de **Python**, **Linux**, **Shell Script** e **GitHub**.

## Arquivos do projeto

- `calculadora.py`: versão da calculadora desenvolvida em Python.
- `calculadora.sh`: versão executável para ambiente Linux usando Shell Script.

## Como executar o arquivo `.sh`

Em um terminal Linux, acesse a pasta onde está o arquivo e dê permissão de execução:

```bash
chmod +x calculadora.sh
```

Para definir as permissões de modo que o proprietário tenha leitura, escrita e execução e os demais tenham apenas leitura:

```bash
chmod 744 calculadora.sh
```

Depois execute:

```bash
./calculadora.sh
```

## Explicação do código em Python

O arquivo `calculadora.py` funciona da seguinte forma:

1. Solicita dois números ao usuário com `input()`.
2. Converte os valores digitados para `float`.
3. Exibe um menu com quatro operações: soma, subtração, multiplicação e divisão.
4. Utiliza `if`, `elif` e `else` para identificar a operação escolhida.
5. Na divisão, verifica se o segundo número é diferente de zero.
6. Usa um laço `while` para permitir que o usuário faça várias operações consecutivas.
7. Mostra o resultado de cada operação utilizando `print()`.

## Como executar o código em Python

No terminal, dentro da pasta do projeto:

```bash
python3 calculadora.py
```
