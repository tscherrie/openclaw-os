/**
 * BootReceiver — Starts AgentCoreService when device boots.
 *
 * @author Forge (Backend Lead, Agent Lab)
 * @since 0.1.0
 */
package com.openclaw.agent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Slog

class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context?, intent: Intent?) {
        if (intent?.action == Intent.ACTION_BOOT_COMPLETED ||
            intent?.action == "android.intent.action.LOCKED_BOOT_COMPLETED"
        ) {
            Slog.i(TAG, "Boot completed, starting AgentCoreService...")
            val serviceIntent = Intent(context, AgentCoreService::class.java)
            try {
                context?.startService(serviceIntent)
            } catch (e: Exception) {
                Slog.e(TAG, "Failed to start AgentCoreService", e)
            }
        }
    }

    companion object {
        private const val TAG = "BootReceiver"
    }
}
