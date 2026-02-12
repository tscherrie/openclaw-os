/**
 * PeripheralManager — The Device Whisperer
 *
 * Manages connections to external devices: smart home gadgets,
 * vehicles, home servers, and other OpenClaw phones.
 *
 * Think of it as a universal remote control, except it doesn't
 * just control TVs — it controls your entire life. And unlike
 * a universal remote, it won't get lost between couch cushions.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent.peripheral

import com.openclaw.agent.bridge.TailscaleBridge
import com.openclaw.agent.model.PeripheralState
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emptyFlow

/**
 * Interface for managing peripheral devices.
 */
interface PeripheralManager {

    companion object {
        fun create(tailscaleBridge: TailscaleBridge): PeripheralManager =
            PeripheralManagerImpl(tailscaleBridge)
    }

    /**
     * Discover available devices on the network.
     * Uses mDNS, Tailscale peer discovery, and cloud APIs.
     */
    suspend fun discoverDevices(): List<Peripheral>

    /**
     * Get all registered/known devices.
     */
    fun getDevices(): List<Peripheral>

    /**
     * Execute a command on a peripheral device.
     *
     * @param deviceId The device identifier
     * @param command The command to execute
     * @return Response from the device
     */
    suspend fun executeCommand(
        deviceId: String,
        command: DeviceCommand
    ): DeviceResponse

    /**
     * Subscribe to state changes from a device.
     */
    fun observeDevice(deviceId: String): Flow<PeripheralState>

    /**
     * Register a new device driver.
     */
    fun registerDriver(driver: PeripheralDriver)

    /**
     * Get available drivers.
     */
    fun getDrivers(): List<PeripheralDriverInfo>
}

// ==========================================
// Data Models
// ==========================================

/**
 * A peripheral device known to the system.
 */
data class Peripheral(
    val id: String,
    val name: String,
    val type: PeripheralType,
    val driver: String,           // Driver ID that handles this device
    val connectionType: String,   // "lan", "tailscale", "bluetooth", "cloud_api"
    val address: String?,         // IP, BLE address, etc.
    val online: Boolean,
    val capabilities: List<String>,  // What this device can do
    val metadata: Map<String, String> = emptyMap()
)

enum class PeripheralType {
    SMART_HOME,     // Lights, plugs, thermostats, sensors
    VEHICLE,        // Tesla, etc.
    HOME_SERVER,    // GPU server, NAS
    DISPLAY,        // TV, smart display
    CAMERA,         // Security camera
    PRINTER,        // 3D printer, paper printer
    PHONE,          // Another OpenClaw phone
    OTHER
}

/**
 * A command to send to a peripheral device.
 */
data class DeviceCommand(
    val action: String,
    val parameters: Map<String, Any?> = emptyMap()
)

/**
 * Response from a peripheral device.
 */
data class DeviceResponse(
    val success: Boolean,
    val data: Map<String, Any?> = emptyMap(),
    val error: String? = null
)

/**
 * Interface for peripheral device drivers.
 * Each smart home protocol gets its own driver.
 */
interface PeripheralDriver {
    /** Unique driver ID */
    val id: String

    /** Human-readable name */
    val name: String

    /** What types of devices this driver supports */
    val supportedTypes: List<PeripheralType>

    /** Discover devices using this driver's protocol */
    suspend fun discover(): List<Peripheral>

    /** Execute a command on a device */
    suspend fun execute(device: Peripheral, command: DeviceCommand): DeviceResponse

    /** Get current state of a device */
    suspend fun getState(device: Peripheral): PeripheralState

    /** Subscribe to state changes */
    fun observe(device: Peripheral): Flow<PeripheralState>
}

data class PeripheralDriverInfo(
    val id: String,
    val name: String,
    val supportedTypes: List<PeripheralType>,
    val deviceCount: Int  // How many devices are using this driver
)

// ==========================================
// Built-in Driver Stubs
// ==========================================

/**
 * SwitchBot driver — controls SwitchBot devices via their API.
 */
class SwitchBotDriver : PeripheralDriver {
    override val id = "switchbot"
    override val name = "SwitchBot"
    override val supportedTypes = listOf(PeripheralType.SMART_HOME)

    override suspend fun discover(): List<Peripheral> = emptyList() // TODO
    override suspend fun execute(device: Peripheral, command: DeviceCommand): DeviceResponse {
        // TODO: Implement SwitchBot API calls
        return DeviceResponse(false, error = "SwitchBot driver not yet implemented")
    }
    override suspend fun getState(device: Peripheral): PeripheralState {
        return PeripheralState(device.id, device.name, "switchbot", false)
    }
    override fun observe(device: Peripheral): Flow<PeripheralState> = emptyFlow()
}

/**
 * Tapo driver — controls TP-Link Tapo devices via KLAP protocol.
 */
class TapoDriver : PeripheralDriver {
    override val id = "tapo"
    override val name = "TP-Link Tapo"
    override val supportedTypes = listOf(PeripheralType.SMART_HOME)

    override suspend fun discover(): List<Peripheral> = emptyList() // TODO
    override suspend fun execute(device: Peripheral, command: DeviceCommand): DeviceResponse {
        // TODO: Implement KLAP protocol
        return DeviceResponse(false, error = "Tapo driver not yet implemented")
    }
    override suspend fun getState(device: Peripheral): PeripheralState {
        return PeripheralState(device.id, device.name, "tapo", false)
    }
    override fun observe(device: Peripheral): Flow<PeripheralState> = emptyFlow()
}

/**
 * Tesla driver — controls Tesla vehicles via Fleet API.
 */
class TeslaDriver : PeripheralDriver {
    override val id = "tesla"
    override val name = "Tesla Fleet API"
    override val supportedTypes = listOf(PeripheralType.VEHICLE)

    override suspend fun discover(): List<Peripheral> = emptyList() // TODO
    override suspend fun execute(device: Peripheral, command: DeviceCommand): DeviceResponse {
        // TODO: Implement Tesla Fleet API
        return DeviceResponse(false, error = "Tesla driver not yet implemented")
    }
    override suspend fun getState(device: Peripheral): PeripheralState {
        return PeripheralState(device.id, device.name, "tesla", false)
    }
    override fun observe(device: Peripheral): Flow<PeripheralState> = emptyFlow()
}

// ==========================================
// Manager Implementation
// ==========================================

internal class PeripheralManagerImpl(
    private val tailscaleBridge: TailscaleBridge
) : PeripheralManager {

    private val drivers = mutableMapOf<String, PeripheralDriver>()
    private val knownDevices = mutableMapOf<String, Peripheral>()

    override suspend fun discoverDevices(): List<Peripheral> {
        val discovered = mutableListOf<Peripheral>()

        // Discover via each registered driver
        for ((_, driver) in drivers) {
            try {
                discovered.addAll(driver.discover())
            } catch (e: Exception) {
                android.util.Slog.w("PeripheralManager",
                    "Discovery failed for driver ${driver.id}: ${e.message}")
            }
        }

        // Discover Tailscale peers
        if (tailscaleBridge.isConnected()) {
            val peers = tailscaleBridge.getPeers()
            for (peer in peers.filter { it.isOpenClawDevice }) {
                discovered.add(Peripheral(
                    id = "phone_${peer.hostname}",
                    name = peer.displayName,
                    type = PeripheralType.PHONE,
                    driver = "openclaw_peer",
                    connectionType = "tailscale",
                    address = peer.ipv4,
                    online = peer.online,
                    capabilities = listOf("messaging", "agent_relay")
                ))
            }
        }

        // Update known devices
        for (device in discovered) {
            knownDevices[device.id] = device
        }

        return discovered
    }

    override fun getDevices(): List<Peripheral> = knownDevices.values.toList()

    override suspend fun executeCommand(
        deviceId: String,
        command: DeviceCommand
    ): DeviceResponse {
        val device = knownDevices[deviceId]
            ?: return DeviceResponse(false, error = "Unknown device: $deviceId")

        val driver = drivers[device.driver]
            ?: return DeviceResponse(false, error = "No driver for: ${device.driver}")

        return driver.execute(device, command)
    }

    override fun observeDevice(deviceId: String): Flow<PeripheralState> {
        val device = knownDevices[deviceId] ?: return emptyFlow()
        val driver = drivers[device.driver] ?: return emptyFlow()
        return driver.observe(device)
    }

    override fun registerDriver(driver: PeripheralDriver) {
        drivers[driver.id] = driver
        android.util.Slog.i("PeripheralManager", "Registered driver: ${driver.id} (${driver.name})")
    }

    override fun getDrivers(): List<PeripheralDriverInfo> {
        return drivers.values.map { driver ->
            PeripheralDriverInfo(
                id = driver.id,
                name = driver.name,
                supportedTypes = driver.supportedTypes,
                deviceCount = knownDevices.values.count { it.driver == driver.id }
            )
        }
    }
}
