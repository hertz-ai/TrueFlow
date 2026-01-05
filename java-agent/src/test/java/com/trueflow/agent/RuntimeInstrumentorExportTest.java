package com.trueflow.agent;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for RuntimeInstrumentor export methods.
 * Verifies parity with Python instrumentor exports.
 */
class RuntimeInstrumentorExportTest {

    @TempDir
    Path tempDir;

    private RuntimeInstrumentor instrumentor;
    private AgentConfig config;

    @BeforeEach
    void setUp() {
        config = AgentConfig.parse("enabled=true,traceDir=" + tempDir.toString());
        instrumentor = new RuntimeInstrumentor(config);
    }

    @Test
    void testExportsAllFormats() throws Exception {
        // Simulate some method calls
        String callId1 = instrumentor.onMethodEnter(
            "com.example.UserController", "getUser", "(I)Lcom/example/User;",
            "UserController.java", 42
        );
        Thread.sleep(10); // Simulate some work
        instrumentor.onMethodExit(callId1);

        String callId2 = instrumentor.onMethodEnter(
            "com.example.UserRepository", "findById", "(I)Lcom/example/User;",
            "UserRepository.java", 100
        );
        Thread.sleep(5);
        instrumentor.onMethodExit(callId2);

        String callId3 = instrumentor.onMethodEnter(
            "com.example.UserService", "processUser", "(Lcom/example/User;)V",
            "UserService.java", 55
        );
        Thread.sleep(2);
        instrumentor.onMethodException(callId3, "NullPointerException", "User was null");

        // Finalize and export
        instrumentor.finalize(tempDir.toString());

        // Count exported files
        try (Stream<Path> files = Files.list(tempDir)) {
            long fileCount = files.count();
            System.out.println("Exported " + fileCount + " files to " + tempDir);
            assertTrue(fileCount >= 10, "Should export at least 10 files (got " + fileCount + ")");
        }

        // Verify specific files exist
        String sessionId = instrumentor.getSessionId();

        // Check PlantUML
        File pumlFile = new File(tempDir.toFile(), sessionId + ".puml");
        assertTrue(pumlFile.exists(), "PlantUML file should exist");
        String pumlContent = Files.readString(pumlFile.toPath());
        assertTrue(pumlContent.contains("@startuml"), "PlantUML should have @startuml");
        assertTrue(pumlContent.contains("@enduml"), "PlantUML should have @enduml");
        assertTrue(pumlContent.contains("UserController"), "PlantUML should contain class names");

        // Check Performance JSON
        File perfFile = new File(tempDir.toFile(), sessionId + "_performance.json");
        assertTrue(perfFile.exists(), "Performance JSON should exist");
        String perfContent = Files.readString(perfFile.toPath());
        assertTrue(perfContent.contains("\"function_metrics\""), "Should have function_metrics");
        assertTrue(perfContent.contains("\"call_count\""), "Should have call_count");

        // Check Flamegraph JSON
        File flameFile = new File(tempDir.toFile(), sessionId + "_flamegraph.json");
        assertTrue(flameFile.exists(), "Flamegraph JSON should exist");
        String flameContent = Files.readString(flameFile.toPath());
        assertTrue(flameContent.contains("\"frames\""), "Should have frames");
        assertTrue(flameContent.contains("\"type\":\"flamegraph\""), "Should have type flamegraph");

        // Check SQL Analysis
        File sqlFile = new File(tempDir.toFile(), sessionId + "_sql_analysis.json");
        assertTrue(sqlFile.exists(), "SQL Analysis JSON should exist");
        String sqlContent = Files.readString(sqlFile.toPath());
        assertTrue(sqlContent.contains("\"n_plus_1_issues\""), "Should have n_plus_1_issues");

        // Check Live Metrics
        File metricsFile = new File(tempDir.toFile(), sessionId + "_live_metrics.json");
        assertTrue(metricsFile.exists(), "Live Metrics JSON should exist");
        String metricsContent = Files.readString(metricsFile.toPath());
        assertTrue(metricsContent.contains("\"metrics\""), "Should have metrics");
        assertTrue(metricsContent.contains("\"p95_latency_ms\""), "Should have p95");

        // Check Mermaid
        File mermaidFile = new File(tempDir.toFile(), sessionId + "_mermaid.md");
        assertTrue(mermaidFile.exists(), "Mermaid file should exist");
        String mermaidContent = Files.readString(mermaidFile.toPath());
        assertTrue(mermaidContent.contains("```mermaid"), "Should have mermaid block");
        assertTrue(mermaidContent.contains("sequenceDiagram"), "Should be sequence diagram");

        // Check D2
        File d2File = new File(tempDir.toFile(), sessionId + ".d2");
        assertTrue(d2File.exists(), "D2 file should exist");
        String d2Content = Files.readString(d2File.toPath());
        assertTrue(d2Content.contains("shape: class"), "Should have class shapes");

        // Check LLM Summary
        File llmFile = new File(tempDir.toFile(), sessionId + "_llm_summary.txt");
        assertTrue(llmFile.exists(), "LLM Summary should exist");
        String llmContent = Files.readString(llmFile.toPath());
        assertTrue(llmContent.contains("JAVA EXECUTION TRACE SUMMARY"), "Should have title");
        assertTrue(llmContent.contains("SLOWEST METHODS"), "Should have slowest methods");

        // Check Markdown Summary
        File mdFile = new File(tempDir.toFile(), sessionId + "_summary.md");
        assertTrue(mdFile.exists(), "Markdown Summary should exist");
        String mdContent = Files.readString(mdFile.toPath());
        assertTrue(mdContent.contains("# TrueFlow Java Execution Trace"), "Should have title");
        assertTrue(mdContent.contains("Generated by TrueFlow"), "Should have footer");

        // Check ASCII Art
        File asciiFile = new File(tempDir.toFile(), sessionId + "_ascii.txt");
        assertTrue(asciiFile.exists(), "ASCII Art should exist");
        String asciiContent = Files.readString(asciiFile.toPath());
        assertTrue(asciiContent.contains("TRUEFLOW JAVA EXECUTION TRACE"), "Should have title");
        assertTrue(asciiContent.contains("CALL TREE"), "Should have call tree");

        System.out.println("All 11 export formats verified successfully!");
    }

    @Test
    void testExceptionTracking() throws Exception {
        String callId = instrumentor.onMethodEnter(
            "com.example.ErrorService", "throwError", "()V",
            "ErrorService.java", 10
        );
        instrumentor.onMethodException(callId, "RuntimeException", "Test error");

        instrumentor.finalize(tempDir.toString());

        String sessionId = instrumentor.getSessionId();
        File llmFile = new File(tempDir.toFile(), sessionId + "_llm_summary.txt");
        String content = Files.readString(llmFile.toPath());

        assertTrue(content.contains("EXCEPTIONS"), "Should show exceptions section");
        assertTrue(content.contains("RuntimeException"), "Should contain exception type");
    }

    @Test
    void testSQLProtocolDetection() throws Exception {
        // JPA Repository method - should be detected as SQL
        String callId = instrumentor.onMethodEnter(
            "com.example.UserRepository", "findAll", "()Ljava/util/List;",
            "UserRepository.java", 20
        );
        Thread.sleep(5);
        instrumentor.onMethodExit(callId);

        instrumentor.finalize(tempDir.toString());

        String sessionId = instrumentor.getSessionId();
        File sqlFile = new File(tempDir.toFile(), sessionId + "_sql_analysis.json");
        String content = Files.readString(sqlFile.toPath());

        assertTrue(content.contains("\"total_sql_calls\""), "Should track SQL calls");
    }

    @Test
    void testPerformanceMetricsAggregation() throws Exception {
        // Call same method multiple times
        for (int i = 0; i < 5; i++) {
            String callId = instrumentor.onMethodEnter(
                "com.example.Calculator", "add", "(II)I",
                "Calculator.java", 10
            );
            Thread.sleep(2);
            instrumentor.onMethodExit(callId);
        }

        instrumentor.finalize(tempDir.toString());

        String sessionId = instrumentor.getSessionId();
        File perfFile = new File(tempDir.toFile(), sessionId + "_performance.json");
        String content = Files.readString(perfFile.toPath());

        assertTrue(content.contains("\"call_count\":5"), "Should count 5 calls");
        assertTrue(content.contains("\"avg_time_ms\""), "Should calculate average");
    }
}
