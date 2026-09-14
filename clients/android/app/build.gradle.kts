import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

// design/tokens.json is the one source for stadium colour and motion. It is
// copied into the APK's assets at build time, never duplicated by hand, so a
// token edit reaches Android the same way it reaches the headset and the web.
abstract class CopyDesignTokens : DefaultTask() {
    @get:InputFile
    abstract val source: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun copy() {
        val out = outputDir.get().asFile
        out.mkdirs()
        source.get().asFile.copyTo(out.resolve("tokens.json"), overwrite = true)
    }
}

val repoRoot = rootProject.layout.projectDirectory.dir("../..")
val designTokens = repoRoot.file("design/tokens.json")

val copyDesignTokens = tasks.register<CopyDesignTokens>("copyDesignTokens") {
    source.set(designTokens)
    outputDir.set(layout.buildDirectory.dir("generated/designTokens"))
}

android {
    namespace = "com.mutaaf.fantasyedge.stadium"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.mutaaf.fantasyedge.stadium"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        // The emulator reaches the host's loopback at 10.0.2.2.
        buildConfigField("String", "DEFAULT_API", "\"http://10.0.2.2:8794\"")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.all {
            it.systemProperty("designTokens", designTokens.asFile.absolutePath)
        }
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(copyDesignTokens, CopyDesignTokens::outputDir)
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.12.01")
    implementation(composeBom)
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.activity:activity-compose:1.12.4")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.4")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material3:material3-window-size-class")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("com.google.android.filament:filament-android:1.75.1")
    implementation("com.google.android.filament:filamat-android:1.75.1")

    testImplementation("junit:junit:4.13.2")
}
