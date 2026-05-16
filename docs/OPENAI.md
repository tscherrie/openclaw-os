# OpenAI Direct BYOK

HansOS uses direct BYOK for the first intelligence path. The key belongs to the
device owner and is never passed through HansCanvas.

## Alpha Configuration

For the first Cuttlefish alpha, the runtime reads:

```text
persist.hansos.openai_key
persist.hansos.openai_key_parts
persist.hansos.openai_key_part1...N
persist.hansos.openai_key_file
persist.hansos.openai_model
persist.hansos.openai_transcription_model
persist.hansos.openai_base_url
persist.hansos.provider
```

On physical MP01 builds where `adb root` is disabled and shell cannot set
`persist.hansos.*`, the runtime also reads the matching Settings.Global
fallbacks:

```text
hansos_openai_key
hansos_openai_key_parts
hansos_openai_key_part1...N
hansos_openai_key_file
hansos_openai_model
hansos_openai_transcription_model
hansos_openai_base_url
hansos_provider
```

The text model property defaults to:

```text
gpt-5.4-mini
```

The voice transcription model property defaults to:

```text
gpt-4o-mini-transcribe
```

The speech output path uses OpenAI Text-to-Speech by default on MP01:

```text
persist.hansos.openai_speech_model
persist.hansos.openai_speech_voice
persist.hansos.openai_speech_speed
persist.hansos.openai_speech_instructions
hansos_openai_speech_model
hansos_openai_speech_voice
hansos_openai_speech_speed
hansos_openai_speech_instructions
```

Defaults are `gpt-4o-mini-tts`, `alloy`, speed `1.03`, and a concise
handheld-agent speaking instruction. New PTT input interrupts any current speech
playback before recording.

Preferred local setup uses the helper script so the key is read from stdin and
does not appear in shell history or process arguments:

```text
printf '%s' "$OPENAI_API_KEY" | scripts/hans-openai-byok.sh --serial 0.0.0.0:6520 configure
scripts/hans-openai-byok.sh --serial 0.0.0.0:6520 test
scripts/hans-openai-byok.sh --serial 0.0.0.0:6520 clear
```

Manual local setup:

```text
adb shell setprop persist.hansos.openai_key sk-...
adb shell setprop persist.hansos.openai_model gpt-5.4-mini
adb shell setprop persist.hansos.openai_transcription_model gpt-4o-mini-transcribe
adb shell setprop persist.hansos.provider openai
adb shell am startservice -n ai.hansos.runtime/.HansRuntimeService
```

Android system properties have a short value limit, so long `sk-proj-...`
keys should use property chunks in Cuttlefish:

```text
adb shell setprop persist.hansos.openai_key_parts 3
adb shell setprop persist.hansos.openai_key_part1 <part-1>
adb shell setprop persist.hansos.openai_key_part2 <part-2>
adb shell setprop persist.hansos.openai_key_part3 <part-3>
adb shell setprop persist.hansos.openai_model gpt-5.4-mini
adb shell setprop persist.hansos.openai_transcription_model gpt-4o-mini-transcribe
adb shell setprop persist.hansos.provider openai
adb shell am startservice -n ai.hansos.runtime/.HansRuntimeService
```

When the test is done, disable OpenAI and clear the part count:

```text
adb shell setprop persist.hansos.provider fake
adb shell setprop persist.hansos.openai_key_parts 0
```

The file indirection remains available for device variants with a matching
SELinux policy:

```text
adb root
adb shell mkdir -p /data/misc/hansos
adb push /local/secret/openai_key /data/misc/hansos/openai_key
adb shell chown system:system /data/misc/hansos /data/misc/hansos/openai_key
adb shell chmod 700 /data/misc/hansos
adb shell chmod 600 /data/misc/hansos/openai_key
adb shell setprop persist.hansos.openai_key_file /data/misc/hansos/openai_key
```

Do not use `/data/misc/hansos` on the current Cuttlefish alpha without adding a
readable policy label; `system_app` cannot read the default `system_data_file`
label.

For maximum quality experiments, set `persist.hansos.openai_model=gpt-5.5`.
For the alpha smoke path, keep OpenAI optional and use fake providers for
pass/fail gating.

Real Cuttlefish BYOK tests need Android framework networking, not just shell
networking. Launch the device with:

```text
scripts/setup-cuttlefish-host-network.sh <host-default-interface>
HANSOS_ENABLE_WIFI=true
```

If `dumpsys connectivity` shows `Active default network: none`, the runtime can
fail with DNS resolution errors even when `adb shell ping api.openai.com`
succeeds.

On DGX, run the host setup before launching, then connect Android to the
virtual access point:

```text
scripts/setup-cuttlefish-host-network.sh enP7s7
adb shell svc wifi enable
adb shell cmd wifi add-suggestion VirtWifi open
adb shell cmd wifi start-scan
```

## MP01 Hardware BYOK Smoke

On the physical MP01, keep OpenAI out of the deterministic pass/fail gate until
the fake flows pass after a clean flash. Then configure the owner key through
stdin and run one direct OpenAI prompt:

```text
cd /home/yearemias/hansos-overlay
printf '%s' "$OPENAI_API_KEY" | \
  ADB=/usr/bin/adb scripts/hans-openai-byok.sh \
    --serial MP0125031802636 \
    configure

ADB=/usr/bin/adb scripts/hans-openai-byok.sh \
  --serial MP0125031802636 \
  --prompt "HansOS MP01 hardware smoke. Answer with one short sentence." \
  test

ADB=/usr/bin/adb scripts/smoke-mp01.sh \
  --serial MP0125031802636 \
  --boot-timeout 900 \
  --include-degraded \
  --include-openai-tts \
  --require-baked-home
```

For Jeremias's current dev MP01, the OpenAI owner key intentionally remains on
device between tests so physical PTT, STT, answer, and TTS can be exercised at
any time. Only clear it when intentionally preparing a sanitized device or
release demo.

If the MP01 has no Android default network after a clean userdata wipe, use the
host-side adb-reverse OpenAI proxy only for the manual OpenAI test:

```text
python3 scripts/hans-openai-proxy.py --host 127.0.0.1 --port 18080
adb -s MP0125031802636 reverse tcp:18080 tcp:18080
printf '%s' "$OPENAI_API_KEY" | \
  ADB=/usr/bin/adb scripts/hans-openai-byok.sh \
    --serial MP0125031802636 \
    --model gpt-4o-mini \
    --base-url http://127.0.0.1:18080/v1 \
    configure
```

For disposable proxy tests, clear both the key and proxy immediately after the
manual test:

```text
ADB=/usr/bin/adb scripts/hans-openai-byok.sh --serial MP0125031802636 clear
adb -s MP0125031802636 reverse --remove tcp:18080
```

The proxy path keeps the API key inside the device/runtime request and avoids
logging authorization headers. It is only a development bridge for offline
userdata-wiped MP01 test boots; production owner devices should use their own
Wi-Fi or cellular default network. The runtime permits cleartext HTTP only so
this loopback bridge can work, and rejects non-loopback HTTP OpenAI base URLs
in code before opening a network connection.

Never put the key in command arguments, logs, source files, Canvas resources, or
Android manifests. The helper stores long `sk-proj-...` values as numbered
system-property chunks, and uses Settings.Global chunks when system properties
cannot be written by shell on the current MP01 image.

## Runtime Behavior

The runtime contains two direct-BYOK OpenAI paths behind the same runtime
boundary:

- Responses API for agent answers.
- Audio Transcriptions API for push-to-talk voice turns.

The default text provider switch is:

```text
persist.hansos.provider=fake
```

Set `persist.hansos.provider=openai` to route normal non-local prompts through
OpenAI. Local alpha intents such as focus mode, morning brief, and app-control
fixtures stay on deterministic fake providers in Cuttlefish, and use real
system providers on MP01 when `persist.hansos.context_provider=real`.

The manual direct trigger is also kept:

```text
ask openai ...
```

Missing key, missing key chunk, unreadable key file, invalid key, network
failure, and rate-limit cases must emit an `error` plus `repair_suggestion`
event. This keeps Cuttlefish smoke tests deterministic while proving the
provider boundary and BYOK path.

## Voice Direction

Voice-first is now a built runtime path. HansCanvas records 16 kHz mono PCM16
while the MP01 side button is held, streams chunks through Binder to
HansRuntimeService, and the runtime can convert that audio to a WAV and send it
to the OpenAI Audio Transcriptions API. The returned transcript is emitted as
`transcript_final` and then routed through the same intent planner as text.
When BYOK is configured, the runtime also attempts best-effort partial
transcriptions every few seconds and emits them as `transcript_partial`, so the
centered Canvas phrase can visibly build while the button is still held.

Agent answers are spoken on-device through OpenAI Text-to-Speech. HansCanvas
stays display-only: it renders the transcript and streamed answer, while
HansRuntimeService sends the final assistant answer to the OpenAI `audio/speech`
endpoint, stores the returned MP3 only as a short-lived app-cache file, plays it
through Android audio, and deletes the file after playback. This keeps one
consistent high-quality voice path across Cuttlefish, MP01, and future devices
instead of depending on whatever Android TTS engine an image happens to ship.
Speech output is enabled by default and can be disabled with
`persist.hansos.audio_output_enabled=0` or `hansos_audio_output_enabled=0`.
The default speech model is `gpt-4o-mini-tts`; the model and voice can be
overridden with `persist.hansos.openai_speech_model` and
`persist.hansos.openai_speech_voice`.

Realtime can still replace the non-streaming transcription hop later, but v1 no
longer depends on Realtime to produce a real transcript.
