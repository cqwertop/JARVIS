# Choosing KAIRO's AI

KAIRO can think with an **online AI service** (you bring an API key from that company) or a **local model**
that runs on your own computer with Ollama.

## Important things to know about API keys

- **An API key is not the same as a chat subscription.** ChatGPT Plus, Claude Pro or Gemini Advanced don't give
  you API access. API use is billed separately, usually per use, and you add credit on the company's developer site.
- **Most services charge for use.** A typical spoken question costs a fraction of a cent, but costs add up. Set a
  monthly spending limit on the company's site. Some services (Google Gemini, Groq, Mistral, some OpenRouter models)
  have free tiers with daily limits.
- **Keep your key private.** Paste it only into KAIRO's setup guide, never into a chat, email or website you don't
  trust. KAIRO stores it in your computer's secure password storage (Windows Credential Manager, macOS Keychain,
  or GNOME Keyring/KWallet), never in a file, and only sends it to the company it belongs to.
- **Checking a key is free.** The setup guide's **Check key** only asks for the list of models.

## Supported services

| Service | Where to get a key | Notes |
|---|---|---|
| **Anthropic Claude** | [console.anthropic.com](https://console.anthropic.com/settings/keys) | Excellent at conversation and using tools. Add credit under Billing. |
| **OpenAI (ChatGPT models)** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Separate from a ChatGPT Plus subscription. Add credit under Billing. |
| **Google Gemini** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Has a free tier with daily limits. |
| **OpenRouter** | [openrouter.ai/keys](https://openrouter.ai/keys) | One key for models from many companies. Some models are free. |
| **Groq** | [console.groq.com/keys](https://console.groq.com/keys) | Very fast answers from open models, with a free tier. |
| **Mistral AI** | [console.mistral.ai](https://console.mistral.ai/api-keys) | Has a free "experiment" tier. |
| **DeepSeek** | [platform.deepseek.com](https://platform.deepseek.com/api_keys) | Low-cost models. |
| **xAI Grok** | [console.x.ai](https://console.x.ai) | Grok models. |
| **Another service** | That service's documentation | Any OpenAI-compatible API. You need its base URL, which usually ends in `/v1`. Also works with LM Studio or a local llama.cpp server. |

### Getting a key (same idea on every site)

1. In the setup guide, pick the company and press **Open <site>**. Your browser opens the company's official page.
2. Sign in or create an account. If the service is paid, add a payment method or credit and set a spending limit.
3. Create a new key. Call it "KAIRO" and copy it. **Most sites show a key only once.**
4. Go back to KAIRO, paste the key, and press **Check key**.
5. Choose a model. The guide suggests a good, low-cost one. To control your computer (open apps, set reminders and
   so on), the model must support **tools**, and most current chat models do. If one doesn't, KAIRO can still talk
   but can't act.

### Changing service or key later

Open **KAIRO Settings** (Start menu on Windows, or right-click KAIRO's panel → Settings...). Choose a different
service, or paste a new key for the same one. The old key is replaced in your password storage.

## Local models (Ollama)

- Free and private: nothing leaves your computer, and it works offline.
- Needs [Ollama](https://ollama.com/download). The setup guide checks for it and tells you if it's missing.
- Downloads are big (2–5 GB), so the guide always shows the size and asks first.
- **Speed depends on your graphics card.** Without a dedicated one, expect around 10–20 seconds per answer and about
  2 minutes for the very first answer while the model loads.

| Model | Download | Memory needed | Good for |
|---|---|---|---|
| qwen3:4b | 2.5 GB | ~6 GB RAM | Older or smaller computers |
| qwen3:8b | 5.2 GB | ~9 GB RAM | Best local choice with 16 GB RAM |
| llama3.2:3b | 2.0 GB | ~5 GB RAM | Fastest, simplest answers |

## Using your own Claude Pro/Max plan (personal use only)

When you run KAIRO **from source**, you can choose "Use my Claude plan through Claude Code". KAIRO then uses
the Claude Code you installed and signed in to yourself, and it counts toward your plan's usage limits.
Anthropic doesn't allow apps given to other people to run on someone's plan sign-in, so the **packaged
installers only offer API keys and local models**.
