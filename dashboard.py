import sqlite3
import uuid

import pandas as pd
import streamlit as st

from ai.custom_rule_engine import add_custom_rule, delete_custom_rule, load_custom_rules
from db import init_db, set_transaction_recurring, update_transaction_manual
from models import ALLOWED_CATEGORIES, ALLOWED_PAYERS

st.set_page_config(page_title="Controle Financeiro", layout="wide")

init_db()

conn = sqlite3.connect("data/finance.db")
df = pd.read_sql("SELECT * FROM transactions", conn)
conn.close()

st.title("Controle Financeiro")

if df.empty:
    st.info("Nenhuma transacao encontrada no banco de dados.")
    st.stop()

df["date"] = pd.to_datetime(df["date"], errors="coerce")
df = df.dropna(subset=["date"])

st.sidebar.header("Filtros")

start_date = st.sidebar.date_input("Data inicial", df["date"].min().date())
end_date = st.sidebar.date_input("Data final", df["date"].max().date())

if start_date > end_date:
    st.warning("Data inicial maior que a data final. Ajustando os valores.")
    start_date, end_date = end_date, start_date

df["payer"] = df["payer"].fillna("Desconhecido")
payer_options = df["payer"].unique().tolist()
payer_filter = st.sidebar.multiselect(
    "Quem pagou",
    options=payer_options,
    default=payer_options,
)

filtered_df = df[
    (df["date"] >= pd.to_datetime(start_date))
    & (df["date"] <= pd.to_datetime(end_date))
    & (df["payer"].isin(payer_filter))
]

st.markdown("---")

col1, col2, col3 = st.columns(3)

raw_desc = filtered_df["description"].fillna("")
ai_desc = (
    filtered_df["description_ai"].fillna("")
    if "description_ai" in filtered_df.columns
    else ""
)
is_investment = raw_desc.str.contains(r"\bAplicacao\b|\bCDB\b|\bInvest", case=False, na=False)
if not isinstance(ai_desc, str):
    is_investment = is_investment | ai_desc.str.contains(
        r"\bAplicacao\b|\bCDB\b|\bInvest", case=False, na=False
    )

total_spent = filtered_df[(filtered_df.amount < 0) & (~is_investment)]["amount"].sum()
parents = filtered_df[
    (filtered_df.amount < 0) & (filtered_df.payer == "Pais")
]["amount"].sum()
total_received = filtered_df[filtered_df.amount > 0]["amount"].sum()

col1.metric("Total gasto", f"R$ {abs(total_spent):.2f}".replace(".", ","))
col2.metric("Pago pelos pais", f"R$ {abs(parents):.2f}".replace(".", ","))
col3.metric("Total recebido", f"R$ {total_received:.2f}".replace(".", ","))

st.markdown("---")

st.subheader("Gerenciar Regras")

rules = load_custom_rules()
if rules:
    st.dataframe(pd.DataFrame(rules), use_container_width=True)
else:
    st.info("Nenhuma regra personalizada cadastrada.")

with st.form("custom_rule_create_form"):
    description_contains = st.text_input("Descricao contem")
    amount_min_text = st.text_input("Valor minimo (opcional)")
    amount_max_text = st.text_input("Valor maximo (opcional)")
    recurring_option = st.selectbox("Recorrente", options=["Qualquer", "Sim", "Nao"])
    set_category = st.text_input("Categoria de destino")
    create_rule_submitted = st.form_submit_button("Criar regra")

if create_rule_submitted:
    amount_min = float(amount_min_text) if amount_min_text.strip() else None
    amount_max = float(amount_max_text) if amount_max_text.strip() else None
    is_recurring_value = None
    if recurring_option == "Sim":
        is_recurring_value = True
    elif recurring_option == "Nao":
        is_recurring_value = False

    add_custom_rule(
        {
            "id": f"rule_{uuid.uuid4().hex[:8]}",
            "description_contains": description_contains or None,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "is_recurring": is_recurring_value,
            "set_category": set_category or None,
        }
    )
    st.success("Regra criada com sucesso.")
    st.rerun()

if rules:
    rule_ids = [r.get("id") for r in rules if r.get("id")]
    selected_rule_id = st.selectbox("Regra para excluir", options=rule_ids)
    if st.button("Excluir regra"):
        delete_custom_rule(selected_rule_id)
        st.success("Regra excluida com sucesso.")
        st.rerun()

st.markdown("---")

st.subheader("Gastos por categoria")

if "category_ai" in filtered_df.columns:
    cat_key = filtered_df["category_ai"].fillna(filtered_df["category"])
else:
    cat_key = filtered_df["category"]

cat = (
    filtered_df[filtered_df.amount < 0]
    .groupby(cat_key)["amount"]
    .sum()
    .abs()
)
st.bar_chart(cat, use_container_width=True)

if "id" in filtered_df.columns and not filtered_df.empty:
    st.markdown("---")
    with st.expander("Correcao manual de classificacao"):
        tx_ids = filtered_df["id"].astype(int).tolist()
        selected_id = st.selectbox("Transacao", options=tx_ids)
        selected_row = filtered_df[filtered_df["id"] == selected_id].iloc[0]

        st.caption(str(selected_row.get("raw_description") or selected_row.get("description") or ""))

        current_category = selected_row.get("category")
        default_category = current_category if current_category in ALLOWED_CATEGORIES else "Outros"

        current_payer = selected_row.get("payer")
        payer_choices = ["", *ALLOWED_PAYERS]
        default_payer = current_payer if current_payer in ALLOWED_PAYERS else ""

        with st.form("manual_classification_form"):
            new_category = st.selectbox(
                "Categoria",
                options=ALLOWED_CATEGORIES,
                index=ALLOWED_CATEGORIES.index(default_category),
            )
            new_payer = st.selectbox(
                "Pagador",
                options=payer_choices,
                index=payer_choices.index(default_payer),
            )
            submitted = st.form_submit_button("Salvar")

        if submitted:
            update_transaction_manual(
                tx_id=int(selected_id),
                category=new_category,
                payer=new_payer or None,
            )
            st.success("Classificacao manual aplicada.")
            st.rerun()

        recurrence_group_name = st.text_input(
            "Grupo de recorrencia",
            value=str(selected_row.get("recurrence_group_id") or ""),
        )
        if st.button("Marcar como recorrente"):
            set_transaction_recurring(
                transaction_id=int(selected_id),
                group_name=recurrence_group_name.strip() or f"manual_{selected_id}",
            )
            st.success("Transacao marcada como recorrente.")
            st.rerun()

st.markdown("---")

st.subheader("Transacoes")

table = filtered_df.copy()

tipo_map = {
    "debit": "Debito",
    "credit": "Credito",
    "transfer": "Transferencia",
    "payment": "Pagamento",
}

table["Tipo"] = (
    table["type"]
    .astype(str)
    .str.lower()
    .map(tipo_map)
    .fillna(table["type"].astype(str))
)

table["Quem pagou"] = (
    table["payer"]
    .fillna("Desconhecido")
    .replace({"Joao": "Joao"})
)

if "category_ai" in table.columns:
    table["Categoria"] = table["category_ai"].fillna(table["category"])
else:
    table["Categoria"] = table["category"]

if "description_ai" in table.columns:
    table["Descricao"] = table["description_ai"].fillna(table["description"])
else:
    table["Descricao"] = table["description"]

table["Valor_num"] = table["amount"].astype(float)


def format_brl(v):
    v = float(v)
    s = f"{v:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


table["Valor"] = table["Valor_num"].apply(format_brl)
table["Data"] = table["date"].dt.strftime("%d/%m/%Y")

display_cols = ["Data", "Tipo", "Categoria", "Descricao", "Valor", "Quem pagou"]
table_display = table[display_cols].copy().reset_index(drop=True)

table_for_style = table.copy().reset_index(drop=True)


def valor_style(row):
    if row["Valor_num"] < 0:
        return [
            "background-color: #ffd6d6; color: #900; font-weight: bold; text-align: right;"
        ]
    return [
        "background-color: #d6ffd6; color: #060; font-weight: bold; text-align: right;"
    ]


styler = table_display.style
styler = styler.apply(
    lambda row_idx: valor_style(table_for_style.loc[row_idx.name]),
    axis=1,
    subset=["Valor"],
)

styler = styler.set_table_styles(
    [
        {"selector": "th", "props": [("text-align", "left")]},
        {"selector": "td", "props": [("vertical-align", "middle")]},
    ]
)

st.dataframe(styler, use_container_width=True, height=600)
