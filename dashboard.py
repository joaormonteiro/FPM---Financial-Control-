import os
import sqlite3
import tempfile
from datetime import datetime

import pandas as pd
import streamlit as st

from ai.custom_rule_engine import create_description_rule, delete_custom_rule, list_rules_for_ui
from ai.description_normalizer import normalize_description
from ai.financial_advisor import generate_financial_advice
from ai.recurrence_engine import detect_recurring_transactions
from core.db import (
    connect,
    init_db,
    insert_transaction,
    set_transaction_recurring,
    update_transaction_manual,
)
from core.settings import DB_PATH
from importers.inter_csv import parse_inter_csv
from core.models import ALLOWED_PAYERS, Transaction
from services.insight_service import generate_monthly_insights

st.set_page_config(page_title="Controle Financeiro", layout="wide")

init_db()

CATEGORY_OPTIONS: list[tuple[str, str]] = [
    ("alimentacao", "Alimentação"),
    ("transporte", "Transporte"),
    ("lazer", "Lazer"),
    ("assinaturas", "Assinaturas"),
    ("saude", "Saúde"),
    ("investimentos", "Investimentos"),
    ("entrada", "Entrada"),
    ("outros", "Outros"),
]


def _category_key_to_label(key: str) -> str:
    value = (key or "").strip().lower()
    for cat_key, label in CATEGORY_OPTIONS:
        if cat_key == value:
            return label
    return "Outros"


def _category_label_to_key(label: str) -> str:
    text = (label or "").strip().lower()
    for cat_key, cat_label in CATEGORY_OPTIONS:
        if cat_label.lower() == text:
            return cat_key
    return "outros"


def _load_df() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    data = pd.read_sql("SELECT * FROM transactions", conn)
    conn.close()
    return data


def _resolve_reference_period() -> tuple[int, int]:
    now = datetime.now()
    current_start = datetime(now.year, now.month, 1).strftime("%Y-%m-%d")
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1)
    else:
        next_month = datetime(now.year, now.month + 1, 1)
    current_end = next_month.strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM transactions
        WHERE date >= ? AND date < ?
        """,
        (current_start, current_end),
    )
    count_current = int(cur.fetchone()[0] or 0)
    if count_current > 0:
        conn.close()
        return now.month, now.year

    cur.execute("SELECT MAX(date) FROM transactions")
    row = cur.fetchone()
    conn.close()
    max_date = str(row[0] or "").strip()
    if len(max_date) >= 7:
        return int(max_date[5:7]), int(max_date[0:4])

    return now.month, now.year


def _import_csv_file(uploaded_file) -> tuple[bool, str]:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded_file.getbuffer())
            temp_path = tmp.name

        original_name = getattr(uploaded_file, "name", None)
        transactions = parse_inter_csv(temp_path, source_name=original_name or temp_path)
        inserted = 0
        for t in transactions:
            if insert_transaction(t):
                inserted += 1

        conn = connect()
        detect_recurring_transactions(conn)
        conn.close()

        os.unlink(temp_path)
        skipped = len(transactions) - inserted
        return True, (
            f"Importação concluída: {inserted} transações adicionadas, "
            f"{skipped} ignoradas (duplicadas)."
        )
    except Exception as exc:
        try:
            if "temp_path" in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception:
            pass
        return False, f"Erro na importação: {exc}"


def _add_manual_transaction(
    tx_date,
    description: str,
    amount: float,
    category: str,
    is_recurring: bool,
) -> tuple[bool, str]:
    try:
        if not description.strip():
            return False, "Descrição é obrigatória."

        ttype = "debit" if float(amount) < 0 else "credit"

        tx = Transaction(
            date=tx_date,
            raw_description=description.strip(),
            description=description.strip(),
            amount=float(amount),
            account="Manual",
            type=ttype,
            category=category,
            payer="eu",
            source_file="manual_entry",
            normalized_description=normalize_description(description.strip()),
            cleaned_description=description.strip(),
            classification_source="manual",
            confidence=1.0,
            is_recurring=1 if is_recurring else 0,
            ai_confidence=1.0,
            description_ai=description.strip(),
            category_ai=category,
            ai_updated_at=datetime.now().isoformat(),
        )

        insert_transaction(tx)

        if is_recurring:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT MAX(id) FROM transactions")
            row = cur.fetchone()
            conn.close()
            if row and row[0] is not None:
                set_transaction_recurring(int(row[0]), f"manual_{row[0]}")

        return True, "Gasto adicionado com sucesso."
    except Exception as exc:
        return False, f"Erro ao adicionar gasto: {exc}"


df = _load_df()

st.title("Controle Financeiro")

main_tab = st.container()

with main_tab:
    st.header("Importar Extrato")
    st.write("Envie seu arquivo CSV do Banco Inter para atualizar automaticamente seu controle.")

    uploaded_file = st.file_uploader("Escolha o extrato CSV", type=["csv"])
    if st.button("Importar Extrato"):
        if uploaded_file is None:
            st.warning("Selecione um arquivo CSV para importar.")
        else:
            ok, msg = _import_csv_file(uploaded_file)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.markdown("---")

    st.header("Lançamento Manual")
    if st.button("➕ Adicionar Gasto"):
        st.session_state["show_manual_form"] = True

    if st.session_state.get("show_manual_form", False):
        with st.form("manual_expense_form"):
            form_date = st.date_input("Data", value=datetime.now().date())
            form_description = st.text_input("Descrição")
            form_amount = st.number_input("Valor", value=0.0, step=0.01, format="%.2f")
            category_labels = [label for _, label in CATEGORY_OPTIONS]
            form_category_label = st.selectbox("Categoria", options=category_labels)
            form_recurring = st.checkbox("Recorrente")
            submit_manual = st.form_submit_button("Salvar Gasto")

        if submit_manual:
            ok, msg = _add_manual_transaction(
                tx_date=form_date,
                description=form_description,
                amount=float(form_amount),
                category=_category_label_to_key(form_category_label),
                is_recurring=form_recurring,
            )
            if ok:
                st.success(msg)
                st.session_state["show_manual_form"] = False
                st.rerun()
            else:
                st.error(msg)

    st.markdown("---")

    if df.empty:
        st.info("Nenhuma transação encontrada no banco de dados.")
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

    st.header("Métricas Principais")

    m1, m2, m3 = st.columns(3)

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
        (filtered_df.amount < 0)
        & (filtered_df.payer.astype(str).str.lower() == "pais")
    ]["amount"].sum()
    total_received = filtered_df[filtered_df.amount > 0]["amount"].sum()

    m1.metric("Total Gasto", f"R$ {abs(total_spent):.2f}".replace(".", ","))
    m2.metric("Pago pelos Pais", f"R$ {abs(parents):.2f}".replace(".", ","))
    m3.metric("Total Recebido", f"R$ {total_received:.2f}".replace(".", ","))

    st.markdown("---")

    st.header("Insights e Conselhos")

    current_month, current_year = _resolve_reference_period()
    st.caption(f"Período em análise: {current_month:02d}/{current_year}")

    insight_col_1, insight_col_2 = st.columns(2)
    with insight_col_1:
        if st.button("Analisar meu mês"):
            st.session_state["monthly_insights_data"] = generate_monthly_insights(
                current_month,
                current_year,
            )

    with insight_col_2:
        if st.button("Onde posso economizar?"):
            insight_data = st.session_state.get("monthly_insights_data")
            if insight_data is None:
                insight_data = generate_monthly_insights(current_month, current_year)
                st.session_state["monthly_insights_data"] = insight_data
            st.session_state["monthly_insights_advice"] = generate_financial_advice(
                insight_data
            )

    current_insights = st.session_state.get("monthly_insights_data")
    if current_insights:
        superfluous = current_insights.get("superfluous", {})
        growth_alerts = current_insights.get("growth_alerts", [])
        small_expenses = current_insights.get("small_expenses", [])

        st.write(f"Gastos supérfluos no mês: R$ {float(superfluous.get('total_superfluous', 0.0)):.2f}")
        st.write(
            f"Percentual sobre despesas do mês: {float(superfluous.get('percentage_of_month', 0.0)):.2f}%"
        )
        st.write("Categorias com crescimento acima de 15%:")
        st.json(growth_alerts)
        st.write("Pequenas despesas acumuladas (< R$ 40):")
        st.json(small_expenses)

    current_advice = st.session_state.get("monthly_insights_advice")
    if current_advice:
        st.write("### Conselho Financeiro")
        st.write(current_advice)

    st.markdown("---")

    st.header("Gráficos")
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

    st.markdown("---")

    st.header("Transações")

    table = filtered_df.copy()

    tipo_map = {
        "debit": "Débito",
        "credit": "Crédito",
        "transfer": "Transferência",
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
        .replace({"eu": "eu", "pais": "pais"})
    )

    if "category_ai" in table.columns:
        table["Categoria"] = table["category_ai"].fillna(table["category"])
    else:
        table["Categoria"] = table["category"]

    if "description_ai" in table.columns:
        main_desc = table["description_ai"].fillna(table["description"]).fillna("")
    else:
        main_desc = table["description"].fillna("")
    raw_desc = table["raw_description"].fillna(table["description"]).fillna("")

    def _description_with_origin(main_text, raw_text):
        main = str(main_text or "").strip()
        raw = str(raw_text or "").strip()
        if not raw or raw == main:
            return main
        return f"{main}\n(orig: {raw})"

    table["Descrição"] = [
        _description_with_origin(main, raw)
        for main, raw in zip(main_desc.tolist(), raw_desc.tolist())
    ]

    table["Valor_num"] = table["amount"].astype(float)

    def format_brl(v):
        v = float(v)
        s = f"{v:,.2f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"

    table["Valor"] = table["Valor_num"].apply(format_brl)
    table["Data"] = table["date"].dt.strftime("%d/%m/%Y")

    display_cols = ["Data", "Tipo", "Categoria", "Descrição", "Valor", "Quem pagou"]
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

    st.dataframe(styler, use_container_width=True, height=500)

    st.markdown("---")

    st.header("Gerenciador de Regras")

    rules = list_rules_for_ui()
    if rules:
        st.dataframe(pd.DataFrame(rules), use_container_width=True)
    else:
        st.info("Nenhuma regra personalizada cadastrada.")

    with st.form("custom_rule_create_form"):
        keywords_text = st.text_input("Keywords (separadas por vírgula)")
        description_final = st.text_input("Descrição final")
        category_labels = [label for _, label in CATEGORY_OPTIONS]
        category_label = st.selectbox("Categoria", options=category_labels)
        priority_text = st.text_input("Prioridade", value="100")
        create_rule_submitted = st.form_submit_button("Criar regra")

    if create_rule_submitted:
        try:
            create_description_rule(
                keywords=keywords_text,
                description_final=description_final,
                category=_category_label_to_key(category_label),
                priority=int(priority_text or "100"),
                source="ui",
            )
            st.success("Regra criada com sucesso.")
            st.rerun()
        except Exception as exc:
            st.error(f"Erro ao criar regra: {exc}")

    if rules:
        rule_ids = [str(r.get("id")) for r in rules if r.get("id")]
        selected_rule_id = st.selectbox("Regra para excluir", options=rule_ids)
        if st.button("Excluir regra"):
            delete_custom_rule(selected_rule_id)
            st.success("Regra excluída com sucesso.")
            st.rerun()

    if "id" in filtered_df.columns and not filtered_df.empty:
        with st.expander("Correção manual de classificação"):
            tx_ids = filtered_df["id"].astype(int).tolist()
            selected_id = st.selectbox("Transação", options=tx_ids)
            selected_row = filtered_df[filtered_df["id"] == selected_id].iloc[0]

            st.caption(str(selected_row.get("raw_description") or selected_row.get("description") or ""))

            current_category = selected_row.get("category")
            default_category = current_category if current_category in {k for k, _ in CATEGORY_OPTIONS} else "outros"

            current_payer = selected_row.get("payer")
            payer_choices = ["", *ALLOWED_PAYERS]
            default_payer = current_payer if current_payer in ALLOWED_PAYERS else ""

            with st.form("manual_classification_form"):
                options = [key for key, _ in CATEGORY_OPTIONS]
                new_category = st.selectbox(
                    "Categoria",
                    options=options,
                    format_func=_category_key_to_label,
                    index=options.index(default_category),
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
                st.success("Classificação manual aplicada.")
                st.rerun()

            recurrence_group_name = st.text_input(
                "Grupo de recorrência",
                value=str(selected_row.get("recurrence_group_id") or ""),
            )
            if st.button("Marcar como recorrente"):
                set_transaction_recurring(
                    transaction_id=int(selected_id),
                    group_name=recurrence_group_name.strip() or f"manual_{selected_id}",
                )
                st.success("Transação marcada como recorrente.")
                st.rerun()
