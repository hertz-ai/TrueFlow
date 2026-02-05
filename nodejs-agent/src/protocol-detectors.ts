/**
 * Protocol and invocation type detection for Node.js functions.
 * Matches the Java agent's protocol detection for consistency.
 */

/**
 * Detect the protocol type based on module/function patterns.
 */
export function detectProtocol(modulePath: string, functionName: string): string | undefined {
    const lowerModule = modulePath.toLowerCase();
    const lowerFunc = functionName.toLowerCase();

    // HTTP/REST
    if (lowerModule.includes('express') ||
        lowerModule.includes('fastify') ||
        lowerModule.includes('koa') ||
        lowerModule.includes('hapi') ||
        lowerModule.includes('restify') ||
        lowerModule.includes('http') ||
        lowerModule.includes('https') ||
        lowerModule.includes('axios') ||
        lowerModule.includes('fetch') ||
        lowerModule.includes('got') ||
        lowerModule.includes('request') ||
        lowerModule.includes('superagent') ||
        lowerFunc.includes('get') ||
        lowerFunc.includes('post') ||
        lowerFunc.includes('put') ||
        lowerFunc.includes('delete') ||
        lowerFunc.includes('patch') ||
        lowerFunc.includes('request') ||
        lowerFunc.includes('fetch')) {
        return 'HTTP';
    }

    // SQL/Database
    if (lowerModule.includes('mysql') ||
        lowerModule.includes('postgres') ||
        lowerModule.includes('pg') ||
        lowerModule.includes('sqlite') ||
        lowerModule.includes('sequelize') ||
        lowerModule.includes('typeorm') ||
        lowerModule.includes('prisma') ||
        lowerModule.includes('knex') ||
        lowerModule.includes('mongoose') ||
        lowerModule.includes('mongodb') ||
        lowerFunc.includes('query') ||
        lowerFunc.includes('execute') ||
        lowerFunc.includes('findone') ||
        lowerFunc.includes('findmany') ||
        lowerFunc.includes('create') ||
        lowerFunc.includes('update') ||
        lowerFunc.includes('delete')) {
        return 'SQL';
    }

    // GraphQL
    if (lowerModule.includes('graphql') ||
        lowerModule.includes('apollo') ||
        lowerFunc.includes('resolver') ||
        lowerFunc.includes('mutation') ||
        lowerFunc.includes('subscription')) {
        return 'GraphQL';
    }

    // gRPC
    if (lowerModule.includes('grpc') ||
        lowerModule.includes('protobuf')) {
        return 'gRPC';
    }

    // WebSocket
    if (lowerModule.includes('socket.io') ||
        lowerModule.includes('ws') ||
        lowerModule.includes('websocket') ||
        lowerFunc.includes('emit') ||
        lowerFunc.includes('onmessage') ||
        lowerFunc.includes('broadcast')) {
        return 'WebSocket';
    }

    // Redis
    if (lowerModule.includes('redis') ||
        lowerModule.includes('ioredis')) {
        return 'Redis';
    }

    // Message Queues
    if (lowerModule.includes('amqp') ||
        lowerModule.includes('rabbitmq') ||
        lowerModule.includes('bull') ||
        lowerModule.includes('kafka') ||
        lowerModule.includes('sqs')) {
        return 'MessageQueue';
    }

    // File System
    if (lowerModule.includes('fs') ||
        lowerFunc.includes('readfile') ||
        lowerFunc.includes('writefile') ||
        lowerFunc.includes('readdir')) {
        return 'FileSystem';
    }

    // Child Process
    if (lowerModule.includes('child_process') ||
        lowerFunc.includes('spawn') ||
        lowerFunc.includes('exec')) {
        return 'Process';
    }

    // Async patterns
    if (lowerFunc.includes('promise') ||
        lowerFunc.includes('async') ||
        lowerFunc.includes('await') ||
        lowerFunc.includes('then') ||
        lowerFunc.includes('callback')) {
        return 'Async';
    }

    return undefined;
}

/**
 * Detect the invocation type (entry point, handler, etc.)
 */
export function detectInvocationType(modulePath: string, functionName: string): string | undefined {
    const lowerModule = modulePath.toLowerCase();
    const lowerFunc = functionName.toLowerCase();

    // API entry points (Express/Fastify/Koa routes)
    if (lowerModule.includes('controller') ||
        lowerModule.includes('router') ||
        lowerModule.includes('route') ||
        lowerModule.includes('endpoint') ||
        lowerModule.includes('api')) {
        return 'API_ENTRY';
    }

    // NestJS controllers/resolvers
    if (lowerModule.includes('controller') ||
        lowerModule.includes('resolver') ||
        lowerModule.includes('gateway')) {
        return 'API_ENTRY';
    }

    // Event handlers
    if (lowerFunc.includes('handle') ||
        lowerFunc.includes('process') ||
        lowerFunc.startsWith('on') ||
        lowerFunc.includes('listener') ||
        lowerFunc.includes('subscriber') ||
        lowerFunc.includes('consumer')) {
        return 'EVENT_HANDLER';
    }

    // Middleware
    if (lowerModule.includes('middleware') ||
        lowerFunc.includes('middleware') ||
        lowerFunc.includes('guard') ||
        lowerFunc.includes('interceptor') ||
        lowerFunc.includes('pipe')) {
        return 'MIDDLEWARE';
    }

    // Scheduled tasks
    if (lowerModule.includes('cron') ||
        lowerModule.includes('schedule') ||
        lowerModule.includes('job') ||
        lowerFunc.includes('schedule') ||
        lowerFunc.includes('cron')) {
        return 'SCHEDULED';
    }

    // Callbacks
    if (lowerFunc.includes('callback') ||
        lowerFunc.includes('complete') ||
        lowerFunc.includes('done') ||
        lowerFunc.includes('success') ||
        lowerFunc.includes('error')) {
        return 'CALLBACK';
    }

    // Service layer
    if (lowerModule.includes('service') ||
        lowerModule.includes('provider')) {
        return 'SERVICE';
    }

    // Repository/DAO layer
    if (lowerModule.includes('repository') ||
        lowerModule.includes('dao') ||
        lowerModule.includes('store')) {
        return 'REPOSITORY';
    }

    return 'INTERNAL';
}

/**
 * Detect framework from module patterns.
 */
export function detectFramework(modulePath: string): string | undefined {
    const lowerModule = modulePath.toLowerCase();

    if (lowerModule.includes('express')) return 'Express';
    if (lowerModule.includes('fastify')) return 'Fastify';
    if (lowerModule.includes('nestjs') || lowerModule.includes('@nestjs')) return 'NestJS';
    if (lowerModule.includes('koa')) return 'Koa';
    if (lowerModule.includes('hapi')) return 'Hapi';
    if (lowerModule.includes('next')) return 'Next.js';
    if (lowerModule.includes('nuxt')) return 'Nuxt';
    if (lowerModule.includes('remix')) return 'Remix';
    if (lowerModule.includes('sveltekit')) return 'SvelteKit';

    return undefined;
}
