"""Decides whether something the microphone heard was meant for JARVIS.

Pure logic (no audio, no AI) so it can be unit-tested. The voice loop in main.py feeds it transcripts.

Every utterance gets one of these verdicts:
    DIRECT     - clearly a command for JARVIS ("Jarvis, open Chrome", or the first thing said after "Jarvis")
    MAYBE      - might be for JARVIS (a follow-up without the name, or the name mentioned mid-sentence).
                 The AI is told it may stay silent if it's background chatter.
    WAKE_ONLY  - just "Hey Jarvis" - start listening for the command
    IGNORE     - not for JARVIS
    STOP       - "stop" / "cancel" / "that's all" - stop talking and end the conversation
    GOODBYE    - shut JARVIS down
"""

import difflib
import re
import time
from dataclasses import dataclass

DIRECT, MAYBE, WAKE_ONLY, IGNORE, STOP, GOODBYE = "direct", "maybe", "wake_only", "ignore", "stop", "goodbye"

_GREETING = r"(?:hey|hi|hello|ok|okay|yo|oh|um|uh|so|and|a)"
_STOP_PHRASES = re.compile(
    r"^(?:ok(?:ay)?\s+)?(?:stop|stop talking|be quiet|quiet|shut up|cancel|never ?mind|nevermind|that's all|that is all|"
    r"that'?s it|thanks? that'?s all|thank you that'?s all|hold on|wait|enough|silence)(?:\s+(?:please|thanks|thank you))?$"
)
_GOODBYE = re.compile(r"\b(goodbye|good bye|shut yourself down|shut down yourself|go offline|exit|quit)\b")

SILENT_TOKEN = "<silent>"


@dataclass
class Verdict:
    kind: str
    command: str = ""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", text.lower())).strip()


def find_wake_word(text: str, wake_words: list[str]) -> re.Match | None:
    pattern = r"\b(" + "|".join(re.escape(w) for w in wake_words) + r")\b"
    return re.search(pattern, text, flags=re.IGNORECASE)


def is_stop(text: str, wake_words: list[str]) -> bool:
    """'stop', 'Jarvis stop', 'okay that's all thanks' ..."""
    t = _norm(text)
    m = find_wake_word(t, wake_words)
    if m:
        t = (t[: m.start()] + " " + t[m.end():]).strip()
        t = re.sub(rf"^{_GREETING}\s+", "", t).strip()
    return bool(_STOP_PHRASES.match(t))


def is_goodbye(text: str) -> bool:
    return bool(_GOODBYE.search(text.lower())) and len(text.split()) <= 5


def classify(text: str, wake_words: list[str], awaiting_command: bool, in_follow_up: bool, mode: str) -> Verdict:
    """Work out what to do with one transcript.

    awaiting_command: the user just said "Jarvis" on its own, so this is their command.
    in_follow_up:     JARVIS answered recently, so a follow-up without the name is plausible.
    mode:             settings listen_mode (conversation | wake_word | always | push_to_talk).
    """
    text = text.strip()
    if not text:
        return Verdict(IGNORE)
    m = find_wake_word(text, wake_words)
    addressed = m is not None or awaiting_command or mode == "push_to_talk"

    if addressed and is_goodbye(text):
        return Verdict(GOODBYE)
    if (addressed or in_follow_up) and is_stop(text, wake_words):
        return Verdict(STOP)

    if m is None:
        if awaiting_command or mode == "push_to_talk":
            return Verdict(DIRECT, text)
        if mode == "always" or (mode == "conversation" and in_follow_up):
            return Verdict(MAYBE, text)
        return Verdict(IGNORE)

    before = text[: m.start()].strip(" ,.!?")
    after = text[m.end():].strip(" ,.!?")
    if re.fullmatch(rf"(?:{_GREETING}\s*)*", before.lower()):
        # "Hey Jarvis, open Chrome" / "Jarvis" - name at the start: clearly talking to JARVIS.
        return Verdict(DIRECT, after) if after else Verdict(WAKE_ONLY)
    if not after:
        # "Open Chrome, Jarvis" is a real command, but "Amazon Jarvis" / "I built Jarvis" usually isn't.
        # Short single-word fragments are more often mishearings than commands, so let the AI judge.
        return Verdict(MAYBE, before)
    # Name in the middle: "are you just making Jarvis do it" - usually talking *about* JARVIS.
    return Verdict(MAYBE, text)


def looks_like_echo(heard: str, being_spoken: str, threshold: float = 0.5) -> bool:
    """True if what the mic heard is probably JARVIS's own voice coming out of the speakers."""
    h, s = _norm(heard), _norm(being_spoken)
    if not h or not s:
        return False
    if h in s:
        return True
    h_words = h.split()
    s_words = set(s.split())
    overlap = sum(w in s_words for w in h_words) / len(h_words)
    if overlap >= 0.7:
        return True
    return difflib.SequenceMatcher(None, h, s).ratio() >= threshold


_INTERRUPT_WORDS = {"stop", "wait", "cancel", "quiet", "enough", "pause", "silence"}


def detect_interruption(heard: str, being_spoken: str, wake_words: list[str]) -> Verdict | None:
    """While JARVIS is talking the microphone also hears JARVIS. Decide if the user cut in.

    Without echo cancellation the transcript is often JARVIS's words mixed with the user's, so only trust
    signals JARVIS itself isn't saying: its own name, or a stop word that isn't in the sentence being spoken.
    Returns STOP, DIRECT(command) or None (no interruption).
    """
    h, s = _norm(heard), _norm(being_spoken)
    if not h:
        return None
    m = find_wake_word(h, wake_words)
    if m and not find_wake_word(s, wake_words):
        after = h[m.end():].strip()
        if not after or is_stop(after, wake_words) or set(after.split()) <= _INTERRUPT_WORDS:
            return Verdict(STOP)
        return Verdict(DIRECT, after)
    spoken_words = set(s.split())
    if any(w in _INTERRUPT_WORDS and w not in spoken_words for w in h.split()):
        return Verdict(STOP)
    if not looks_like_echo(heard, being_spoken) and is_stop(heard, wake_words):
        return Verdict(STOP)
    return None


def maybe_prompt(text: str) -> str:
    """Wraps a not-clearly-addressed utterance so the AI knows it may stay silent."""
    return (
        f"[Heard without being clearly addressed to you - it may be background conversation or a mishearing. "
        f"If it is not meant for you, or makes no sense as a request, reply with exactly {SILENT_TOKEN} and nothing else.] "
        f"{text}"
    )


def is_silent_reply(reply: str) -> bool:
    return SILENT_TOKEN in reply.lower() or reply.strip().lower() in ("silent", "(silent)")


class ConversationState:
    """Tracks whether JARVIS is in standby or in an active conversation."""

    def __init__(self, follow_up_seconds: float, clock=time.monotonic):
        self.follow_up_seconds = follow_up_seconds
        self._clock = clock
        self._follow_up_until = 0.0
        self._awaiting_until = 0.0

    @property
    def in_follow_up(self) -> bool:
        return self._clock() < self._follow_up_until

    @property
    def awaiting_command(self) -> bool:
        return self._clock() < self._awaiting_until

    @property
    def active(self) -> bool:
        return self.in_follow_up or self.awaiting_command

    def heard_wake_word(self, wait_seconds: float = 8):
        self._awaiting_until = self._clock() + wait_seconds

    def answered(self):
        """JARVIS replied - open the follow-up window."""
        self._awaiting_until = 0.0
        self._follow_up_until = self._clock() + self.follow_up_seconds

    def consumed_command(self):
        self._awaiting_until = 0.0

    def end(self):
        self._awaiting_until = self._follow_up_until = 0.0
