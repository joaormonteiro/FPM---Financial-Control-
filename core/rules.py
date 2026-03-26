# Dicionario de categorias baseado em palavras-chave encontradas na descricao
# Chave: palavra ou termo presente na descricao da transacao
# Valor: categoria correspondente
CATEGORIES = {
    # Transporte
    "úBER": "transporte",
    "99": "transporte",
    "ONIBUS": "transporte",
    "METRO": "transporte",

    # Alimentacao
    "IFOOD": "alimentacao",
    "PADARIA": "alimentacao",
    "MERCADO": "alimentacao",
    "RESTAURANTE": "alimentacao",

    # Assinaturas e servicos
    "SPOTIFY": "assinaturas",
    "NETFLIX": "assinaturas",
    "AMAZON": "assinaturas",

    # Banco / pagamentos
    "INTER": "outros"
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
