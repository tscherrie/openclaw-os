package ai.hansos.agent;

import ai.hansos.agent.IHansStreamCallback;

interface IHansRuntime {
    String submitIntent(String text, IHansStreamCallback callback);
    String startVoiceSession(IHansStreamCallback callback);
    void appendVoiceAudio(String sessionId, in byte[] pcm16MonoChunk);
    void finishVoiceSession(String sessionId);
    void cancelVoiceSession(String sessionId);
    void emergencyStop();
    int getRuntimeState();
}
