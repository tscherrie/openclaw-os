package com.openclaw.agent;

interface IAgentResponseCallback {
    /** Streaming token from LLM. */
    void onToken(String requestId, String token, int index);

    /** Agent wants to use a tool. */
    void onToolCall(String requestId, String toolName, String paramsJson,
                    boolean requiresConfirmation, String actionId);

    /** Tool execution result. */
    void onToolResult(String requestId, String toolName, String resultJson, boolean success);

    /** Response complete. */
    void onComplete(String requestId, String finalText);

    /** Error occurred. */
    void onError(String requestId, int errorCode, String errorMessage);
}
