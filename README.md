# portfolio_analyzer

A Streamlit app that grades how diversified a portfolio is and suggests what-if swaps.

```
pip install -r requirements.txt
streamlit run portfolio_analyzer_simple.py
```

## Reading brokerage files with an open AI model

The CSV upload first uses a built-in reader. If that reader can't match every line, the app asks an open-weight LLM to read the file. This helps with 401(k) and 529 trust funds that have no ticker, money-market cash, broker marks like `NFLX@`, and other unusual layouts. You can also tick **Use AI to read this file** to always use the LLM. Funds with no ticker are analyzed as a similar public fund (for example, a US bond index trust as BND), and the app asks you for their dollar value.

Any OpenAI-compatible endpoint works. Settings come from Streamlit secrets or environment variables:

| Setting | Default | |
|---|---|---|
| `LLM_API_KEY` | none | Required for hosted services. Without it the AI option is hidden. |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | e.g. `http://localhost:11434/v1` for Ollama, `https://openrouter.ai/api/v1`, `https://router.huggingface.co/v1` |
| `LLM_MODEL` | `qwen/qwen3-32b` | Any model the service offers, e.g. `qwen2.5:14b` on Ollama |

**Streamlit Community Cloud:** Cloud apps can't run a model themselves. Get a free key at [console.groq.com](https://console.groq.com) and add it under the app's **Settings → Secrets**:

```toml
LLM_API_KEY = "gsk_..."
```

**On your own computer:** run `ollama pull qwen2.5:14b`, then put these in `.streamlit/secrets.toml` (this file is gitignored):

```toml
LLM_BASE_URL = "http://localhost:11434/v1"
LLM_MODEL = "qwen2.5:14b"
```

When the AI is hosted, the file's contents are sent to that service. With Ollama, nothing leaves your machine.
