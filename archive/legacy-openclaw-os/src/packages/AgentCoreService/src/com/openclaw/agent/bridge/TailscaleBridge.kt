/**
 * TailscaleBridge — The Nervous System
 *
 * Interface to Tailscale for mesh networking. Connects the phone
 * to the rest of the user's digital life: home servers, smart home
 * devices (via home LAN), other OpenClaw phones, and more.
 *
 * Tailscale is like a VPN, except it actually works and doesn't
 * make you want to throw your laptop out the window.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent.bridge

import kotlinx.coroutines.flow.Flow

/**
 * Interface for Tailscale mesh networking operations.
 */
interface TailscaleBridge {

    companion object {
        fun create(): TailscaleBridge = TailscaleBridgeImpl()
    }

    /**
     * Get current Tailscale connection status.
     */
    fun getStatus(): TailscaleStatus

    /**
     * Is Tailscale connected to the tailnet?
     */
    fun isConnected(): Boolean

    /**
     * Get list of peers in the tailnet.
     * These are your devices: home server, other phones, etc.
     */
    fun getPeers(): List<TailscalePeer>

    /**
     * Connect to a specific service on a peer.
     *
     * @param peerName Tailscale hostname (e.g., "gx10-1")
     * @param port Service port
     * @return Connection handle
     */
    suspend fun connectToPeer(peerName: String, port: Int): PeerConnection

    /**
     * Discover available services on peers.
     * Uses a custom OpenClaw service discovery protocol.
     */
    suspend fun discoverServices(): List<PeerService>

    /**
     * Send a message to another OpenClaw agent on the tailnet.
     * Agent-to-Agent communication — the social network of AIs.
     *
     * @param targetPeer The peer hostname
     * @param message The message to send
     * @return Response from the other agent, if any
     */
    suspend fun sendAgentMessage(
        targetPeer: String,
        message: AgentPeerMessage
    ): AgentPeerMessage?

    /**
     * Observe peer connectivity changes.
     */
    fun observePeerChanges(): Flow<PeerChangeEvent>
}

// ==========================================
// Data Models
// ==========================================

data class TailscaleStatus(
    val connected: Boolean,
    val hostname: String?,
    val tailnetName: String?,
    val ipv4: String?,
    val ipv6: String?,
    val peerCount: Int
)

data class TailscalePeer(
    val hostname: String,
    val displayName: String,
    val ipv4: String,
    val ipv6: String,
    val online: Boolean,
    val lastSeen: Long,          // epoch millis
    val os: String?,             // "android", "linux", "macos", etc.
    val isOpenClawDevice: Boolean // Does it run OpenClaw OS?
)

data class PeerConnection(
    val peerName: String,
    val port: Int,
    val connected: Boolean,
    val localAddress: String?,
    val remoteAddress: String?
) {
    suspend fun close() {
        // TODO: Close connection
    }
}

data class PeerService(
    val peerName: String,
    val serviceType: String,    // "llm", "stt", "tts", "storage", "smarthome"
    val serviceName: String,    // "ollama", "whisper", "qwen-tts"
    val port: Int,
    val metadata: Map<String, String> = emptyMap()
)

data class AgentPeerMessage(
    val fromAgent: String,
    val toAgent: String,
    val contentType: String,    // "text", "command", "query"
    val content: String,
    val priority: String = "normal",
    val replyTo: String? = null
)

sealed class PeerChangeEvent {
    data class PeerOnline(val peer: TailscalePeer) : PeerChangeEvent()
    data class PeerOffline(val hostname: String) : PeerChangeEvent()
    data class ServiceDiscovered(val service: PeerService) : PeerChangeEvent()
    data class ServiceLost(val peerName: String, val serviceType: String) : PeerChangeEvent()
}

// ==========================================
// Stub Implementation
// ==========================================

internal class TailscaleBridgeImpl : TailscaleBridge {

    override fun getStatus(): TailscaleStatus {
        // TODO: Query TailscaleSystemService via Binder
        return TailscaleStatus(
            connected = false,
            hostname = null,
            tailnetName = null,
            ipv4 = null,
            ipv6 = null,
            peerCount = 0
        )
    }

    override fun isConnected(): Boolean = false

    override fun getPeers(): List<TailscalePeer> {
        // TODO: Query TailscaleSystemService
        return emptyList()
    }

    override suspend fun connectToPeer(peerName: String, port: Int): PeerConnection {
        // TODO: Establish TCP connection via Tailscale
        return PeerConnection(peerName, port, false, null, null)
    }

    override suspend fun discoverServices(): List<PeerService> {
        // TODO: Query peers for available services
        return emptyList()
    }

    override suspend fun sendAgentMessage(
        targetPeer: String,
        message: AgentPeerMessage
    ): AgentPeerMessage? {
        // TODO: Send via WebSocket over Tailscale
        return null
    }

    override fun observePeerChanges(): Flow<PeerChangeEvent> {
        // TODO: Observe TailscaleSystemService for peer changes
        return kotlinx.coroutines.flow.emptyFlow()
    }
}
