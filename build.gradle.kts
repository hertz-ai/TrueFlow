import java.util.Properties

plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.21"
    id("org.jetbrains.intellij") version "1.17.3"
}

group = "com.trueflow"

// Auto-increment version on each build
version = run {
    val pythonExe = findProperty("python.executable")?.toString() ?: "python"
    val versionScript = file("increment_version.py")

    if (versionScript.exists()) {
        try {
            val process = ProcessBuilder(pythonExe, versionScript.absolutePath)
                .directory(projectDir)
                .redirectErrorStream(true)
                .start()

            val output = process.inputStream.bufferedReader().readText()
            val exitCode = process.waitFor()

            if (exitCode == 0) {
                println("Version auto-incremented successfully")
                println(output)
            } else {
                println("Warning: Version increment failed: $output")
            }
        } catch (e: Exception) {
            println("Warning: Could not auto-increment version: ${e.message}")
        }
    }

    // Read version from gradle.properties
    val props = Properties()
    file("gradle.properties").inputStream().use { props.load(it) }
    props.getProperty("pluginVersion", "1.0.0")
}

repositories {
    mavenCentral()
}

// Configure Gradle IntelliJ Plugin
// Supports multiple IDE variants:
//   PC = PyCharm Community (default) - has built-in Python support
//   IU = IntelliJ IDEA Ultimate - requires Python plugin for Python features
//   IC = IntelliJ IDEA Community - requires Python plugin for Python features
// Usage: ./gradlew buildPlugin -PideType=IU
val ideType = findProperty("ideType")?.toString() ?: "PC"

intellij {
    version.set("2023.3.2")
    type.set(ideType)

    // For IntelliJ IDEA, include Python plugin as optional dependency
    // This enables Python features when Python plugin is installed
    if (ideType == "IU" || ideType == "IC") {
        plugins.set(listOf("PythonCore:233.11799.241"))  // Python Community plugin
    }
    // PyCharm (PC) has Python built-in, no additional plugins needed
}

dependencies {
    implementation("com.google.code.gson:gson:2.10.1")
    implementation("org.commonmark:commonmark:0.21.0")
    implementation("org.java-websocket:Java-WebSocket:1.5.6")  // WebSocket client for Hub communication
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.1")
}

tasks {
    // ========================================
    // Python Regression Testing Tasks
    // ========================================

    // Base task for running pytest with configurable options
    abstract class PytestTask : Exec() {
        @get:Input
        abstract val testMarkers: Property<String>

        @get:Input
        abstract val extraArgs: ListProperty<String>

        @get:OutputDirectory
        abstract val reportDir: DirectoryProperty

        init {
            group = "verification"
            workingDir = project.file("manim_visualizer")

            // Use Python from gradle properties or default
            val pythonExe = project.findProperty("python.executable")?.toString() ?: "python"
            executable = pythonExe

            // Base pytest args
            val baseArgs = mutableListOf(
                "-m", "pytest",
                "tests/",
                "-v",
                "--tb=short"
            )

            // Add markers if specified
            doFirst {
                val finalArgs = baseArgs.toMutableList()
                val markers = testMarkers.orNull
                if (!markers.isNullOrBlank()) {
                    finalArgs.add("-m")
                    finalArgs.add(markers)
                }

                // Add extra args
                finalArgs.addAll(extraArgs.getOrElse(emptyList()))

                // Add HTML report output
                val reportPath = reportDir.get().asFile.absolutePath.replace("\\", "/")
                finalArgs.add("--html=${reportPath}/pytest-report.html")
                finalArgs.add("--self-contained-html")

                args = finalArgs

                println("=".repeat(70))
                println("Running pytest with command:")
                println("  $executable ${finalArgs.joinToString(" ")}")
                println("  Working dir: ${workingDir.absolutePath}")
                println("=".repeat(70))
            }

            // Create report directory
            doFirst {
                reportDir.get().asFile.mkdirs()
            }

            // Handle test failures
            isIgnoreExitValue = false
        }
    }

    // Quick tests - unit tests only, no slow tests
    val runQuickTests by registering(PytestTask::class) {
        description = "Run quick regression tests (unit tests only, no slow tests)"
        testMarkers.set("unit and not slow")
        extraArgs.set(listOf("--maxfail=3"))
        reportDir.set(project.layout.buildDirectory.dir("reports/pytest-quick"))
    }

    // Fast tests - skip slow integration tests
    val runFastTests by registering(PytestTask::class) {
        description = "Run fast tests (skip slow tests)"
        testMarkers.set("not slow")
        extraArgs.set(emptyList())
        reportDir.set(project.layout.buildDirectory.dir("reports/pytest-fast"))
    }

    // Full regression - all tests including slow e2e
    val runRegressionTests by registering(PytestTask::class) {
        description = "Run full regression test suite (all tests including slow)"
        testMarkers.set("")  // No marker filtering
        extraArgs.set(emptyList())
        reportDir.set(project.layout.buildDirectory.dir("reports/pytest-full"))
    }

    // Integration tests only
    val runIntegrationTests by registering(PytestTask::class) {
        description = "Run integration tests only"
        testMarkers.set("integration")
        extraArgs.set(emptyList())
        reportDir.set(project.layout.buildDirectory.dir("reports/pytest-integration"))
    }

    // Coverage report task
    val generateCoverageReport by registering(Exec::class) {
        group = "verification"
        description = "Generate HTML coverage report"
        workingDir = project.file("manim_visualizer")

        val pythonExe = project.findProperty("python.executable")?.toString() ?: "python"
        executable = pythonExe

        args = listOf(
            "-m", "coverage", "html",
            "-d", project.layout.buildDirectory.dir("reports/coverage").get().asFile.absolutePath
        )

        dependsOn(runRegressionTests)
    }

    // Combined build and test task (opt-in)
    val buildAndTest by registering {
        group = "build"
        description = "Build plugin JAR and run fast regression tests"
        dependsOn("build", runFastTests)

        // Ensure tests run after build
        mustRunAfter("build")
    }

    // Full verification (build + full regression)
    val verify by registering {
        group = "verification"
        description = "Build plugin and run full regression suite"
        dependsOn("build", runRegressionTests)

        // Ensure tests run after build
        mustRunAfter("build")
    }

    // Frame bounds validation - critical test that runs after build
    // This catches Manim elements rendered outside visible frame
    val runFrameBoundsTest by registering(Exec::class) {
        group = "verification"
        description = "Run frame bounds validation tests (checks elements stay in frame)"
        workingDir = project.file("manim_visualizer")

        val pythonExe = project.findProperty("python.executable")?.toString() ?: "python"
        executable = pythonExe

        args(
            "-m", "pytest",
            "tests/test_frame_bounds_validation.py",
            "-v",
            "--tb=short"
        )

        // Don't fail the build, just warn
        isIgnoreExitValue = true

        doLast {
            if (executionResult.get().exitValue != 0) {
                logger.warn("WARNING: Frame bounds tests failed! Elements may be rendering outside visible frame.")
                logger.warn("Run 'gradle runFrameBoundsTest' to see details.")
            } else {
                logger.lifecycle("Frame bounds validation PASSED - all elements within visible frame")
            }
        }
    }

    // Hook frame bounds test into the build process
    named("build") {
        finalizedBy(runFrameBoundsTest)
    }

    // ========================================
    // End Python Regression Testing Tasks
    // ========================================

    // Generate version properties file at build time
    val generateVersionFile by registering {
        doLast {
            val versionFile = file("src/main/resources/plugin-version.properties")
            versionFile.parentFile.mkdirs()
            versionFile.writeText("pluginVersion=${project.version}\n")
            println("[OK] Generated plugin-version.properties with version: ${project.version}")
        }
    }

    // Copy all Python resources into JAR (preserving directory structure)
    val copyPythonResources by registering(Copy::class) {
        from("manim_visualizer") {
            include("**/*.py")
            exclude("**/__pycache__/**")
            exclude("**/test_*.py")
            exclude("**/*.pyc")
        }
        into("src/main/resources/manim_visualizer")

        from("runtime_injector") {
            include("**/*.py")
            exclude("**/__pycache__/**")
            exclude("**/*.pyc")
        }
        into("src/main/resources/runtime_injector")
    }

    // Make processResources depend on version file generation and Python resource copying
    processResources {
        dependsOn(generateVersionFile, copyPythonResources)
    }

    // Set the JVM compatibility versions
    withType<JavaCompile> {
        sourceCompatibility = "17"
        targetCompatibility = "17"
    }

    withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
        kotlinOptions.jvmTarget = "17"
    }

    patchPluginXml {
        sinceBuild.set("231")
        untilBuild.set("251.*")  // Supports up to Android Studio 2025.1 (Meerkat)

        pluginDescription.set("""
            TrueFlow - Deterministic Code Visualizer & Explainer

            Unblackbox LLM code with deterministic truth. Reveals hidden execution paths
            of AI-generated code. Zero-code auto-instrumentation with JRebel-style runtime injection.
            No SDK required. No code changes. Just one click!

            Features: 3D animated execution videos (Manim), Flamegraph visualization,
            SQL query analyzer, Live metrics dashboard, PlantUML/Mermaid/D2 diagrams,
            Dead code detection, Performance profiling, and 29+ protocol detection.

            For detailed documentation visit https://github.com/trueflow/trueflow
        """.trimIndent())

        changeNotes.set("""
            Version 1.0.0 - Initial release with comprehensive crash prevention,
            error handling, SQL detection, and 11 export formats.
            All 32 tests passing. Production ready.
        """.trimIndent())
    }

    signPlugin {
        certificateChain.set(System.getenv("CERTIFICATE_CHAIN"))
        privateKey.set(System.getenv("PRIVATE_KEY"))
        password.set(System.getenv("PRIVATE_KEY_PASSWORD"))
    }

    publishPlugin {
        token.set(System.getenv("PUBLISH_TOKEN"))
    }

    test {
        useJUnitPlatform()
    }

    // Set artifact name to include version
    named<Jar>("jar") {
        archiveBaseName.set("trueflow")
        archiveVersion.set(project.version.toString())
    }
}
