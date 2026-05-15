#!/usr/bin/env bash
set -euo pipefail

DEFAULT_IF="${1:-${HANSOS_HOST_DEFAULT_IF:-}}"
if [[ -z "${DEFAULT_IF}" ]]; then
  DEFAULT_IF="$(ip route show default 0.0.0.0/0 | awk 'NR == 1 {print $5}')"
fi
if [[ -z "${DEFAULT_IF}" ]]; then
  echo "Could not detect host default network interface." >&2
  exit 1
fi

RUN_USER="${SUDO_USER:-$(id -un)}"
SUDO=()
if [[ "$(id -u)" -ne 0 ]]; then
  SUDO=(sudo)
fi

ensure_tap() {
  local name="$1"
  if ! ip link show "${name}" >/dev/null 2>&1; then
    "${SUDO[@]}" ip tuntap add dev "${name}" mode tap user "${RUN_USER}"
  fi
  "${SUDO[@]}" ip link set "${name}" up
}

ensure_addr() {
  local name="$1"
  local cidr="$2"
  if ! ip addr show dev "${name}" | grep -Fq "${cidr%/*}"; then
    "${SUDO[@]}" ip addr add "${cidr}" dev "${name}"
  fi
}

ensure_rule() {
  if ! "${SUDO[@]}" iptables -C "$@" 2>/dev/null; then
    "${SUDO[@]}" iptables -A "$@"
  fi
}

ensure_nat_rule() {
  if ! "${SUDO[@]}" iptables -t nat -C "$@" 2>/dev/null; then
    "${SUDO[@]}" iptables -t nat -A "$@"
  fi
}

ensure_tap cvd-wtap-01
ensure_addr cvd-wtap-01 192.168.96.1/30
ensure_tap cvd-etap-01

"${SUDO[@]}" sysctl -w net.ipv4.ip_forward=1 >/dev/null
ensure_rule FORWARD -i cvd-wtap-01 -o "${DEFAULT_IF}" -j ACCEPT
ensure_rule FORWARD -i "${DEFAULT_IF}" -o cvd-wtap-01 -m state --state RELATED,ESTABLISHED -j ACCEPT
ensure_nat_rule POSTROUTING -s 192.168.96.0/30 -o "${DEFAULT_IF}" -j MASQUERADE

echo "Cuttlefish host network ready on ${DEFAULT_IF}: cvd-wtap-01, cvd-etap-01, IPv4 forwarding, NAT."
