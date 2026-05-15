# HansOS arm64-only GSI board config for MP01 bring-up.
#
# This keeps the first physical-device image in GSI shape while avoiding the
# upstream gsi_arm64 target's 32-bit secondary architecture on the Linux ARM
# build host.

include build/make/target/board/BoardConfigGsiCommon.mk

TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_ABI2 :=
TARGET_CPU_VARIANT := generic
