package com.crawl4ai.learningviz

/**
 * Generates Mermaid sequence diagrams from trace sessions.
 */
class MermaidGenerator {

    fun generateSequenceDiagram(session: TraceParser.TraceSession): String {
        val builder = StringBuilder()

        builder.appendLine("```mermaid")
        builder.appendLine("sequenceDiagram")
        builder.appendLine("    autonumber")

        // Collect unique participants (modules)
        val participants = session.events
            .map { it.module }
            .distinct()
            .sorted()

        // Add participants
        for (participant in participants) {
            val displayName = participant.split(".").lastOrNull() ?: participant
            builder.appendLine("    participant ${cleanName(participant)} as $displayName")
        }

        builder.appendLine()

        // Add events
        for (event in session.events) {
            val src = cleanName(event.module)

            when (event.event_type) {
                "api" -> {
                    builder.appendLine("    ${src}->>${src}: ${event.function_name}")
                    if (event.duration_ms != null) {
                        builder.appendLine("    Note right of ${src}: ${String.format("%.1f", event.duration_ms)}ms")
                    }
                }

                "learning" -> {
                    builder.appendLine("    activate ${src}")
                    builder.appendLine("    Note over ${src}: ${event.function_name}")

                    // Add learning stats if available
                    event.learning_stats?.let { stats ->
                        val errorReduction = stats["error_reduction"]
                        if (errorReduction != null) {
                            builder.appendLine("    Note right of ${src}: Error reduction: ${String.format("%.2f", errorReduction)}")
                        }
                    }

                    builder.appendLine("    deactivate ${src}")
                }

                "prediction" -> {
                    builder.appendLine("    ${src}->>${src}: ${event.function_name}")
                    event.learning_stats?.let { stats ->
                        val error = stats["error"]
                        if (error != null) {
                            builder.appendLine("    Note right of ${src}: Error: ${String.format("%.2f", error)}")
                        }
                    }
                }

                "validation" -> {
                    builder.appendLine("    ${src}->>${src}: ${event.function_name}")
                    event.learning_stats?.let { stats ->
                        val passed = stats["validation_passed"]
                        if (passed == true) {
                            builder.appendLine("    Note right of ${src}: ✓ Validation passed")
                        } else {
                            builder.appendLine("    Note right of ${src}: ✗ Validation failed")
                        }
                    }
                }

                else -> {
                    builder.appendLine("    ${src}->>${src}: ${event.function_name}")
                }
            }

            // Add error notes
            if (!event.error.isNullOrEmpty()) {
                builder.appendLine("    Note over ${src}: ⚠ ${event.error}")
            }
        }

        builder.appendLine("```")

        return builder.toString()
    }

    private fun cleanName(name: String): String {
        return name.replace(".", "_").replace("-", "_")
    }

    fun generateFlowchart(session: TraceParser.TraceSession): String {
        val builder = StringBuilder()

        builder.appendLine("```mermaid")
        builder.appendLine("flowchart TD")

        for ((index, event) in session.events.withIndex()) {
            val nodeId = "E$index"
            val label = "${event.function_name}<br/>${event.event_type}"

            when (event.event_type) {
                "api" -> builder.appendLine("    ${nodeId}[\"$label\"]")
                "learning" -> builder.appendLine("    ${nodeId}{\"$label\"}")
                "validation" -> {
                    val passed = event.learning_stats?.get("validation_passed") == true
                    if (passed) {
                        builder.appendLine("    ${nodeId}[\"$label\"]:::success")
                    } else {
                        builder.appendLine("    ${nodeId}[\"$label\"]:::error")
                    }
                }
                else -> builder.appendLine("    ${nodeId}(\"$label\")")
            }

            // Add connections based on parent-child relationships
            event.children_event_ids?.forEach { childId ->
                val childIndex = session.events.indexOfFirst { it.event_id == childId }
                if (childIndex >= 0) {
                    builder.appendLine("    ${nodeId} --> E${childIndex}")
                }
            }
        }

        // Add styling
        builder.appendLine("    classDef success fill:#90EE90")
        builder.appendLine("    classDef error fill:#FFB6C1")

        builder.appendLine("```")

        return builder.toString()
    }
}
