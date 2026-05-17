# 📧 Email Digest Bot → Telegram

Automated system that reads emails from selected senders, summarizes them using Google Gemini AI, and delivers a daily digest to Telegram and email.

## 🏗️ Architecture

```
⏰ GitHub Actions (scheduled automation)
    → 📧 Gmail IMAP (fetch monitored emails)
    → 🤖 Gemini AI (generate summaries)
    → 📱 Telegram + Email (deliver digest)
```

## 🚀 Features

- Monitor emails from selected senders
- AI-powered summarization using Gemini
- Telegram digest delivery
- Email digest delivery
- Automated scheduling with GitHub Actions
- Environment-variable-based configuration
- Customizable prompts and workflows

## 🚀 Quick Setup

### 1. Gmail App Password

1. Open Google Account Security
2. Enable **2-Step Verification**
3. Create a Gmail App Password
4. Store it securely

---

### 2. Local Setup

```bash
# Clone repository
cd email_digest_bot

# Install dependencies
pip install -r requirements.txt

# Create environment file
copy .env.example .env

# Add your credentials to .env
python email_digest.py
```

---

### 3. Required Environment Variables

Add these variables locally or in GitHub Actions Secrets:

| Variable |
|---|
| `GMAIL_EMAIL` |
| `GMAIL_APP_PASSWORD` |
| `GEMINI_API_KEY` |
| `TELEGRAM_TOKEN` |
| `TELEGRAM_CHAT_ID` |
| `DIGEST_RECIPIENT_EMAIL` |

---

## ⚙️ Configuration

Update `config.py` to:

- modify monitored senders
- adjust lookback window
- switch Gemini models
- customize summarization prompts

---

## 🧠 Prompt Customization

The current implementation is configured for financial and market-related email summaries.

However, the summarization behavior is fully customizable through the `SUMMARY_PROMPT` variable inside `config.py`.

You can easily adapt this project for:

- research digests
- AI news summaries
- productivity workflows
- support ticket summaries
- customer feedback analysis
- newsletter aggregation
- internal business reporting
- educational content summaries

Simply modify the prompt instructions in `config.py` to change:

- summary style
- output format
- tone
- domain expertise
- analysis depth
- sentiment behavior

This makes the project flexible enough to work as a general-purpose AI email intelligence pipeline.

---

## 📁 Project Structure

```
email_digest_bot/
├── email_digest.py
├── config.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── .github/
    └── workflows/
```

---

## 🔒 Security Notes

- Never commit `.env` files
- Store secrets in GitHub Actions Secrets
- Rotate API keys periodically
- Keep bot tokens private
- Avoid hardcoding personal email addresses

---

## 🔧 Troubleshooting

| Problem | Solution |
|---|---|
| IMAP login failed | Verify Gmail App Password and IMAP access |
| No emails found | Verify monitored sender configuration |
| Telegram send failed | Verify Telegram bot token and permissions |
| Gemini API error | Verify API key and quota |
