import os, json, ssl, smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import requests
import xml.etree.ElementTree as ET

# ---------------- Configurações ----------------
TOP_N = 8
QUICK_N = 10
TIMEZONE = timezone(timedelta(hours=-3))  # BRT

# --- Chaves/segredos ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "").strip()

SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587

# ---------------- Fontes RSS ----------------
RSS_FEEDS = [
    "https://feeds.feedburner.com/TechCrunch/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/technology/",
    "https://www.canaltech.com.br/rss/",
    "https://www.infomoney.com.br/tecnologia/feed/",
    "https://rss.cnn.com/rss/edition_technology.rss",
]

# ---------------- Utilidades ----------------
def now_date_str():
    return datetime.now(tz=TIMEZONE).strftime("%Y-%m-%d")

def text(node):
    return (node.text or '').strip() if node is not None else ''

def fetch_rss(url, timeout=20):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "BriefingBot/1.0"})
    r.raise_for_status()
    return r.text

def parse_rss(xml_text, source_hint=""):
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    # RSS 2.0
    for item in root.findall('.//item'):
        title = text(item.find('title'))
        link = text(item.find('link'))
        desc = text(item.find('description'))
        pub = text(item.find('pubDate'))
        items.append({"title": title, "url": link, "desc": desc, "source": source_hint or "RSS", "published": pub})
    # Atom
    for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
        title = text(entry.find('{http://www.w3.org/2005/Atom}title'))
        link_node = entry.find('{http://www.w3.org/2005/Atom}link')
        link = link_node.get('href') if link_node is not None else ''
        desc = text(entry.find('{http://www.w3.org/2005/Atom}summary')) or text(entry.find('{http://www.w3.org/2005/Atom}content'))
        pub = text(entry.find('{http://www.w3.org/2005/Atom}updated')) or text(entry.find('{http://www.w3.org/2005/Atom}published'))
        items.append({"title": title, "url": link, "desc": desc, "source": source_hint or "Atom", "published": pub})
    return items

# ---------------- Coleta ----------------
def fetch_news():
    items = []
    for url in RSS_FEEDS:
        try:
            xml = fetch_rss(url)
            parsed = parse_rss(xml, source_hint=urlparse(url).netloc)
            items.extend(parsed[:15])
        except Exception:
            continue
    # deduplicar por título normalizado
    seen = set()
    dedup = []
    for it in items:
        norm = (it.get('title') or '').strip().lower()
        if not it.get('title') or not it.get('url') or norm in seen:
            continue
        seen.add(norm)
        dedup.append(it)
    return dedup

# ---------------- GROQ (LLM) ----------------
def summarize_with_groq(top, quick):
    assert GROQ_API_KEY, "Faltou configurar GROQ_API_KEY"
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"}
    payload = {
        "model": "mixtral-8x7b-32768",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é um analista sênior que produz um briefing executivo diário em PT-BR. "
                    "Para cada manchete, gere 2–3 linhas com: o que aconteceu, por que importa e impacto para negócios. "
                    "Use tom direto. Cite a fonte entre parênteses com domínio. Em seguida, traga 'Pílulas rápidas' (1 linha cada)."
                )
            },
            {"role": "user", "content": json.dumps({"top": top, "quick": quick}, ensure_ascii=False)}
        ],
        "temperature": 0.3
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

# ---------------- Render ----------------
def render_markdown(summary_md, items):
    hoje = now_date_str()
    links = ["\n## Links das fontes\n"] + [f"- {it['title']} ({urlparse(it['url']).netloc}) — {it['url']}" for it in items]
    header = f"# Briefing Diário de Tecnologia — {hoje}\n\n"
    return header + summary_md + "\n\n" + "\n".join(links) + "\n"

# ---------------- Email ----------------
def send_email_markdown(md_content):
    assert SMTP_USER and SMTP_PASS and RECIPIENT_EMAIL, "Faltou configurar SMTP_USER, SMTP_PASS e RECIPIENT_EMAIL"
    msg = MIMEText(md_content, "plain", "utf-8")
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
    show = top[:3]
    lines = []
    for i, it in enumerate(show, start=1):
        lines.append(f"**{i}) {it['title']}**\n{urlparse(it['url']).netloc} — {it['url']}")
    payload = {"text": f"Briefing Tech — {now_date_str()}\n\n" + "\n\n".join(lines)}
    requests.post(TEAMS_WEBHOOK_URL, headers={"Content-Type": "application/json"}, data=json.dumps(payload))

# ---------------- Main ----------------
def main():
    items = fetch_news()
    top = items[:TOP_N]
    quick = items[TOP_N:TOP_N+QUICK_N]
    try:
        summary = summarize_with_groq(top, quick)
    except Exception as e:
        summary = (
            "## Top 8 Manchetes (sem resumo)\n" +
            "\n".join([f"{i+1}) {it['title']} ({urlparse(it['url']).netloc}) — {it['url']}" for i, it in enumerate(top)]) +
            "\n\n## Pílulas rápidas\n" +
            "\n".join([f"- {it['title']} ({urlparse(it['url']).netloc}) — {it['url']}" for it in quick]) +
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
