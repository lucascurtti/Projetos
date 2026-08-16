# Calculadora simples em Python

continuar = "s"

while continuar == "s":
    numero1 = float(input("Digite o primeiro número: "))
    numero2 = float(input("Digite o segundo número: "))

    print("\nEscolha uma operação:")
    print("1 - Soma")
    print("2 - Subtração")
    print("3 - Multiplicação")
    print("4 - Divisão")

    opcao = input("Digite a opção desejada: ")

    if opcao == "1":
        resultado = numero1 + numero2
        print("Resultado:", resultado)

    elif opcao == "2":
        resultado = numero1 - numero2
        print("Resultado:", resultado)

    elif opcao == "3":
        resultado = numero1 * numero2
        print("Resultado:", resultado)

    elif opcao == "4":
        if numero2 != 0:
            resultado = numero1 / numero2
            print("Resultado:", resultado)
        else:
            print("Não é possível dividir por zero.")

    else:
        print("Opção inválida.")

    continuar = input("\nDeseja fazer outra operação? (s/n): ").lower()

print("Programa encerrado.")
