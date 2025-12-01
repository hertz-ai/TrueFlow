package com.trueflow.agent;

import org.objectweb.asm.*;
import org.objectweb.asm.commons.AdviceAdapter;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.logging.Logger;

/**
 * ASM-based class transformer that instruments methods for tracing.
 * Injects entry/exit hooks into method bytecode.
 */
public class TracingClassTransformer implements ClassFileTransformer {
    private static final Logger LOGGER = Logger.getLogger(TracingClassTransformer.class.getName());

    private final RuntimeInstrumentor instrumentor;
    private final AgentConfig config;

    public TracingClassTransformer(RuntimeInstrumentor instrumentor, AgentConfig config) {
        this.instrumentor = instrumentor;
        this.config = config;
    }

    @Override
    public byte[] transform(ClassLoader loader, String className, Class<?> classBeingRedefined,
                            ProtectionDomain protectionDomain, byte[] classfileBuffer) {

        // Skip if null or shouldn't instrument
        if (className == null) return null;

        // Convert internal name to package format for filtering
        String packageName = className.replace('/', '.');

        if (!config.shouldInstrument(packageName)) {
            return null;  // Return null means no transformation
        }

        try {
            ClassReader reader = new ClassReader(classfileBuffer);
            ClassWriter writer = new ClassWriter(reader, ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
            ClassVisitor visitor = new TracingClassVisitor(writer, className);

            reader.accept(visitor, ClassReader.EXPAND_FRAMES);
            return writer.toByteArray();

        } catch (Exception e) {
            LOGGER.fine("[TrueFlow] Failed to transform class " + className + ": " + e.getMessage());
            return null;  // Return original bytecode on error
        }
    }

    /**
     * Class visitor that wraps methods with tracing.
     */
    private class TracingClassVisitor extends ClassVisitor {
        private final String className;
        private String sourceFile = "Unknown";

        public TracingClassVisitor(ClassWriter writer, String className) {
            super(Opcodes.ASM9, writer);
            this.className = className;
        }

        @Override
        public void visitSource(String source, String debug) {
            this.sourceFile = source != null ? source : "Unknown";
            super.visitSource(source, debug);
        }

        @Override
        public MethodVisitor visitMethod(int access, String name, String descriptor,
                                         String signature, String[] exceptions) {
            MethodVisitor mv = super.visitMethod(access, name, descriptor, signature, exceptions);

            // Skip constructors, static initializers, and synthetic methods
            if (name.equals("<init>") || name.equals("<clinit>") ||
                    (access & Opcodes.ACC_SYNTHETIC) != 0 ||
                    (access & Opcodes.ACC_BRIDGE) != 0) {
                return mv;
            }

            // Skip abstract and native methods
            if ((access & Opcodes.ACC_ABSTRACT) != 0 || (access & Opcodes.ACC_NATIVE) != 0) {
                return mv;
            }

            return new TracingMethodAdapter(mv, access, name, descriptor, className, sourceFile);
        }
    }

    /**
     * Method adapter that injects entry/exit tracing code.
     */
    private class TracingMethodAdapter extends AdviceAdapter {
        private final String className;
        private final String methodName;
        private final String descriptor;
        private final String sourceFile;
        private int callIdLocal = -1;
        private Label tryStart = new Label();
        private Label tryEnd = new Label();
        private Label catchHandler = new Label();

        protected TracingMethodAdapter(MethodVisitor mv, int access, String name,
                                        String descriptor, String className, String sourceFile) {
            super(Opcodes.ASM9, mv, access, name, descriptor);
            this.className = className.replace('/', '.');
            this.methodName = name;
            this.descriptor = descriptor;
            this.sourceFile = sourceFile;
        }

        @Override
        protected void onMethodEnter() {
            // Allocate local variable for callId
            callIdLocal = newLocal(Type.getType(String.class));

            // Call RuntimeInstrumentor.onMethodEnter(className, methodName, descriptor, sourceFile, lineNumber)
            // Get instrumentor instance
            mv.visitMethodInsn(INVOKESTATIC, "com/trueflow/agent/TrueFlowAgent", "getInstrumentor",
                    "()Lcom/trueflow/agent/RuntimeInstrumentor;", false);

            // Check if instrumentor is null
            mv.visitInsn(DUP);
            Label notNull = new Label();
            mv.visitJumpInsn(IFNONNULL, notNull);
            mv.visitInsn(POP);
            mv.visitInsn(ACONST_NULL);
            mv.visitVarInsn(ASTORE, callIdLocal);
            Label skipCall = new Label();
            mv.visitJumpInsn(GOTO, skipCall);

            mv.visitLabel(notNull);

            // Push arguments
            mv.visitLdcInsn(className);
            mv.visitLdcInsn(methodName);
            mv.visitLdcInsn(descriptor);
            mv.visitLdcInsn(sourceFile);
            mv.visitLdcInsn(0);  // Line number (we don't have exact line in bytecode)

            // Call onMethodEnter
            mv.visitMethodInsn(INVOKEVIRTUAL, "com/trueflow/agent/RuntimeInstrumentor", "onMethodEnter",
                    "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;I)Ljava/lang/String;", false);
            mv.visitVarInsn(ASTORE, callIdLocal);

            mv.visitLabel(skipCall);

            // Start try block
            mv.visitLabel(tryStart);
        }

        @Override
        protected void onMethodExit(int opcode) {
            // Only handle normal returns (RETURN, IRETURN, etc.), not ATHROW
            if (opcode != ATHROW) {
                // Call RuntimeInstrumentor.onMethodExit(callId)
                mv.visitMethodInsn(INVOKESTATIC, "com/trueflow/agent/TrueFlowAgent", "getInstrumentor",
                        "()Lcom/trueflow/agent/RuntimeInstrumentor;", false);

                Label skipExit = new Label();
                mv.visitInsn(DUP);
                mv.visitJumpInsn(IFNULL, skipExit);

                mv.visitVarInsn(ALOAD, callIdLocal);
                mv.visitMethodInsn(INVOKEVIRTUAL, "com/trueflow/agent/RuntimeInstrumentor", "onMethodExit",
                        "(Ljava/lang/String;)V", false);
                Label afterExit = new Label();
                mv.visitJumpInsn(GOTO, afterExit);

                mv.visitLabel(skipExit);
                mv.visitInsn(POP);

                mv.visitLabel(afterExit);
            }
        }

        @Override
        public void visitMaxs(int maxStack, int maxLocals) {
            // End try block and add catch handler
            mv.visitLabel(tryEnd);
            mv.visitLabel(catchHandler);

            // Exception is on stack, store it temporarily
            int exceptionLocal = newLocal(Type.getType(Throwable.class));
            mv.visitVarInsn(ASTORE, exceptionLocal);

            // Call RuntimeInstrumentor.onMethodException(callId, exceptionClass, message)
            mv.visitMethodInsn(INVOKESTATIC, "com/trueflow/agent/TrueFlowAgent", "getInstrumentor",
                    "()Lcom/trueflow/agent/RuntimeInstrumentor;", false);

            Label skipException = new Label();
            mv.visitInsn(DUP);
            mv.visitJumpInsn(IFNULL, skipException);

            mv.visitVarInsn(ALOAD, callIdLocal);
            mv.visitVarInsn(ALOAD, exceptionLocal);
            mv.visitMethodInsn(INVOKEVIRTUAL, "java/lang/Object", "getClass", "()Ljava/lang/Class;", false);
            mv.visitMethodInsn(INVOKEVIRTUAL, "java/lang/Class", "getName", "()Ljava/lang/String;", false);
            mv.visitVarInsn(ALOAD, exceptionLocal);
            mv.visitMethodInsn(INVOKEVIRTUAL, "java/lang/Throwable", "getMessage", "()Ljava/lang/String;", false);
            mv.visitMethodInsn(INVOKEVIRTUAL, "com/trueflow/agent/RuntimeInstrumentor", "onMethodException",
                    "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V", false);

            Label afterException = new Label();
            mv.visitJumpInsn(GOTO, afterException);

            mv.visitLabel(skipException);
            mv.visitInsn(POP);

            mv.visitLabel(afterException);

            // Re-throw the exception
            mv.visitVarInsn(ALOAD, exceptionLocal);
            mv.visitInsn(ATHROW);

            // Add exception table entry
            mv.visitTryCatchBlock(tryStart, tryEnd, catchHandler, "java/lang/Throwable");

            super.visitMaxs(maxStack + 6, maxLocals + 2);
        }
    }
}
