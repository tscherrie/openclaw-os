#!/usr/bin/env bash
set -eo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This helper is for Linux Cuttlefish hosts. Use build-cuttlefish-host-darwin.sh on macOS." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/build-aosp-full.sh" \
  aarch64_linux_gnu_crosvm \
  aarch64_linux_gnu_gfxstream_graphics_detector_for_crosvm \
  aarch64_linux_gnu_libdrm.so.2_for_crosvm \
  aarch64_linux_gnu_libepoxy.so.0_for_crosvm \
  aarch64_linux_gnu_libffi.so.7_for_crosvm \
  aarch64_linux_gnu_libgbm.so.1_for_crosvm \
  aarch64_linux_gnu_libgfxstream_backend.so_for_crosvm \
  aarch64_linux_gnu_libminijail.so_for_crosvm \
  aarch64_linux_gnu_libvirglrenderer.so.1_for_crosvm \
  aarch64_linux_gnu_libwayland_client.so.0_for_crosvm \
  adb \
  adb_connector \
  config_server \
  control_env_proxy_server \
  cvd \
  cvd_internal_start \
  cvd_internal_status \
  cvd_internal_stop \
  metrics \
  metrics_launcher \
  modem_simulator \
  newfs_msdos \
  openwrt_kernel_aarch64 \
  openwrt_control_server \
  openwrt_rootfs_aarch64 \
  openwrt_rootfs_x86_64 \
  process_restarter \
  record_cvd \
  restart_cvd \
  screen_recording_server \
  tombstone_receiver \
  webRTC \
  webrtc_adb.js \
  webrtc_app.js \
  webrtc_cf.js \
  webrtc_client.html \
  webrtc_controls.css \
  webrtc_controls.js \
  webrtc_custom_blank.css \
  webrtc_index.css \
  webrtc_index.html \
  webrtc_index.js \
  webrtc_location.js \
  webrtc_operator \
  webrtc_rootcanal.js \
  webrtc_server.crt \
  webrtc_server.key \
  webrtc_server.p12 \
  webrtc_server_connector.js \
  webrtc_style.css \
  webrtc_touch.js \
  webrtc_trusted.pem \
  wmediumd \
  wmediumd_gen_config
