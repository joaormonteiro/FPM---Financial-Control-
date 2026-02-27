import sqlite3  # Biblioteca padrão para trabalhar com banco de dados SQLite

# Abre conexão com o banco de dados onde estão armazenadas as transações
conn = sqlite3.connect("data/finance.db")
cursor = conn.cursor()  # Cria um cursor para executar comandos SQL

# Executa consulta SQL para buscar as 20 transações mais recentes
# Seleciona apenas as colunas relevantes: date, description, amount, category e payer
cursor.execute("""
SELECT date, description, amount, category, payer
FROM transactions
ORDER BY date DESC  -- ordena do mais recente para o mais antigo
LIMIT 20           -- limita a 20 resultados
""")

# Itera sobre os resultados e imprime cada transação no console
for r in cursor.fetchall():
    print(r)

# Fecha a conexão com o banco
conn.close()
