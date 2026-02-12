package com.openclaw.agent;

interface IAgentEventListener {
    /** Agent state changed. */
    void onStateChanged(int newState);

    /** Proactive suggestion from agent. */
    void onProactiveSuggestion(String suggestionJson);

    /** Card update for Agent Canvas. */
    void onCardUpdate(String cardJson);

    /** Cloud connectivity changed. */
    void onConnectivityChanged(boolean isConnected);

    /** New device discovered on Tailscale mesh. */
    void onDeviceDiscovered(String deviceJson);

    /** Context updated (location, calendar, etc.). */
    void onContextUpdate(String contextKey, String contextValueJson);
}
