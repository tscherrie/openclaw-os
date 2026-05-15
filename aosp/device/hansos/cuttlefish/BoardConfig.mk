# HansOS alpha uses ext4 partitions so host image generation stays
# deterministic across Darwin and Linux/ARM64 build hosts.
TARGET_RO_FILE_SYSTEM_TYPE := ext4
TARGET_USERDATAIMAGE_FILE_SYSTEM_TYPE := ext4

-include device/google/cuttlefish/vsoc_arm64_only/BoardConfig.mk
