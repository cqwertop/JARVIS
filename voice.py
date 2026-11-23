"""Speech in (microphone -> text) and speech out (text -> Windows voice)."""

import asyncio
import ctypes
import queue
import tempfile
import threading
from pathlib import Path

import speech_recognition as sr


def _mci(command: str):
    err = ctypes.windll.winmm.mciSendStringW(command, None, 0, None)
    if err:
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.winmm.mciGetErrorStringW(err, buf, 256)
        raise RuntimeError(f"MCI error {err}: {buf.value}")


def _play_mp3(path: Path):
    """Play an mp3 and wait until it finishes, using Windows' built-in media player API (no extra installs)."""
    try:
        _mci(f'open "{path}" type mpegvideo alias jarvis_audio')
        _mci("play jarvis_audio wait")
    finally:
        try:
            _mci("close jarvis_audio")
        except RuntimeError:
            pass


class Speaker:
    """Speaks text out loud.

    Uses a natural-sounding Microsoft neural voice (the same ones as Edge's "Read aloud", via edge-tts).
    That needs the internet; if it fails, it falls back to the built-in Windows voice (SAPI).

    All speech runs on one background thread, so reminders that fire while
    JARVIS is busy can still talk without clashing with the main loop.
    """

    def __init__(
        self,
        neural_voice: str = "en-GB-RyanNeural",
        neural_rate: str = "+5%",
        fallback_voice: str = "David",
        fallback_rate: int = 1,
    ):
        self._queue: "queue.Queue[tuple[str, threading.Event]]" = queue.Queue()
        self._neural_voice = neural_voice
        self._neural_rate = neural_rate
        self._fallback_voice = fallback_voice
        self._fallback_rate = fallback_rate
        self._audio_file = Path(tempfile.gettempdir()) / "jarvis_speech.mp3"
        self._ready = threading.Event()
        threading.Thread(target=self._worker, daemon=True).start()
        self._ready.wait(timeout=10)

    def _neural_say(self, text: str):
        import edge_tts

        async def synth():
            await edge_tts.Communicate(text, self._neural_voice, rate=self._neural_rate).save(str(self._audio_file))

        asyncio.run(asyncio.wait_for(synth(), timeout=15))
        _play_mp3(self._audio_file)

    def _worker(self):
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        sapi = comtypes.client.CreateObject("SAPI.SpVoice")
        voices = sapi.GetVoices()
        for i in range(voices.Count):
            if self._fallback_voice.lower() in voices.Item(i).GetDescription().lower():
                sapi.Voice = voices.Item(i)
                break
        sapi.Rate = self._fallback_rate
        self._ready.set()

        while True:
            text, done = self._queue.get()
            try:
                try:
                    self._neural_say(text)
                except Exception as exc:
                    print(f"[neural voice unavailable, using Windows voice: {exc!r}]")
                    sapi.Speak(text)
            except Exception as exc:  # never let a speech error kill the thread
                print(f"[voice error] {exc}")
            finally:
                done.set()

    def say(self, text: str, wait: bool = True):
        print(f"JARVIS: {text}")
        done = threading.Event()
        self._queue.put((text, done))
        if wait:
            done.wait()


class Listener:
    """Listens on the microphone and turns speech into text (Google's free recognizer)."""

    def __init__(self, device_index: int | None = None):
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self.microphone = sr.Microphone(device_index=device_index)
        with self.microphone as source:
            print("Calibrating microphone for background noise... stay quiet for a second.")
            self.recognizer.adjust_for_ambient_noise(source, duration=1.5)

    def listen(self, timeout: float | None = None, phrase_limit: float = 15) -> str | None:
        """Returns what was said, or None if nothing was heard / understood."""
        with self.microphone as source:
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            except sr.WaitTimeoutError:
                return None
        try:
            return self.recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as exc:
            print(f"[speech recognition unavailable: {exc}]")
            return None
