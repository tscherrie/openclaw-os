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
    assert "KEYCODE_SYM" in canvas
    assert "KEYCODE_PICTSYMBOLS" in canvas
    assert "KEYCODE_REFRESH = 285" in canvas
    assert "reportInputEvent" in canvas
    assert "new Button" not in canvas
    assert "EditText" not in canvas


def test_canvas_stays_display_only_while_runtime_owns_openai_audio() -> None:
    canvas = read("aosp/packages/apps/HansCanvas/src/main/java/ai/hansos/canvas/HansCanvasActivity.java")
    speech_block = canvas[canvas.index("HansEventTypes.SPEECH"):canvas.index("HansEventTypes.SPEAKING_FINISHED")]
    finish_block = canvas[canvas.index("HansEventTypes.SPEAKING_FINISHED"):canvas.index("HansEventTypes.ERROR")]

    assert "TextToSpeech" not in canvas
    assert "tts_enabled" not in canvas
    assert "appendSpeechOutput" not in canvas
    assert "flushSpeechOutput" not in canvas
    assert "mAgentSpeech.append(message)" in speech_block
    assert "updatePhrase(mAgentSpeech.toString()" in speech_block
    assert "mStatus.setText(\"Antwort bereit.\")" in finish_block


def test_voice_contract_is_exposed_through_binder() -> None:
    manager = read("protocol/aidl/ai/hansos/agent/IHansManager.aidl")
    runtime = read("protocol/aidl/ai/hansos/agent/IHansRuntime.aidl")
    for contract in (manager, runtime):
        assert "String startVoiceSession(IHansStreamCallback callback);" in contract
        assert "void appendVoiceAudio(String sessionId, in byte[] pcm16MonoChunk);" in contract
        assert "void finishVoiceSession(String sessionId);" in contract
        assert "void cancelVoiceSession(String sessionId);" in contract
    assert "void reportInputEvent(int keyCode, int action, boolean pttCandidate);" in manager


def test_manager_exposes_ptt_voice_diagnostics_without_audio_payload() -> None:
    manager = read("aosp/frameworks/base/services/core/java/ai/hansos/server/HansManagerService.java")

    assert "last_input_keycode" in manager
    assert "last_input_ptt_candidate" in manager
    assert "audio_bytes" in manager
    assert "transcription_status" in manager
    assert "dumpsys hans input <keyCode> <action> <pttCandidate>" in manager
    assert "byte[] audio" not in manager


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
    app_pilot = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/HansAppPilotAccessibilityService.java")
    app_pilot_xml = read("runtime/HansRuntimeService/res/xml/hans_app_pilot_accessibility.xml")

    assert "persist.hansos.context_provider" in runtime
    assert "shouldUseFakeContextProvider" in runtime
    assert "SystemPhoneProvider" in runtime
    assert "HansAppPilotAccessibilityService.ensureEnabled" in runtime
    assert "buildMorningBrief" in provider
    assert "CalendarContract.Instances" in provider
    assert "ConnectivityManager" in provider
    assert "TelephonyManager" in provider
    assert "setInterruptionFilter" in provider
    assert "NotificationListenerService" in listener
    assert "BIND_NOTIFICATION_LISTENER_SERVICE" in manifest
    assert "BIND_ACCESSIBILITY_SERVICE" in manifest
    assert "WRITE_SECURE_SETTINGS" in manifest
    assert "AccessibilityService" in app_pilot
    assert "openSettingsAndInspectNetwork" in app_pilot
    assert "clickVisibleText" in app_pilot
    assert "enterTextInFocusedField" in app_pilot
    assert "performGlobalAction" in app_pilot
    assert "canRetrieveWindowContent" in app_pilot_xml
    assert "canPerformGestures" in app_pilot_xml


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


def test_agent_answers_can_be_spoken_on_device_without_android_tts_engine() -> None:
    runtime = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/HansRuntimeService.java")
    openai = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/OpenAiResponsesProvider.java")

    assert "MediaPlayer" in runtime
    assert "AudioAttributes.USAGE_ASSISTANT" in runtime
    assert "persist.hansos.audio_output_enabled" in runtime
    assert "hansos_audio_output_enabled" in runtime
    assert "enqueueAudioOutput(message)" in runtime
    assert "enqueueAudioOutput(spoken.toString())" in runtime
    assert "stopAudioOutput();" in runtime
    assert "Playing Hans speech output" in runtime
    assert "audio/speech" in openai
    assert "synthesizeSpeechMp3" in openai
    assert "persist.hansos.openai_speech_model" in openai
    assert "persist.hansos.openai_speech_voice" in openai
    assert "gpt-4o-mini-tts" in openai
    assert "response_format" in openai


def test_voice_turns_prefer_openai_over_accidental_local_actions() -> None:
    runtime = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/HansRuntimeService.java")
    run_flow = runtime[runtime.index("private void runFlow"):runtime.index("private boolean isMorningIntent")]

    assert run_flow.index("explicitOpenAi") < run_flow.index("isMorningIntent")
    assert run_flow.index("isFocusIntent") < run_flow.index("isOpenAiProviderActive")
    assert 'normalized.contains("app")' not in runtime
    assert 'normalized.contains("focus") || normalized.contains("fokus")' not in runtime
    assert 'normalized.contains("focus mode")' in runtime
    assert 'normalized.contains("fokusmodus")' in runtime


def test_sensitive_intents_require_manual_mode() -> None:
    runtime = read("runtime/HansRuntimeService/src/main/java/ai/hansos/runtime/HansRuntimeService.java")
    assert "requiresManualMode" in runtime
    assert "CONFIRMATION_REQUIRED" in runtime
    assert "MANUAL_MODE_REQUIRED" in runtime
    assert "unlock bootloader" in runtime
    assert "APP_PILOT_MAX_STEPS" in runtime
    assert "allowlist=com.android.settings" in runtime


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
    assert "HansAppPilotAccessibilityService" in verify
    assert "last_input_keycode" in verify
    assert "hansos_ptt_keycode" in verify
    assert "Hans live phrase" in verify
    assert "WRITE_SECURE_SETTINGS" in verify
    assert "MP01 side-button push-to-talk" in readme
    assert "Audio Transcriptions API" in openai


def test_mp01_ptt_diagnose_script_exists() -> None:
    script = read("scripts/mp01-ptt-diagnose.sh")
    bridge = read("scripts/hans-input-bridge.sh")
    smoke = read("scripts/smoke-mp01.sh")

    assert "getevent -l -t" in script
    assert "aw9523b-key.kl" in script
    assert "dumpsys hans voice" in script
    assert "ptt-sim" in bridge
    assert "last_input_keycode=63" in smoke
