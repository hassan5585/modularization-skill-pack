package @@PACKAGE@@

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import @@PACKAGE@@.android.BuildConfig
import @@PACKAGE@@.app.App
import @@PACKAGE@@.core.domain.model.Environment

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Environment.configure(
            id = BuildConfig.APP_ENVIRONMENT,
            isDebuggable = BuildConfig.DEBUG,
        )
        enableEdgeToEdge()
        setContent { App() }
    }
}
