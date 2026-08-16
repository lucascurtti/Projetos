#!/bin/bash

echo "=== CALCULADORA ==="

continuar="s"

while [ "$continuar" = "s" ]; do
    read -p "Digite o primeiro número inteiro: " numero1
    read -p "Digite o segundo número inteiro: " numero2

    echo
    echo "Escolha uma operação:"
    echo "1 - Soma"
    echo "2 - Subtração"
    echo "3 - Multiplicação"
    echo "4 - Divisão"

    read -p "Digite a opção desejada: " opcao

    case "$opcao" in
        1)
            resultado=$((numero1 + numero2))
            echo "Resultado: $resultado"
            ;;
        2)
            resultado=$((numero1 - numero2))
            echo "Resultado: $resultado"
            ;;
        3)
            resultado=$((numero1 * numero2))
            echo "Resultado: $resultado"
            ;;
        4)
            if [ "$numero2" -ne 0 ]; then
                resultado=$((numero1 / numero2))
                echo "Resultado: $resultado"
            else
                echo "Não é possível dividir por zero."
            fi
            ;;
        *)
            echo "Opção inválida."
            ;;
    esac

    echo
    read -p "Deseja fazer outra operação? (s/n): " continuar
    continuar=$(echo "$continuar" | tr '[:upper:]' '[:lower:]')
    echo
done

echo "Programa encerrado."
