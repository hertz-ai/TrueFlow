/**
 * Example Express.js app for testing TrueFlow Node.js agent.
 *
 * Run with:
 *   cd nodejs-agent
 *   npm install
 *   npm run build
 *   TRUEFLOW_ENABLED=1 node --require ./dist/index.js examples/express-app.js
 *
 * Then in PyCharm/IDE, the TrueFlow panel will show live traces.
 */

const express = require('express');

const app = express();
app.use(express.json());

// Simulated database
const users = [
    { id: 1, name: 'Alice', email: 'alice@example.com' },
    { id: 2, name: 'Bob', email: 'bob@example.com' },
    { id: 3, name: 'Charlie', email: 'charlie@example.com' }
];

// Service layer
function findUserById(id) {
    return users.find(u => u.id === id);
}

function findAllUsers() {
    return users;
}

async function processUser(user) {
    // Simulate async processing
    await new Promise(resolve => setTimeout(resolve, 10));
    return {
        ...user,
        processed: true,
        timestamp: Date.now()
    };
}

async function validateEmail(email) {
    // Simulate email validation
    await new Promise(resolve => setTimeout(resolve, 5));
    return email.includes('@');
}

// Routes
app.get('/', (req, res) => {
    res.json({ message: 'TrueFlow Express Example', version: '1.0.0' });
});

app.get('/users', async (req, res) => {
    const allUsers = findAllUsers();
    const processed = await Promise.all(allUsers.map(processUser));
    res.json(processed);
});

app.get('/users/:id', async (req, res) => {
    const id = parseInt(req.params.id);
    const user = findUserById(id);

    if (!user) {
        return res.status(404).json({ error: 'User not found' });
    }

    const processed = await processUser(user);
    res.json(processed);
});

app.post('/users', async (req, res) => {
    const { name, email } = req.body;

    // Validate
    if (!name || !email) {
        return res.status(400).json({ error: 'Name and email required' });
    }

    const isValidEmail = await validateEmail(email);
    if (!isValidEmail) {
        return res.status(400).json({ error: 'Invalid email format' });
    }

    // Create user
    const newUser = {
        id: users.length + 1,
        name,
        email
    };
    users.push(newUser);

    const processed = await processUser(newUser);
    res.status(201).json(processed);
});

// Error handler
app.use((err, req, res, next) => {
    console.error('[Error]', err.message);
    res.status(500).json({ error: 'Internal server error' });
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Express app listening on http://localhost:${PORT}`);
    console.log('Try these endpoints:');
    console.log(`  GET  http://localhost:${PORT}/`);
    console.log(`  GET  http://localhost:${PORT}/users`);
    console.log(`  GET  http://localhost:${PORT}/users/1`);
    console.log(`  POST http://localhost:${PORT}/users`);
});
