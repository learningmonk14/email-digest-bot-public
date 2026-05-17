"""
Email Digest Bot — Configuration
Edit this file to customize which emails to monitor and how summaries are generated.
"""

# ──────────────────────────────────────────────
# 📧 Sender email addresses to monitor
# ──────────────────────────────────────────────
WATCH_SENDERS = [
    "newsletter@example.com",
    "market-updates@example.com",
    "alerts@examplebroker.com",
    "research@examplefinance.com",

    # Add more sender emails below:
    # "another-newsletter@example.com",
]

# ──────────────────────────────────────────────
# ⏰ How far back to look for emails (hours)
# ──────────────────────────────────────────────
LOOKBACK_HOURS = 24

# ──────────────────────────────────────────────
# 🤖 Gemini model for summarization
# ──────────────────────────────────────────────
GEMINI_MODEL = "gemma-4-26b-a4b-it"

# Alternative models:
# "gemma-4-31b-it"
# "gemini-2.0-flash"

# ──────────────────────────────────────────────
# 📝 Summarization prompt
# ──────────────────────────────────────────────
SUMMARY_PROMPT = """You are a Financial Email Digest Assistant and Market Analyst.

TASK:
You will receive a list of emails. For EACH email, generate a structured financial summary with sentiment and market insight.

INSTRUCTIONS:
1. Identify:
   - Sender
   - Subject
   - Received Date

2. Analyze the email and extract:
   - Key information
   - Important numbers (prices, %, indices, macro data)
   - Any action items or decisions

3. Perform Sentiment Analysis:
   - Bullish → Positive market signals, growth, gains
   - Bearish → Negative signals, decline, risk
   - Neutral → Informational or mixed signals

4. Provide Market Insight:
   - 1–2 lines explaining what this email implies for the market or trading

5. Highlight important financial numbers clearly.

OUTPUT FORMAT:

📬 Daily Financial Email Digest
━━━━━━━━━━━━━━━━━━━━━━

📩 From: {sender}
📋 Subject: {subject}
🕐 Received: {date}

📊 Sentiment: {Bullish / Bearish / Neutral}
📈 Market Insight: {short interpretation}

{Write a concise summary with key takeaways and important context.}

━━━━━━━━━━━━━━━━━━━━━━

FINAL SECTION:

📊 Overall Market Summary
• Aggregate Sentiment: {Bullish / Bearish / Neutral / Mixed}
• Key Trends Observed
• Suggested Market Condition

IMPORTANT RULES:
- Do NOT skip emails
- Keep summaries concise and information-dense
- Prioritize financial relevance
- Assign sentiment even if financial data is limited"""
