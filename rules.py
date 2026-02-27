# Dicionario de categorias baseado em palavras-chave encontradas na descricao
# Chave: palavra ou termo presente na descricao da transacao
# Valor: categoria correspondente
CATEGORIES = {
    # Transporte
    "UBER": "Transporte",
    "99": "Transporte",
    "ONIBUS": "Transporte",
    "METRO": "Transporte",

    # Alimentacao
    "IFOOD": "Alimentação",
    "PADARIA": "Alimentação",
    "MERCADO": "Alimentação",
    "RESTAURANTE": "Alimentação",

    # Assinaturas e servicos
    "SPOTIFY": "Lazer",
    "NETFLIX": "Lazer",
    "AMAZON": "Lazer",

    # Banco / pagamentos
    "INTER": "Outros"
}

# Lista de palavras-chave que indicam que o pagamento foi feito pelos pais
# Se alguma dessas palavras aparecer na descricao da transacao, o pagador sera definido como "Pais"
PARENTS_PAY = [
    "UBER",
    "99",
    "PADARIA",
    "MERCADO",
    "RESTAURANTE",
    "IFOOD"
]
