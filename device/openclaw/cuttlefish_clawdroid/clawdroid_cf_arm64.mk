#
# Product makefile for OpenClaw on Cuttlefish (arm64)
#
# Inherits from standard AOSP cuttlefish and adds OpenClaw packages.
#

# Inherit from AOSP cuttlefish base
$(call inherit-product, device/google/cuttlefish/vsoc_arm64/phone/aosp_cf.mk)

# OpenClaw packages
PRODUCT_PACKAGES += \
    AgentCoreService \
    privapp-permissions-openclaw.xml

# Enable soong namespace for OpenClaw packages
PRODUCT_SOONG_NAMESPACES += \
    openclaw-os/src/packages

# Product info
PRODUCT_NAME := clawdroid_cf_arm64
PRODUCT_DEVICE := cuttlefish_clawdroid
PRODUCT_MANUFACTURER := OpenClaw
PRODUCT_MODEL := OpenClaw Cuttlefish arm64
PRODUCT_BRAND := openclaw

# Shipping API level
PRODUCT_SHIPPING_API_LEVEL := 34
