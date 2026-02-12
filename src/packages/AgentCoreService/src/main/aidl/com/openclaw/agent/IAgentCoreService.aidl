package com.openclaw.agent;

import com.openclaw.agent.IAgentResponseCallback;
import com.openclaw.agent.IAgentEventListener;

interface IAgentCoreService {
    /** Send user request, get streaming response via callback. Returns requestId. */
    String submitRequest(String text, IAgentResponseCallback callback);

    /** Cancel an in-flight request. */
    boolean cancelRequest(String requestId);

    /** Get current agent state (0=idle, 1=listening, 2=thinking, 3=acting, 4=confirming, 5=error). */
    int getAgentState();

    /** Register for agent events (state changes, cards, suggestions). */
    void registerEventListener(IAgentEventListener listener);
    void unregisterEventListener(IAgentEventListener listener);

    /** Approve or reject a pending action. */
    void confirmAction(String actionId, boolean confirmed);

    /** EMERGENCY STOP — cancel everything, return to idle. */
    void emergencyStop();

    /** Check cloud connectivity. */
    boolean isCloudAvailable();

    /** Get current context summary. */
    String getContextSummary();

    /** Enable/disable an agent capability. */
    boolean setCapabilityEnabled(String capabilityId, boolean enabled);
}
