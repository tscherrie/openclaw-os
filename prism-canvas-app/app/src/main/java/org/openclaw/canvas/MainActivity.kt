package org.openclaw.canvas

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import org.openclaw.canvas.ui.ChatScreen
import org.openclaw.canvas.ui.theme.PrismCanvasTheme
import org.openclaw.canvas.viewmodel.CanvasViewModel

/**
 * Einzige Activity der Canvas-App.
 * Single-Screen, kein Navigation-Graph.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PrismCanvasTheme {
                val viewModel: CanvasViewModel = viewModel()
                val state by viewModel.state.collectAsState()

                ChatScreen(
                    state = state,
                    onInputChanged = viewModel::onInputChanged,
                    onSend = viewModel::sendMessage,
                )
            }
        }
    }
}
