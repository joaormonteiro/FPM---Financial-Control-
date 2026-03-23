import json

from ai.llm_client import LLMClientError, call_ollama


def generate_financial_advice(insight_data: dict) -> str:
    system_prompt = (
        "Voce e um consultor financeiro objetivo. "
        "Use exclusivamente os dados JSON fornecidos. "
        "Nao invente valores, nao invente categorias e nao assuma informacoes ausentes. "
        "Gere sugestoes praticas, aponte riscos e sugira cortes realistas. "
        "Resposta em portugues, no maximo 12 paragrafos."
    )

    prompt = (
        "Analise os insights financeiros abaixo e gere conselhos acionaveis.\\n"
        f"INSIGHTS_JSON: {json.dumps(insight_data, ensure_ascii=False)}"
    )

    try:
        text = call_ollama(prompt=prompt, system_prompt=system_prompt)
    except LLMClientError:
        return "Não foi possível gerar conselho financeiro no momento."

    if not text.strip():
        return "Não foi possível gerar conselho financeiro no momento."

    return text.strip()
