# HansOS MP01 bring-up image.
#
# The Minimal Phone MP01 flash path starts with a Treble/GSI-style system.img.
# Unlike the Cuttlefish target, this product installs HansCanvas and
# HansRuntimeService into /system/priv-app so a first hardware flash can touch
# only the dynamic system partition.

# The upstream gsi_arm64 product targets generic_arm64, which also enables a
# 32-bit secondary ARM build. That is useful for broad compliance GSIs, but it
# currently pulls in unnecessary 32-bit ART artifacts on our Linux ARM host. The
# first MP01 image is intentionally arm64-only: MP01 supports arm64-v8a and all
# HansOS system pieces are Java/system_server code.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/generic_system.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/gsi_release.mk)

PRODUCT_BUILD_CACHE_IMAGE := false
PRODUCT_BUILD_ODM_IMAGE := false
PRODUCT_BUILD_PRODUCT_IMAGE := false
PRODUCT_BUILD_RAMDISK_IMAGE := false
PRODUCT_BUILD_SYSTEM_EXT_IMAGE := false
PRODUCT_BUILD_SYSTEM_IMAGE := true
PRODUCT_BUILD_SYSTEM_OTHER_IMAGE := false
PRODUCT_BUILD_USERDATA_IMAGE := false
PRODUCT_BUILD_VENDOR_DLKM_IMAGE := false
PRODUCT_BUILD_VENDOR_IMAGE := false
PRODUCT_RESTRICT_VENDOR_FILES := all
PRODUCT_OTA_ENFORCE_VINTF_KERNEL_REQUIREMENTS := false

PRODUCT_NAME := hansos_gsi_arm64
PRODUCT_DEVICE := gsi
PRODUCT_BRAND := HansOS
PRODUCT_MODEL := HansOS GSI ARM64
PRODUCT_MANUFACTURER := HansOS

# Custom product names do not match the exact upstream GSI allowlist. Keep the
# release-style GSI image shape, but relax path enforcement for HansOS modules.
PRODUCT_ENFORCE_ARTIFACT_PATH_REQUIREMENTS := relaxed
PRODUCT_ARTIFACT_PATH_REQUIREMENT_ALLOWED_LIST += \
    system/etc/permissions/privapp-permissions-ai.hansos.canvas.system.xml \
    system/etc/permissions/privapp-permissions-ai.hansos.runtime.system.xml \
    system/priv-app/HansCanvasSystem/% \
    system/priv-app/HansRuntimeServiceSystem/%

PRODUCT_SOONG_NAMESPACES += \
    packages/apps/HansCanvas \
    packages/services/HansRuntimeService \
    packages/modules/HansProtocol \
    packages/modules/HansFakes

PRODUCT_PACKAGES += \
    HansCanvasSystem \
    HansRuntimeServiceSystem \
    hansos-agent-protocol \
    hansos-fakes \
    privapp-permissions-ai.hansos.canvas.system.xml \
    privapp-permissions-ai.hansos.runtime.system.xml

PRODUCT_SYSTEM_PROPERTIES += \
    ro.hansos.enabled=true \
    ro.hansos.agent_name=Hans \
    persist.hansos.provider=fake
