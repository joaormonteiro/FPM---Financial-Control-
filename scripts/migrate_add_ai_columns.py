import sqlite3  # Biblioteca padrão do Python para interação com bancos SQLite

# Caminho para o banco de dados SQLite.
# OBS: este script deve ser executado a partir da pasta finance_app/scripts
DB = "../data/finance.db"

# Cria a conexão com o banco de dados
conn = sqlite3.connect(DB)

# Cria um cursor para executar comandos SQL
c = conn.cursor()

# Função auxiliar que verifica se uma coluna já existe em uma tabela
def has_column(table, col):
    """
    Verifica se uma coluna existe em uma tabela do SQLite.

    Parâmetros:
    - table (str): nome da tabela
    - col (str): nome da coluna a ser verificada

    Retorno:
    - True se a coluna existir
    - False caso contrário
    """
    # PRAGMA table_info retorna informações sobre as colunas da tabela
    c.execute(f"PRAGMA table_info({table})")

    # Extrai apenas o nome das colunas (posição 1 do retorno)
    cols = [r[1] for r in c.fetchall()]

    # Verifica se o nome da coluna procurada está presente
    return col in cols

# Flag usada para indicar se alguma alteração foi feita no schema
altered = False

# Verifica e adiciona a coluna de descrição gerada por IA
if not has_column("transactions", "description_ai"):
    c.execute("ALTER TABLE transactions ADD COLUMN description_ai TEXT")
    altered = True

# Verifica e adiciona a coluna de categoria gerada por IA
if not has_column("transactions", "category_ai"):
    c.execute("ALTER TABLE transactions ADD COLUMN category_ai TEXT")
    altered = True

# Verifica e adiciona a coluna de confiança da IA
if not has_column("transactions", "ai_confidence"):
    c.execute("ALTER TABLE transactions ADD COLUMN ai_confidence REAL")
    altered = True

# Verifica e adiciona a coluna que armazena a data/hora da última atualização pela IA
if not has_column("transactions", "ai_updated_at"):
    c.execute("ALTER TABLE transactions ADD COLUMN ai_updated_at TEXT")
    altered = True

# Exibe mensagem indicando se a migração foi aplicada ou não
if altered:
    print("Migração aplicada: colunas IA adicionadas.")
else:
    print("Migração não necessária: colunas já existem.")

# Confirma as alterações feitas no banco de dados
conn.commit()

# Fecha a conexão com o banco
conn.close()
