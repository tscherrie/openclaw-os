package ai.hansos.agent;

import ai.hansos.agent.IHansStreamCallback;

interface IHansRuntime {
    String submitIntent(String text, IHansStreamCallback callback);
    void emergencyStop();
    int getRuntimeState();
}
