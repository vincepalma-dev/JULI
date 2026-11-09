"""
JULI — Utility Functions.
TTS/STT voice interface, Git helpers, Docker helpers.
"""

import os
import sys
import subprocess
from typing import Optional

# ─────────────────────────────────────────────────────────────
# Voice Interface — Text-to-Speech (TTS)
# ─────────────────────────────────────────────────────────────

# Agent voice colors for terminal feedback
VOICE_COLORS = {
    "PlannerResearcher": "\033[94m",  # Blue
    "Coder": "\033[96m",              # Cyan
    "ReviewerSecurity": "\033[91m",   # Red
    "DevOps": "\033[92m",             # Green
    "TestMonitor": "\033[93m",        # Yellow
    "DocsDiagram": "\033[95m",        # Magenta
    "System": "\033[90m",             # Gray
}
RESET_COLOR = "\033[0m"


def speak(text: str, agent_name: str = "System", engine: str = "auto"):
    """
    Text-to-Speech output. Speaks agent messages aloud.
    
    Supports:
    - 'pyttsx3' (offline, cross-platform)
    - 'gtts' (Google TTS, requires internet)
    - 'auto' (tries pyttsx3, falls back to gtts, then system)
    
    Args:
        text: Text to speak
        agent_name: Agent name for voice color feedback
        engine: TTS engine ('pyttsx3', 'gtts', 'system', 'auto')
    """
    color = VOICE_COLORS.get(agent_name, VOICE_COLORS["System"])
    print(f"{color}🔊 [{agent_name}] Speaking...{RESET_COLOR}")

    # Limit text length for TTS
    speak_text = text[:500] if len(text) > 500 else text

    if engine == "auto":
        for eng in ["pyttsx3", "system"]:
            try:
                _speak_with_engine(speak_text, eng, agent_name)
                return
            except Exception:
                continue
        print(f"{color}🔇 TTS unavailable — install pyttsx3: pip install pyttsx3{RESET_COLOR}")
    else:
        try:
            _speak_with_engine(speak_text, engine, agent_name)
        except Exception as e:
            print(f"TTS error ({engine}): {e}")


def _speak_with_engine(text: str, engine: str, agent_name: str):
    """Internal TTS dispatcher."""
    if engine == "pyttsx3":
        import pyttsx3
        tts = pyttsx3.init()
        # Adjust voice properties per agent
        voices = tts.getProperty('voices')
        if voices and len(voices) > 1:
            # Alternate voices for different agents
            agent_idx = hash(agent_name) % len(voices)
            tts.setProperty('voice', voices[agent_idx].id)
        tts.setProperty('rate', 175)
        tts.say(text)
        tts.runAndWait()

    elif engine == "gtts":
        from gtts import gTTS
        import tempfile
        tts = gTTS(text=text, lang='en', slow=False)
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            tts.save(f.name)
            _play_audio(f.name)

    elif engine == "system":
        if sys.platform == "win32":
            # Windows SAPI
            subprocess.run(
                ['powershell', '-Command',
                 f'Add-Type -AssemblyName System.Speech; '
                 f'$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                 f'$s.Speak("{text[:200]}")'],
                capture_output=True
            )
        elif sys.platform == "darwin":
            subprocess.run(['say', text[:200]], capture_output=True)
        else:
            subprocess.run(['espeak', text[:200]], capture_output=True)


def _play_audio(filepath: str):
    """Play an audio file cross-platform."""
    try:
        if sys.platform == "win32":
            os.startfile(filepath)
        elif sys.platform == "darwin":
            subprocess.run(['afplay', filepath])
        else:
            subprocess.run(['mpg321', filepath], capture_output=True)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# Voice Interface — Speech-to-Text (STT)
# ─────────────────────────────────────────────────────────────

def listen(timeout: int = 10, phrase_limit: int = 30) -> Optional[str]:
    """
    Speech-to-Text input. Listens for user voice commands.
    
    Requires: pip install SpeechRecognition pyaudio
    
    Args:
        timeout: Max seconds to wait for speech
        phrase_limit: Max seconds of speech to capture
        
    Returns:
        Recognized text or None if failed
    """
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        
        with sr.Microphone() as source:
            print("🎤 Listening... (speak now)")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)

        print("🔄 Processing speech...")
        text = recognizer.recognize_google(audio)
        print(f"✅ Heard: \"{text}\"")
        return text

    except ImportError:
        print("❌ Install speech_recognition: pip install SpeechRecognition pyaudio")
        return None
    except Exception as e:
        print(f"❌ STT error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Git Helpers
# ─────────────────────────────────────────────────────────────

def git_init(path: str = "."):
    """Initialize a git repository."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)


def git_add_commit(message: str, path: str = "."):
    """Stage all and commit."""
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True)


def git_push(remote: str = "origin", branch: str = "main", path: str = "."):
    """Push to remote."""
    subprocess.run(["git", "push", remote, branch], cwd=path, check=True)


def git_add_remote(name: str, url: str, path: str = "."):
    """Add a git remote."""
    subprocess.run(["git", "remote", "add", name, url], cwd=path, capture_output=True)


def git_setup_and_push(repo_url: str, message: str = "Initial commit", path: str = "."):
    """Full git init → add → commit → push workflow."""
    git_init(path)
    git_add_commit(message, path)
    # Add remote if not exists
    result = subprocess.run(["git", "remote", "get-url", "origin"], cwd=path, capture_output=True)
    if result.returncode != 0:
        git_add_remote("origin", repo_url, path)
    git_push(path=path)


# ─────────────────────────────────────────────────────────────
# Docker Helpers
# ─────────────────────────────────────────────────────────────

def docker_build(tag: str = "juli-app", path: str = "."):
    """Build a Docker image."""
    subprocess.run(["docker", "build", "-t", tag, "."], cwd=path, check=True)


def docker_compose_up(path: str = ".", detach: bool = True):
    """Start docker-compose services."""
    cmd = ["docker-compose", "up"]
    if detach:
        cmd.append("-d")
    subprocess.run(cmd, cwd=path, check=True)


def docker_compose_down(path: str = "."):
    """Stop docker-compose services."""
    subprocess.run(["docker-compose", "down"], cwd=path, check=True)
