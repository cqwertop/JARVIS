"""Speech in (microphone -> text) and speech out (text -> voice).

Speaker: natural Microsoft neural voice via edge-tts (needs internet), falling back to the built-in
Windows voice (SAPI). Speech runs on one background thread and can be interrupted with stop().

Listener: keeps the microphone open while JARVIS is listening and fully closes it when muted, so
nothing is recorded while muted. Audio is never saved to disk.
"""

import asyncio
import logging
import queue
import sys
import tempfile
import threading
import time
from pathlib import Path

import speech_recognition as sr

log = logging.getLogger("jarvis.voice")
IS_WINDOWS = sys.platform == "win32"


# --------------------------------------------------------------------------- Windows MCI (mp3 playback)

def _mci(command: str) -> str:
    import ctypes

    buf = ctypes.create_unicode_buffer(256)
    err = ctypes.windll.winmm.mciSendStringW(command, buf, 256, None)
    if err:
        ebuf = ctypes.create_unicode_buffer(256)
        ctypes.windll.winmm.mciGetErrorStringW(err, ebuf, 256)
        raise RuntimeError(f"MCI error {err}: {ebuf.value}")
    return buf.value


class _Stopped(Exception):
    pass


class Speaker:
    """Speaks text out loud. say() queues speech; stop() cuts it off and drops anything queued."""

    def __init__(self, neural_voice="en-GB-RyanNeural", rate="+5%", volume="+0%", fallback_voice="David", fallback_rate=1):
        self._queue: "queue.Queue[tuple[str, threading.Event]]" = queue.Queue()
        self._neural_voice, self._rate, self._volume = neural_voice, rate, volume
        self._fallback_voice, self._fallback_rate = fallback_voice, fallback_rate
        self._audio_file = Path(tempfile.gettempdir()) / "jarvis_speech.mp3"
        self._stop = threading.Event()
        self._busy = threading.Event()
        self.current_text = ""
        self.on_state = lambda speaking: None  # the HUD hooks in here
        self._ready = threading.Event()
        threading.Thread(target=self._worker, daemon=True, name="speaker").start()
        self._ready.wait(timeout=10)

    @classmethod
    def from_settings(cls, voice: dict) -> "Speaker":
        return cls(voice["neural_voice"], voice["rate"], voice["volume"], voice["fallback_voice"], voice["fallback_rate"])

    @property
    def speaking(self) -> bool:
        return self._busy.is_set() or not self._queue.empty()

    # ------------------------------------------------------------------ engines
    def _neural_say(self, text: str):
        import edge_tts

        async def synth():
            comm = edge_tts.Communicate(text, self._neural_voice, rate=self._rate, volume=self._volume)
            await comm.save(str(self._audio_file))

        async def synth_unless_stopped():
            # Downloading the voice audio takes ~1-2 s; check for stop() meanwhile so interrupting is instant.
            task = asyncio.ensure_future(synth())
            deadline = time.monotonic() + 15
            while not task.done():
                if self._stop.is_set() or time.monotonic() > deadline:
                    task.cancel()
                    if self._stop.is_set():
                        raise _Stopped
                    raise TimeoutError("neural voice took too long")
                await asyncio.sleep(0.03)
            task.result()

        asyncio.run(synth_unless_stopped())
        try:
            _mci("close jarvis_audio")
        except RuntimeError:
            pass
        try:
            _mci(f'open "{self._audio_file}" type mpegvideo alias jarvis_audio')
        except RuntimeError:
            time.sleep(0.3)  # MCI occasionally fails to initialise once (error 277) - one retry
            _mci(f'open "{self._audio_file}" type mpegvideo alias jarvis_audio')
        try:
            _mci("play jarvis_audio")
            while _mci("status jarvis_audio mode") == "playing":
                if self._stop.wait(0.05):
                    _mci("stop jarvis_audio")
                    raise _Stopped
        finally:
            try:
                _mci("close jarvis_audio")
            except RuntimeError:
                pass

    def _sapi_say(self, sapi, text: str):
        sapi.Speak(text, 1)  # 1 = async
        while not sapi.WaitUntilDone(50):
            if self._stop.is_set():
                sapi.Speak("", 3)  # async + purge = stop now
                raise _Stopped

    def _worker(self):
        sapi = None
        if IS_WINDOWS:
            try:
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
            except Exception as exc:
                log.warning("Windows voice unavailable: %r", exc)
        self._ready.set()

        while True:
            text, done = self._queue.get()
            self._busy.set()
            self.current_text = text
            self.on_state(True)
            try:
                if self._stop.is_set():
                    raise _Stopped
                try:
                    self._neural_say(text)
                except _Stopped:
                    raise
                except Exception as exc:
                    if sapi is None:
                        raise
                    log.warning("Neural voice unavailable, using Windows voice: %r", exc)
                    self._sapi_say(sapi, text)
            except _Stopped:
                pass
            except Exception as exc:  # never let a speech error kill the thread
                log.error("Voice error: %r", exc)
            finally:
                self.current_text = ""
                self._busy.clear()
                if self._queue.empty():
                    self._stop.clear()
                    self.on_state(False)
                done.set()

    # ------------------------------------------------------------------ public
    def say(self, text: str, wait: bool = True):
        log.info("JARVIS: %s", text)
        done = threading.Event()
        self._queue.put((text, done))
        if wait:
            done.wait()
        return done

    def stop(self):
        """Stop talking now and forget anything queued."""
        if not self.speaking:
            return
        self._stop.set()
        while True:
            try:
                _, done = self._queue.get_nowait()
                done.set()
            except queue.Empty:
                break
        if not self._busy.is_set():
            self._stop.clear()

    def wait(self, timeout: float | None = None):
        end = None if timeout is None else time.monotonic() + timeout
        while self.speaking and (end is None or time.monotonic() < end):
            time.sleep(0.05)


def chime():
    """Short 'I'm listening' beep."""
    if IS_WINDOWS:
        try:
            import winsound

            winsound.Beep(880, 90)
        except Exception:
            pass


# --------------------------------------------------------------------------- microphone

class Listener:
    """Turns speech into text using Google's free recognizer (needs internet)."""

    def __init__(self, device_index: int | None = None):
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self._device_index = device_index
        self._microphone: sr.Microphone | None = None
        self._source = None
        self._last_net_warning = 0.0

    @property
    def is_open(self) -> bool:
        return self._source is not None

    def open(self):
        if self._source is None:
            self._microphone = sr.Microphone(device_index=self._device_index)
            self._source = self._microphone.__enter__()
            log.info("Microphone on. Calibrating for background noise...")
            self.recognizer.adjust_for_ambient_noise(self._source, duration=1.0)

    def close(self):
        """Release the microphone completely (used for mute)."""
        if self._source is not None:
            try:
                self._microphone.__exit__(None, None, None)
            except Exception:
                pass
            self._source = None
            self._microphone = None
            log.info("Microphone off.")

    def listen(self, timeout: float | None = 1, phrase_limit: float = 15) -> str | None:
        """Waits up to `timeout` seconds for speech to start. Returns the words, or None.

        Raises OSError if the microphone itself fails (unplugged etc.) - the caller reopens it.
        """
        self.open()
        try:
            audio = self.recognizer.listen(self._source, timeout=timeout, phrase_time_limit=phrase_limit)
        except sr.WaitTimeoutError:
            return None
        return self.transcribe(audio)

    def transcribe(self, audio) -> str | None:
        try:
            return self.recognizer.recognize_google(audio) or None
        except sr.UnknownValueError:
            return None  # speech-like noise, nothing understood
        except sr.RequestError as exc:
            self._warn_offline(exc)
            return None
        except Exception as exc:  # e.g. a garbled reply from the recognition service (JSONDecodeError)
            log.warning("Speech recognition glitch: %r", exc)
            return None

    def _warn_offline(self, exc):
        now = time.monotonic()
        if now - self._last_net_warning > 300:
            log.warning("Speech recognition unavailable (no internet?): %s", exc)
            self._last_net_warning = now


def list_microphones() -> list[str]:
    return sr.Microphone.list_microphone_names()
