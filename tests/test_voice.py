import subprocess

from agents import utils


def test_windows_tts_never_interpolates_text(monkeypatch):
    calls = []
    monkeypatch.setattr(utils.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    evil = '"); Remove-Item -Recurse C:\\ ; ("'
    utils._speak_with_engine(evil, "system", "Coder")

    ((args, kwargs),) = calls
    assert all(evil not in a for a in args)
    assert args[-1] == utils.WINDOWS_TTS_SCRIPT
    assert "$env:JULI_TTS_TEXT" in utils.WINDOWS_TTS_SCRIPT
    assert kwargs["env"]["JULI_TTS_TEXT"] == evil


def test_stt_notice_mentions_google():
    assert "Google" in utils.STT_NOTICE
