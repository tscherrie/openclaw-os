package ai.hansos.agent;

import ai.hansos.agent.IHansRuntime;
import ai.hansos.agent.IHansStreamCallback;

interface IHansManager {
    String submitIntent(String text, IHansStreamCallback callback);
    void registerRuntime(IHansRuntime runtime);
    void unregisterRuntime(IHansRuntime runtime);
    void emergencyStop();
    int getAgentState();
    String getMemorySnapshotJson();
}
