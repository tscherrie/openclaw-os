package com.android.server;

final class SystemServer {
    private SystemServiceManager mSystemServiceManager;

    private void startOtherServices(TimingsTraceAndSlog t) {
        mSystemServiceManager.startBootPhase(t, SystemService.PHASE_SYSTEM_SERVICES_READY);
    }
}

final class SystemServiceManager {
    void startBootPhase(TimingsTraceAndSlog t, int phase) {
    }
}

final class TimingsTraceAndSlog {
}

final class SystemService {
    static final int PHASE_SYSTEM_SERVICES_READY = 500;
}
