#
# Device configuration for OpenClaw Cuttlefish (arm64)
#
# Adds OpenClaw packages and Soong namespaces on top of AOSP Cuttlefish.
#

# OpenClaw packages
PRODUCT_PACKAGES += \
    AgentCoreService \
    privapp-permissions-openclaw.xml

# Soong namespaces for OpenClaw modules
PRODUCT_SOONG_NAMESPACES += \
    openclaw-os/src/packages
