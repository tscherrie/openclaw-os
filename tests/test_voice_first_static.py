from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_canvas_default_is_voice_first_surface() -> None:
    canvas = read("aosp/packages/apps/HansCanvas/src/main/java/ai/hansos/canvas/HansCanvasActivity.java")
    assert "Hans live phrase" in canvas
    assert "Hans voice status" in canvas
    assert "startVoiceSession" in canvas
    assert "appendVoiceAudio" in canvas
    assert "AudioRecord" in canvas
    assert "KEYCODE_ASSIST" in canvas
    assert "new Button" not in canvas
    assert "EditText" not in canvas


def test_voice_contract_is_exposed_through_binder() -> None:
    manager = read("protocol/aidl/ai/hansos/agent/IHansManager.aidl")
    runtime = read("protocol/aidl/ai/hansos/agent/IHansRuntime.aidl")
    for contract in (manager, runtime):
        assert "String startVoiceSession(IHansStreamCallback callback);" in contract
        assert "void appendVoiceAudio(String sessionId, in byte[] pcm16MonoChunk);" in contract
        assert "void finishVoiceSession(String sessionId);" in contract
        assert "void cancelVoiceSession(String sessionId);" in contract


def test_voice_events_and_states_are_declared() -> None:
    events = read("protocol/src/main/java/ai/hansos/agent/HansEventTypes.java")
    states = read("protocol/src/main/java/ai/hansos/agent/HansAgentStates.java")
    for event in (
        "LISTENING_STARTED",
        "LISTENING_FINISHED",
        "TRANSCRIPT_PARTIAL",
        "TRANSCRIPT_FINAL",
        "SPEAKING_STARTED",
        "SPEAKING_FINISHED",
        "MANUAL_MODE_REQUIRED",
    ):
        assert event in events
    assert "LISTENING = 5" in states
    assert "TRANSCRIBING = 6" in states
    assert "STOPPED = 7" in states


def test_runtime_has_real_mp01_system_provider_and_fake_switch() -> None:
    runtime = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/HansRuntimeService.java")
    provider = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/SystemPhoneProvider.java")
    listener = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/HansNotificationListenerService.java")
    manifest = read("runtime/HansRuntimeService/src/main/AndroidManifest.xml")

    assert "persist.hansos.context_provider" in runtime
    assert "shouldUseFakeContextProvider" in runtime
    assert "SystemPhoneProvider" in runtime
    assert "buildMorningBrief" in provider
    assert "CalendarContract.Instances" in provider
    assert "ConnectivityManager" in provider
    assert "TelephonyManager" in provider
    assert "setInterruptionFilter" in provider
    assert "NotificationListenerService" in listener
    assert "BIND_NOTIFICATION_LISTENER_SERVICE" in manifest
    assert "WRITE_SECURE_SETTINGS" in manifest


def test_voice_audio_can_be_transcribed_through_byok_and_routed() -> None:
    runtime = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/HansRuntimeService.java")
    openai = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/OpenAiResponsesProvider.java")

    assert "ByteArrayOutputStream" in runtime
    assert "transcribeVoiceSession" in runtime
    assert "runFlow(session.sessionId, transcript, session.callback)" in runtime
    assert "MAX_VOICE_AUDIO_BYTES" in runtime
    assert "VOICE_PARTIAL_TRANSCRIPT_BYTES" in runtime
    assert "TRANSCRIPT_PARTIAL" in runtime
    assert "https://api.openai.com/v1" in openai
    assert "AUDIO_TRANSCRIPTIONS_ENDPOINT" in openai
    assert "persist.hansos.openai_base_url" in openai
    assert "gpt-4o-mini-transcribe" in openai
    assert "buildPcm16Wav" in openai
    assert "multipart/form-data" in openai


def test_sensitive_intents_require_manual_mode() -> None:
    runtime = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/HansRuntimeService.java")
    assert "requiresManualMode" in runtime
    assert "CONFIRMATION_REQUIRED" in runtime
    assert "MANUAL_MODE_REQUIRED" in runtime
    assert "unlock bootloader" in runtime


def test_release_scripts_verify_v1_voice_and_byok_artifacts() -> None:
    byok = read("scripts/hans-openai-byok.sh")
    verify = read("scripts/verify-mp01-image.sh")
    readme = read("README.md")
    openai = read("docs/OPENAI.md")

    assert "--transcription-model" in byok
    assert "--base-url" in byok
    assert "persist.hansos.openai_transcription_model" in byok
    assert "audio/transcriptions" in verify
    assert "SystemPhoneProvider" in verify
    assert "Hans live phrase" in verify
    assert "WRITE_SECURE_SETTINGS" in verify
    assert "MP01 side-button push-to-talk" in readme
    assert "Audio Transcriptions API" in openai
