#!/usr/bin/env bash
set -euo pipefail

CVD_HOME="${HANSOS_CVD_HOME:-${HOME}/hansos-work/cvd-home}"
LOG_ROOTS=(
  "${CVD_HOME}"
  "${HOME}/cuttlefish"
  "${HOME}/hansos-work"
)

echo "HansOS Cuttlefish input diagnostics"
echo

echo "Host:"
uname -a
id
echo

echo "Input devices:"
for path in /dev/uinput /dev/input /dev/input/event*; do
  if compgen -G "${path}" >/dev/null; then
    ls -ld ${path}
  fi
done
if command -v getfacl >/dev/null 2>&1; then
  for path in /dev/uinput /dev/input/event*; do
    if compgen -G "${path}" >/dev/null; then
      getfacl -p ${path} 2>/dev/null || true
    fi
  done
fi
echo

echo "Relevant processes:"
ps -eo pid,ppid,stat,comm,args \
  | grep -E 'launch_cvd|cvd(_internal_start)?|crosvm|webrtc|operator_proxy' \
  | grep -v grep || true
echo

echo "Recent input/crosvm log lines:"
for root in "${LOG_ROOTS[@]}"; do
  if [[ ! -d "${root}" ]]; then
    continue
  fi
  find "${root}" -maxdepth 6 -type f \( -name '*.log' -o -name 'logcat' -o -name 'kernel.log' \) 2>/dev/null \
    | while read -r log; do
        if grep -Eiq 'virtio.*touch|multi touch|uinput|event device|input socket|VIRTUAL_DEVICE_BOOT_FAILED|failed configuring' "${log}"; then
          echo "--- ${log}"
          grep -Ein 'virtio.*touch|multi touch|uinput|event device|input socket|VIRTUAL_DEVICE_BOOT_FAILED|failed configuring' "${log}" \
            | tail -40
        fi
      done
done
echo

echo "Suggested next interactive launch probe:"
echo "  HANSOS_START_WEBRTC=true HANSOS_CVD_VIEW_ONLY_WEBRTC=false scripts/launch-cuttlefish.sh"
