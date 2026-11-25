# Troubleshooting

First try: **quit KAIRO** (right-click its panel → Quit KAIRO) and open it again.
Still stuck? The log file usually says why. Right-click the panel → **Open my KAIRO data folder** → `kairo.log`.

## Installing

| Problem | Fix |
|---|---|
| Windows: "Windows protected your PC" | Click **More info** → **Run anyway**. The installer isn't signed with a paid certificate yet. |
| Windows: "KAIRO is currently running" | Quit KAIRO (right-click its panel → Quit), then click OK. |
| Mac: "KAIRO can't be opened because Apple cannot check it" | Right-click KAIRO in Applications → **Open** → **Open**. You only need to do this once. |
| Mac: "KAIRO is damaged" | Open Terminal and run `xattr -cr /Applications/KAIRO.app`, then right-click → Open. |
| Linux: `./install.sh: Permission denied` | Run `bash install.sh` instead. |

## API keys

| Message | What it means |
|---|---|
| "didn't accept this key" | The key is wrong, incomplete or deleted. Copy it again, all of it, with no spaces. If you can't see it any more, make a new one. |
| "out of credit" / "billing" / "quota" | The key works but the account has no credit. Add some on the company's billing page. API credit is separate from ChatGPT Plus or Claude Pro. |
| "too many requests" / "rate limit" | Free tiers have per-minute and per-day limits. Wait a minute, or upgrade on the company's site. |
| "model not found" | That model isn't available to your key. Open KAIRO Settings, press Check key, and pick another model. |
| "couldn't reach" | No internet connection, or the service is down. KAIRO can fall back to a local model if you set one up. |

## Hearing and speaking

| Problem | Fix |
|---|---|
| The KAIRO panel disappeared | It's hidden, not closed. Press **Ctrl+Alt+H**, or open KAIRO again from the Start menu / Windows search (it won't start a second copy, it just shows the panel). |
| KAIRO doesn't react | Check the panel. **MIC OFF** means you're muted (press MUTE or Ctrl+Alt+M). Then check the right microphone is chosen in KAIRO Settings. |
| The mic level meter in setup doesn't move | Windows: Settings → Privacy → Microphone → allow desktop apps. Mac: System Settings → Privacy & Security → Microphone → turn on KAIRO. |
| It reacts to the TV or other people | Use **Wake word** mode in Settings, so KAIRO only answers when it hears "Kairo". |
| It interrupts itself through the speakers | Use headphones, or turn off barge-in in Settings. The STOP button always works. |
| Robotic voice | The natural voices need the internet. Without it, KAIRO falls back to the computer's built-in voice. |
| Linux: no voice at all | Install `ffmpeg` (or `mpg123`) and `espeak-ng`. |
| "I can't reach the speech service" | Speech recognition currently needs the internet. |

## Local models (Ollama)

| Problem | Fix |
|---|---|
| "Ollama isn't running" | Open the Ollama app, or run `ollama serve`. |
| Very slow answers | That's normal without a dedicated graphics card. Try a smaller model (qwen3:4b or llama3.2:3b) or an online service. |
| Download stopped | Press **Retry** in setup. It continues where it stopped. |
