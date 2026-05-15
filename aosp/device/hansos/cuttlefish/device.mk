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
