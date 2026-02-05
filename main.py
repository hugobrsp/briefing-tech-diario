
import os, re, json, ssl, smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import requests
import markdown as md

# ---------------- Configurações ----------------
TOP_N = 8
QUICK_N = 10
TIMEZONE = timezone(timedelta(hours=-3))  # BRT

BING_KEY = os.getenv("BING_API_KEY")
AZOAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip('/') + '/'
AZOAI_DEPLOY = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZOAI_KEY = os.getenv("AZURE_OPENAI_KEY")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "").strip()

SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587

# ---------------- Utilidades ----------------
def now_date_str():
    return datetime.now(tz=TIMEZONE).strftime("%Y-%m-%d")

def normalize_title(t):
    return re.sub(r"\W+", " ", t or "").strip().lower()

def host_of(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

def score_item(title, desc):
    text = f"{title} {desc}".lower()
    weights = {
        "openai": 6, "gpt": 5, "nvidia": 6, "microsoft": 5, "azure": 4,
        "google": 5, "alphabet": 4, "aws": 5, "amazon": 3, "apple": 4,
        "meta": 4, "llm": 5, "chips": 5, "gpu": 5, "semiconductor": 4,
        "cloud": 4, "datacenter": 4, "cybersecurity": 5, "ciberseguran": 5,
        "ataque": 4, "breach": 5, "regulation": 4, "regula": 4,
        "funding": 4, "startup": 4, "aquisição": 4, "acquisition": 4
    }
    return sum(w for k, w in weights.items() if k in text)

# ---------------- Bing News ----------------
def bing_news(query, mkt="pt-BR", count=50):
    url = "https://api.bing.microsoft.com/v7.0/news/search"
    params = {
        "q": query,
        "mkt": mkt,
        "freshness": "Day",
        "sortBy": "Date",
        "count": count,
        "originalImg": "true"
    }
    headers = {"Ocp-Apim-Subscription-Key": BING_KEY}
    r = requests.get(url, params=params, headers=headers, timeout=25)
    r.raise_for_status()
    return r.json().get("value", [])

def fetch_merge_rank():
    assert BING_KEY, "Faltou BING_API_KEY"
    q_pt = '(technology OR "inteligência artificial" OR AI OR cloud OR chips OR startups OR cibersegurança)'
    q_en = '(technology OR AI OR cloud OR chips OR startups OR cybersecurity)'
    pt = bing_news(q_pt, "pt-BR", 50)
    en = bing_news(q_en, "en-US", 50)
    items = []
    seen = set()
    for it in pt + en:
        title = it.get("name", "").strip()
        url = it.get("url")
        if not title or not url:
            continue
        norm = normalize_title(title)
        if norm in seen:
            continue
        seen.add(norm)
        desc = it.get("description", "")
        src = (it.get("provider", [{}])[0] or {}).get("name", host_of(url))
        date = it.get("datePublished", "")
        score = score_item(title, desc)
        items.append({
            "title": title,
            "url": url,
            "desc": desc,
            "source": src,
            "published": date,
            "score": score
        })
    # ordenar por score e data (data como fallback por título)
    items.sort(key=lambda x: (x["score"], x["published"] or x["title"]), reverse=True)
    return items

# ---------------- Azure OpenAI ----------------
def summarize_with_azoai(top, quick):
    assert AZOAI_ENDPOINT and AZOAI_DEPLOY and AZOAI_KEY, "Faltou configuração do Azure OpenAI"
    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é um analista sênior que produz um briefing executivo diário em PT-BR. "
                    "Para cada manchete, gere 2–3 linhas com: o que aconteceu, por que importa e impacto para negócios. "
                    "Use tom direto e cite a fonte entre parênteses com domínio. "
                    "Depois traga 'Pílulas rápidas' (1 linha cada). Finalize com 'Sinais a observar' (3 bullets)."
                )
            },
            {
                "role": "user",
                "content": json.dumps({"top": top, "quick": quick}, ensure_ascii=False)
            }
        ],
        "temperature": 0.3,
        "top_p": 0.9
    }
    url = f"{AZOAI_ENDPOINT}openai/deployments/{AZOAI_DEPLOY}/chat/completions?api-version=2024-08-01-preview"
    headers = {"Content-Type": "application/json", "api-key": AZOAI_KEY}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

# ---------------- Render ----------------
def render_markdown(summary_md, items):
    hoje = now_date_str()
    links = ["\n## Links das fontes\n"] + [f"- {it['title']} ({it['source']}) — {it['url']}" for it in items]
    header = f"# Briefing Diário de Tecnologia — {hoje}\n\n"
    return header + summary_md + "\n\n" + "\n".join(links) + "\n"

def markdown_to_text(md_content):
    # Converte para HTML e remove tags básicas, mas aqui enviaremos como texto simples
    # Para manter simples, retornamos o próprio markdown como texto
    return md_content

# ---------------- Email ----------------
def send_email_markdown(md_content):
    assert SMTP_USER and SMTP_PASS and RECIPIENT_EMAIL, "Faltou configurar SMTP_USER, SMTP_PASS e RECIPIENT_EMAIL"
    msg = MIMEText(markdown_to_text(md_content), "plain", "utf-8")
    msg["Subject"] = f"Briefing Tech — {now_date_str()}"
    msg["From"] = SMTP_USER
    msg["To"] = RECIPIENT_EMAIL
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [RECIPIENT_EMAIL], msg.as_string())

# ---------------- Teams ----------------
def post_to_teams(top):
    if not TEAMS_WEBHOOK_URL:
        return
    # Construir Adaptive Card simples com Top 3
    show = top[:3]
    facts = []
    for i, it in enumerate(show, start=1):
        facts.append({
            "type": "TextBlock",
            "text": f"**{i}) {it['title']}**\n{it['source']} — [Ler]({it['url']})",
            "wrap": True
        })
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {"type": "TextBlock", "text": f"Briefing Tech — {now_date_str()}", "weight": "Bolder", "size": "Large"},
            {"type": "TextBlock", "text": "Top 3 Manchetes", "weight": "Bolder", "spacing": "Medium"},
            *facts,
            {"type": "TextBlock", "text": "Resumo completo enviado por e-mail.", "isSubtle": True, "spacing": "Medium"}
        ]
    }
    payload = {
        "type": "message",
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ]
    }
    r = requests.post(TEAMS_WEBHOOK_URL, headers={"Content-Type": "application/json"}, data=json.dumps(payload))
    r.raise_for_status()

# ---------------- Main ----------------
def main():
    items = fetch_merge_rank()
    top = items[:TOP_N]
    quick = items[TOP_N:TOP_N+QUICK_N]

    try:
        summary = summarize_with_azoai(top, quick)
    except Exception as e:
        summary = (
            "## Top 8 Manchetes (sem resumo)\n" +
            "\n".join([f"{i+1}) {it['title']} ({it['source']}) — {it['url']}" for i, it in enumerate(top)]) +
            "\n\n## Pílulas rápidas\n" +
            "\n".join([f"- {it['title']} ({it['source']}) — {it['url']}" for it in quick]) +
            f"\n\n> Falha ao resumir: {e}"
        )
    md_content = render_markdown(summary, top + quick)

    # Salvar arquivo local para artefato
    filename = f"briefing-{now_date_str()}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(md_content)

    # Enviar
    send_email_markdown(md_content)
    post_to_teams(top)

if __name__ == "__main__":
    main()
