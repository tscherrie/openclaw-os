// AgentCanvas — Build Configuration
// "The build system is the first thing that breaks and the last thing anyone wants to fix."

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "os.openclaw.agentcanvas"
    compileSdk = 35

    defaultConfig {
        applicationId = "os.openclaw.agentcanvas"
        minSdk = 31  // Android 12+ (we're not supporting phones from the Bronze Age)
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0-sprint1"
    }

    buildFeatures {
        compose = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.8"
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // Compose BOM — one version to rule them all
    val composeBom = platform("androidx.compose:compose-bom:2024.02.00")
    implementation(composeBom)

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.animation:animation")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.7.0")

    // Debug — for the preview to work
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
