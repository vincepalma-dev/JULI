import subprocess

from juli import voice


def test_windows_tts_never_interpolates_text(monkeypatch):
    calls = []
    monkeypatch.setattr(voice.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    evil = '"); Remove-Item -Recurse C:\\ ; ("'
    voice._speak_with_engine(evil, "system", "Coder")

    ((args, kwargs),) = calls
    assert all(evil not in a for a in args)
    assert args[-1] == voice.WINDOWS_TTS_SCRIPT
    assert "$env:JULI_TTS_TEXT" in voice.WINDOWS_TTS_SCRIPT
    assert kwargs["env"]["JULI_TTS_TEXT"] == evil


def test_stt_notice_mentions_google():
    assert "Google" in voice.STT_NOTICE


def test_mac_and_linux_tts_pass_text_on_stdin(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    evil = "-o /tmp/owned.aiff hello"
    for platform in ("darwin", "linux"):
        monkeypatch.setattr(voice.sys, "platform", platform)
        voice._speak_with_engine(evil, "system", "Coder")
    assert [args for args, _ in calls] == [["say"], ["espeak", "--stdin"]]
    assert all(kw["input"] == evil and kw["text"] is True for _, kw in calls)
