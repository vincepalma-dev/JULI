"""
Voice: text-to-speech for agent replies and speech-to-text for prompts.

TTS uses pyttsx3 when installed, else the system speech engine. On Windows
the text travels in an environment variable into a constant PowerShell
script, so LLM output can never become PowerShell code. STT uses Google's
online recognizer and says so before it listens.
"""

import os
import subprocess
import sys

WINDOWS_TTS_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.Speak($env:JULI_TTS_TEXT)"
)

STT_NOTICE = (
    "Privacy notice: voice input uses Google's online speech recognition. "
    "Your recorded audio is sent to Google to be transcribed."
)

MAX_SPOKEN_CHARS = 500


def speak(text: str, agent_name: str = "System") -> None:
    """Speak the start of a message. Tries pyttsx3, then the system engine."""
    text = text[:MAX_SPOKEN_CHARS]
    for engine in ("pyttsx3", "system"):
        try:
            _speak_with_engine(text, engine, agent_name)
            return
        except Exception:
            continue
    print("Text-to-speech unavailable. Install pyttsx3: pip install pyttsx3")


def _speak_with_engine(text: str, engine: str, agent_name: str) -> None:
    if engine == "pyttsx3":
        import pyttsx3  # type: ignore[import-not-found, import-untyped]  # optional voice package

        tts = pyttsx3.init()
        voices = tts.getProperty("voices")
        if voices and len(voices) > 1:
            tts.setProperty("voice", voices[hash(agent_name) % len(voices)].id)  # a voice per agent
        tts.setProperty("rate", 175)
        tts.say(text)
        tts.runAndWait()
    elif engine == "system":
        if sys.platform == "win32":
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_TTS_SCRIPT],
                env={**os.environ, "JULI_TTS_TEXT": text[:200]},
                capture_output=True,
            )
        # Text goes in on stdin, so a leading "-" can't become an option
        # (say -o and espeak -w would write files).
        elif sys.platform == "darwin":
            subprocess.run(["say"], input=text[:200], text=True, capture_output=True)
        else:
            subprocess.run(["espeak", "--stdin"], input=text[:200], text=True, capture_output=True)


def listen(timeout: int = 10, phrase_limit: int = 30) -> str | None:
    """Recognize one spoken prompt. Requires SpeechRecognition and pyaudio."""
    try:
        import speech_recognition as sr  # type: ignore[import-not-found, import-untyped]  # optional voice package
    except ImportError:
        print("Install speech recognition: pip install SpeechRecognition pyaudio")
        return None
    print(STT_NOTICE)
    try:
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            print("Listening... (speak now)")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        print("Processing speech...")
        text = recognizer.recognize_google(audio)
        print(f'Heard: "{text}"')
        return text
    except Exception as e:
        print(f"Speech recognition failed: {e}")
        return None
