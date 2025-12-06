# TrueFlow Java Agent

Zero-code runtime instrumentation for Java applications. Captures method calls, timing, and execution flow without modifying your code.

## Features

- **Zero-code instrumentation**: No SDK or annotations required
- **Real-time streaming**: Events stream to IDE via TCP socket (port 5679)
- **Hierarchical tracing**: Full call stack with parent-child relationships
- **Protocol detection**: Automatically detects SQL, HTTP, gRPC, Kafka, etc.
- **Thread-aware**: Tracks calls across multiple threads
- **Configurable filtering**: Include/exclude packages via config or environment

## Quick Start

### 1. Build the Agent

```bash
cd java-agent
./gradlew shadowJar
# Output: build/libs/trueflow-agent.jar
```

### 2. Run Your Application with the Agent

```bash
# Basic usage
java -javaagent:trueflow-agent.jar -jar your-app.jar

# With environment variable to enable
TRUEFLOW_ENABLED=1 java -javaagent:trueflow-agent.jar -jar your-app.jar

# With options
java -javaagent:trueflow-agent.jar=enabled=true,includes=com.myapp -jar your-app.jar
```

### 3. Connect IDE

The agent starts a socket server on port **5679** (different from Python's 5678).
Configure TrueFlow plugin to connect to `localhost:5679` for Java projects.

## Configuration

### Agent Arguments

Pass options after `=` in the javaagent path:

```bash
java -javaagent:trueflow-agent.jar=option1=value1,option2=value2 ...
```

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `false` | Enable tracing (or set `TRUEFLOW_ENABLED=1`) |
| `port` | `5679` | Socket server port |
| `host` | `127.0.0.1` | Socket server host |
| `includes` | (all) | Packages to instrument (semicolon-separated) |
| `excludes` | (JDK) | Packages to exclude (semicolon-separated) |
| `maxDepth` | `1000` | Maximum call stack depth |
| `maxCalls` | `100000` | Maximum total calls to track |
| `sampleRate` | `1` | Sample 1 in N calls (1 = all) |
| `traceDir` | `./.trueflow/traces` | Output directory for trace files |
| `socket` | `true` | Enable socket server |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TRUEFLOW_ENABLED=1` | Enable tracing |
| `TRUEFLOW_PORT` | Socket server port |
| `TRUEFLOW_HOST` | Socket server host |
| `TRUEFLOW_INCLUDES` | Packages to instrument (comma-separated) |
| `TRUEFLOW_EXCLUDES` | Packages to exclude (comma-separated) |
| `TRUEFLOW_TRACE_DIR` | Trace output directory |
| `TRUEFLOW_MAX_DEPTH` | Maximum call depth |
| `TRUEFLOW_MAX_CALLS` | Maximum calls to track |
| `TRUEFLOW_SAMPLE_RATE` | Sampling rate |

## Examples

### Spring Boot Application

```bash
# Trace only your app code
TRUEFLOW_ENABLED=1 java \
  -javaagent:trueflow-agent.jar=includes=com.mycompany.myapp \
  -jar my-spring-app.jar
```

### Gradle Run Task

```kotlin
// build.gradle.kts
tasks.named<JavaExec>("run") {
    jvmArgs = listOf(
        "-javaagent:${rootDir}/trueflow-agent.jar=enabled=true"
    )
}
```

### Maven Surefire

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>-javaagent:${project.basedir}/trueflow-agent.jar=enabled=true</argLine>
    </configuration>
</plugin>
```

### IntelliJ IDEA Run Configuration

1. Edit Run Configuration
2. Add VM options: `-javaagent:/path/to/trueflow-agent.jar=enabled=true`
3. Add environment: `TRUEFLOW_INCLUDES=com.myapp`

## Socket Protocol

The agent uses the same protocol as the Python instrumentor:
- **Newline-delimited JSON** on TCP port 5679
- Compatible with TrueFlow IDE plugins

### Event Types

**Call Event:**
```json
{
  "type": "call",
  "timestamp": 1234567890.123,
  "call_id": "call_42",
  "module": "com.myapp.service.UserService",
  "function": "getUser",
  "signature": "(Ljava/lang/Long;)Lcom/myapp/model/User;",
  "file": "UserService.java",
  "line": 0,
  "depth": 3,
  "parent_id": "call_41",
  "thread_id": 1,
  "thread_name": "main",
  "session_id": "session_20251201_120000",
  "process_id": 12345,
  "language": "java",
  "protocol": "SQL",
  "invocation_type": "INTERNAL"
}
```

**Return Event:**
```json
{
  "type": "return",
  "timestamp": 1234567890.456,
  "call_id": "call_42",
  "module": "com.myapp.service.UserService",
  "function": "getUser",
  "duration_ms": 15.5,
  "depth": 3,
  "parent_id": "call_41",
  "session_id": "session_20251201_120000",
  "language": "java"
}
```

## Protocol Detection

The agent automatically detects these protocols/patterns:

| Protocol | Detection Pattern |
|----------|-------------------|
| SQL | jdbc, datasource, connection, statement, hibernate, jpa |
| HTTP | httpclient, resttemplate, webclient, controller, servlet |
| gRPC | grpc, protobuf, stub |
| Kafka | kafka, producer, consumer |
| AMQP | rabbit, amqp |
| Redis | redis, jedis, lettuce |
| WebSocket | websocket, stomp |
| Async | completablefuture, reactive, flux, mono |

## Default Excludes

These packages are excluded by default:
- `java.`, `javax.`, `jdk.`, `sun.`, `com.sun.`
- `org.apache.logging.`, `org.slf4j.`, `ch.qos.logback.`
- `kotlin.`, `kotlinx.`, `scala.`, `groovy.`
- `org.objectweb.asm.` (ASM itself)
- `com.trueflow.agent.` (the agent itself)
- `org.gradle.`, `com.intellij.`, `org.jetbrains.`
- `org.junit.`, `org.testng.`, `org.mockito.`

## Troubleshooting

### Agent not loading
- Ensure `TRUEFLOW_ENABLED=1` is set or `enabled=true` is in agent args
- Check Java version (requires Java 11+)

### Too much noise in traces
- Add `includes=com.yourpackage` to only trace your code
- Increase `sampleRate` to reduce volume

### Performance impact
- Use `sampleRate=10` to trace only 1 in 10 calls
- Reduce `maxDepth` to limit deep recursion
- Exclude hot paths with `excludes`

### Socket connection fails
- Check if port 5679 is available
- Ensure firewall allows localhost connections
- Try different port with `port=5680`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Java Application                       │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              Your Code (instrumented)                │ │
│  │    onMethodEnter() ──────┐                          │ │
│  │         ...              │                          │ │
│  │    onMethodExit()  ◄─────┘                          │ │
│  └─────────────────────────────────────────────────────┘ │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│                  TrueFlow Java Agent                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │ ASM Bytecode│  │  Runtime    │  │  TraceSocket    │ │
│  │ Transformer │──▶ Instrumentor│──▶ Server (5679)   │ │
│  └─────────────┘  └─────────────┘  └───────┬─────────┘ │
└────────────────────────────────────────────┬───────────┘
                                             │ JSON/TCP
                                             ▼
┌─────────────────────────────────────────────────────────┐
│            TrueFlow IDE Plugin (PyCharm/VS Code)         │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌─────────┐ │
│  │ Call    │  │ Flame    │  │ Sequence  │  │ Manim   │ │
│  │ Tree    │  │ Graph    │  │ Diagram   │  │ Video   │ │
│  └─────────┘  └──────────┘  └───────────┘  └─────────┘ │
└─────────────────────────────────────────────────────────┘
```

## License

MIT License - Same as TrueFlow
