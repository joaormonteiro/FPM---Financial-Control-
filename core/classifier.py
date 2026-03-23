from core.rules import CATEGORIES, PARENTS_PAY


def classify(transaction):
    """
    Classifica uma transacao com base na descricao,
    definindo categoria e pagador usando regras simples.
    """
    desc = transaction.description.upper()

    # Respeita valores ja definidos (ex: motor local anterior).
    if not transaction.category:
        for key, cat in CATEGORIES.items():
            if key in desc:
                transaction.category = cat
                break
        else:
            transaction.category = "outros"

    if not transaction.payer:
        for key in PARENTS_PAY:
            if key in desc:
                transaction.payer = "pais"
                return

        transaction.payer = "eu"
