# The inherited Cuttlefish virtualization product enables fs-verity build
# manifests. On Darwin host image builds those Make-side manifest rules still
# depend on legacy framework-res intermediates that are not emitted for the
# Soong-only Cuttlefish target. This product variable is single-valued and must
# be set before inheritance so the alpha boot path stays deterministic.
PRODUCT_FSVERITY_GENERATE_METADATA := false

# PRODUCT_DEVICE intentionally stays vsoc_arm64_only so Cuttlefish host tooling
# keeps the standard output layout. Set image formats here, before the inherited
# product can apply its EROFS/F2FS defaults.
TARGET_RO_FILE_SYSTEM_TYPE := ext4
TARGET_USERDATAIMAGE_FILE_SYSTEM_TYPE := ext4

# Keep APEX payloads on ext4 for the Darwin-hosted alpha build. Some upstream
# release flags default preinstalled APEX payloads to EROFS, which pulls in
# mkfs.erofs host tooling before the boot path needs it.
PRODUCT_DEFAULT_APEX_PAYLOAD_TYPE := ext4

$(call inherit-product, device/google/cuttlefish/vsoc_arm64_only/phone/aosp_cf.mk)
$(call inherit-product, device/hansos/cuttlefish/device.mk)

PRODUCT_NAME := hansos_cf_arm64
PRODUCT_DEVICE := vsoc_arm64_only
PRODUCT_BRAND := HansOS
PRODUCT_MODEL := HansOS Cuttlefish ARM64
PRODUCT_MANUFACTURER := HansOS

# The inherited Cuttlefish product only enables Soong-only image generation for
# its exact upstream TARGET_PRODUCT. HansOS has its own product name, so carry
# the same setting forward explicitly; otherwise the build falls back to Make
# image file lists while the base Cuttlefish product ignores Android.mk modules,
# producing tiny non-bootable partitions.
PRODUCT_SOONG_ONLY := $(RELEASE_SOONG_ONLY_CUTTLEFISH)

PRODUCT_SOONG_NAMESPACES += \
    packages/apps/HansCanvas \
    packages/services/HansRuntimeService \
    packages/modules/HansProtocol \
    packages/modules/HansFakes

PRODUCT_PACKAGES += \
    HansCanvas \
    HansRuntimeService \
    hansos-agent-protocol \
    hansos-fakes \
    privapp-permissions-ai.hansos.canvas.xml \
    privapp-permissions-ai.hansos.runtime.xml

PRODUCT_SYSTEM_EXT_PROPERTIES += \
    ro.hansos.enabled=true \
    ro.hansos.agent_name=Hans

# HansOS local: some ARM64 host checkouts inherit this optional host tool even
# though no module is present for the local host configuration.
PRODUCT_HOST_PACKAGES := $(filter-out ld.mc,$(PRODUCT_HOST_PACKAGES))
