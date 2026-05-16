package ai.hansos.agent;

import ai.hansos.agent.IHansRuntime;
import ai.hansos.agent.IHansStreamCallback;

interface IHansManager {
    String submitIntent(String text, IHansStreamCallback callback);
    String startVoiceSession(IHansStreamCallback callback);
    void appendVoiceAudio(String sessionId, in byte[] pcm16MonoChunk);
    void finishVoiceSession(String sessionId);
    void cancelVoiceSession(String sessionId);
    void reportInputEvent(int keyCode, int action, boolean pttCandidate);
    void registerRuntime(IHansRuntime runtime);
    void unregisterRuntime(IHansRuntime runtime);
    void emergencyStop();
    int getAgentState();
    String getMemorySnapshotJson();
}
