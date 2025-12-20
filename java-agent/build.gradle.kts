plugins {
    java
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

group = "com.trueflow"
version = "0.1.0"

java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}

repositories {
    mavenCentral()
}

dependencies {
    // ASM for bytecode manipulation
    implementation("org.ow2.asm:asm:9.6")
    implementation("org.ow2.asm:asm-commons:9.6")
    implementation("org.ow2.asm:asm-util:9.6")

    // JSON serialization
    implementation("com.google.code.gson:gson:2.10.1")

    // Testing
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.0")
}

tasks.jar {
    manifest {
        attributes(
            "Premain-Class" to "com.trueflow.agent.TrueFlowAgent",
            "Agent-Class" to "com.trueflow.agent.TrueFlowAgent",
            "Can-Redefine-Classes" to "true",
            "Can-Retransform-Classes" to "true",
            "Can-Set-Native-Method-Prefix" to "true"
        )
    }
}

tasks.named<com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar>("shadowJar") {
    archiveBaseName.set("trueflow-agent")
    archiveClassifier.set("")

    manifest {
        attributes(
            "Premain-Class" to "com.trueflow.agent.TrueFlowAgent",
            "Agent-Class" to "com.trueflow.agent.TrueFlowAgent",
            "Can-Redefine-Classes" to "true",
            "Can-Retransform-Classes" to "true",
            "Can-Set-Native-Method-Prefix" to "true"
        )
    }
}

tasks.test {
    useJUnitPlatform()
}
