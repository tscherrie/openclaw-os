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
hansos_provider
```

The model property defaults to:

```text
gpt-5.4-mini
```

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
stdin, run one direct OpenAI prompt, clear the key chunks immediately, and rerun
the fake provider path:

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

ADB=/usr/bin/adb scripts/hans-openai-byok.sh \
  --serial MP0125031802636 \
  clear

ADB=/usr/bin/adb scripts/smoke-mp01.sh \
  --serial MP0125031802636 \
  --boot-timeout 900 \
  --include-degraded \
  --require-baked-home
```

If the MP01 has no Android default network after a clean userdata wipe, use the
host-side HTTPS CONNECT proxy only for the manual OpenAI test:

```text
python3 scripts/adb-reverse-connect-proxy.py \
  --listen 127.0.0.1 \
  --port 8888 \
  --allow-host api.openai.com \
  --allow-port 443

adb -s MP0125031802636 reverse tcp:8888 tcp:8888
adb -s MP0125031802636 shell settings put global http_proxy 127.0.0.1:8888
```

Clear both the key and proxy immediately after the manual test:

```text
ADB=/usr/bin/adb scripts/hans-openai-byok.sh --serial MP0125031802636 clear
adb -s MP0125031802636 shell settings delete global http_proxy
adb -s MP0125031802636 shell settings put global http_proxy :0
adb -s MP0125031802636 reverse --remove tcp:8888
```

The 2026-05-15 MP01 Alpha 2 hardware test used this proxy path, passed one real
OpenAI prompt, then verified `hansos_openai_key_parts=0`, `http_proxy=:0`, and a
stopped proxy process before rerunning the fake smoke.

Never put the key in command arguments, logs, source files, Canvas resources, or
Android manifests. The helper stores long `sk-proj-...` values as numbered
system-property chunks, and uses Settings.Global chunks when system properties
cannot be written by shell on the current MP01 image.

## Runtime Behavior

The runtime contains an OpenAI Responses API provider behind an explicit
provider switch. The default is:

```text
persist.hansos.provider=fake
```

Set `persist.hansos.provider=openai` to route normal non-local prompts through
OpenAI. Local alpha intents such as focus mode, morning brief, and app-control
fixtures still stay on deterministic fake providers so smoke tests remain
stable.

The manual direct trigger is also kept:

```text
ask openai ...
```

Missing key, missing key chunk, unreadable key file, invalid key, network
failure, and rate-limit cases must emit an `error` plus `repair_suggestion`
event. This keeps Cuttlefish smoke tests deterministic while proving the
provider boundary and BYOK path.

## Voice Direction

Voice-first remains the product direction. The first Cuttlefish alpha uses text
and fake injection. OpenAI Realtime should be added behind the same runtime
provider boundary after the bootable Canvas/Core loop is stable.
