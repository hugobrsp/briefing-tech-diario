
# Briefing Tech Diário — Agente Plug‑and‑Play

Este repositório executa **um briefing diário de notícias de tecnologia** com:
- Coleta em PT-BR e EN (Bing News Search)
- Deduplicação e ranqueamento por relevância
- **Resumo em PT-BR (Azure OpenAI)** com Top 8 + Pílulas rápidas + Sinais a observar
- **Envio por e-mail (Outlook/Office 365)** e **Teams (Incoming Webhook)**
- **Agendamento automático** via GitHub Actions — 08:00 BRT (11:00 UTC) em dias úteis

---

## ✅ Pré‑requisitos
1. **Chave do Bing News Search** (Azure: recurso *Bing Search v7*)
2. **Azure OpenAI** com um deployment (ex.: `gpt-4o-mini`)
3. **Conta de e-mail O365** (SMTP habilitado) para envio
4. (Opcional) **Webhook de Canal no Microsoft Teams**

---

## 🔐 Secrets necessários (GitHub → Settings → Secrets and variables → Actions)
- `BING_API_KEY`
- `AZURE_OPENAI_ENDPOINT` (ex.: `https://<seu-endpoint>.openai.azure.com/`)
- `AZURE_OPENAI_DEPLOYMENT` (ex.: `gpt-4o-mini`)
- `AZURE_OPENAI_KEY`
- `SMTP_USER` (ex.: seu e-mail O365)
- `SMTP_PASS` (senha/app password)
- `RECIPIENT_EMAIL` (e-mail que receberá o briefing)
- `TEAMS_WEBHOOK_URL` (opcional; URL do webhook do canal no Teams)

---

## ▶️ Como usar
1. Crie um repositório **privado** e suba estes arquivos.
2. Cadastre os **Secrets** acima.
3. O fluxo roda automaticamente às **08:00 BRT** (11:00 UTC) de **segunda a sexta**.
   - Você pode **rodar manualmente** em *Actions → Briefing Tech Diário → Run workflow*.

---

## 📦 Saídas
- E-mail com o briefing (Markdown convertido para texto)
- Post no Teams com as 3 principais manchetes + link
- Artefato do workflow com o arquivo `briefing-YYYY-MM-DD.md`

---

## 🔧 Personalizações rápidas
- Palavras-chave de relevância e peso: ver função `score_item()` em `main.py`.
- Tamanho: edite `TOP_N = 8` e `QUICK_N = 10`.
- Horário: ajuste o cron em `.github/workflows/briefing.yml`.

---

## ⚠️ Observações
- Respeite políticas de uso e paywalls das fontes; cite sempre as fontes.
- Custos: Bing (mínimos), Azure OpenAI (modelo *mini* sai barato) e e-mail/Teams sem custo extra.
