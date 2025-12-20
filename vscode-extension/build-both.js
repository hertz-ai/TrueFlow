#!/usr/bin/env node
/**
 * Build VSIX packages for both marketplaces:
 * - Open VSX: publisher "hevolve-ai"
 * - VS Marketplace: publisher "hertzai"
 *
 * Auto-increments version before building (like PyCharm plugin).
 * Use --no-increment to skip version increment.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const packageJsonPath = path.join(__dirname, 'package.json');
const gradlePropsPath = path.join(__dirname, '..', 'gradle.properties');

// Check for --no-increment flag
const noIncrement = process.argv.includes('--no-increment');

/**
 * Increment patch version (0.1.6 -> 0.1.7)
 */
function incrementVersion(version) {
    const parts = version.split('.');
    if (parts.length !== 3) {
        console.error(`[FAIL] Invalid version format: ${version}`);
        return version;
    }
    const [major, minor, patch] = parts;
    return `${major}.${minor}.${parseInt(patch) + 1}`;
}

/**
 * Update gradle.properties version to keep in sync
 */
function updateGradleProperties(newVersion) {
    if (!fs.existsSync(gradlePropsPath)) {
        console.log('[WARN] gradle.properties not found, skipping sync');
        return;
    }

    let content = fs.readFileSync(gradlePropsPath, 'utf8');
    const match = content.match(/pluginVersion = ([0-9]+\.[0-9]+\.[0-9]+)/);
    if (match) {
        const oldVersion = match[1];
        // Increment PyCharm version too
        const parts = oldVersion.split('.');
        const newPyCharmVersion = `${parts[0]}.${parts[1]}.${parseInt(parts[2]) + 1}`;
        content = content.replace(
            /pluginVersion = [0-9]+\.[0-9]+\.[0-9]+/,
            `pluginVersion = ${newPyCharmVersion}`
        );
        fs.writeFileSync(gradlePropsPath, content);
        console.log(`[OK] Updated gradle.properties: ${oldVersion} -> ${newPyCharmVersion}`);
    }
}

// Load package.json
let packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
let version = packageJson.version;

// Auto-increment version unless --no-increment
if (!noIncrement) {
    console.log('\n[1/4] Auto-incrementing version...');
    console.log('='.repeat(50));
    const oldVersion = version;
    version = incrementVersion(version);
    packageJson.version = version;
    console.log(`[OK] Updated package.json: ${oldVersion} -> ${version}`);
    updateGradleProperties(version);
} else {
    console.log('\n[1/4] Skipping version increment (--no-increment)');
    console.log('='.repeat(50));
}

console.log(`\nBuilding TrueFlow v${version} for both marketplaces...\n`);

// Build for Open VSX (hevolve-ai)
console.log('[2/4] Building for Open VSX (publisher: hevolve-ai)');
console.log('='.repeat(50));

packageJson.publisher = 'hevolve-ai';
fs.writeFileSync(packageJsonPath, JSON.stringify(packageJson, null, 2) + '\n');

try {
    execSync('npx vsce package --no-dependencies', { stdio: 'inherit', cwd: __dirname });
    const openVsxFile = `trueflow-${version}.vsix`;
    const openVsxTarget = `trueflow-openvsx-${version}.vsix`;
    if (fs.existsSync(path.join(__dirname, openVsxFile))) {
        fs.renameSync(
            path.join(__dirname, openVsxFile),
            path.join(__dirname, openVsxTarget)
        );
        console.log(`\n✓ Created: ${openVsxTarget}\n`);
    }
} catch (e) {
    console.error('Failed to build Open VSX package:', e.message);
}

// Build for VS Marketplace (hertzai)
console.log('[3/4] Building for VS Marketplace (publisher: hertzai)');
console.log('='.repeat(50));

packageJson.publisher = 'hertzai';
fs.writeFileSync(packageJsonPath, JSON.stringify(packageJson, null, 2) + '\n');

try {
    execSync('npx vsce package --no-dependencies', { stdio: 'inherit', cwd: __dirname });
    const vsmpFile = `trueflow-${version}.vsix`;
    const vsmpTarget = `trueflow-vsmarketplace-${version}.vsix`;
    if (fs.existsSync(path.join(__dirname, vsmpFile))) {
        fs.renameSync(
            path.join(__dirname, vsmpFile),
            path.join(__dirname, vsmpTarget)
        );
        console.log(`\n✓ Created: ${vsmpTarget}\n`);
    }
} catch (e) {
    console.error('Failed to build VS Marketplace package:', e.message);
}

// Restore original publisher (hevolve-ai for git)
console.log('[4/4] Restoring package.json for git');
console.log('='.repeat(50));
packageJson.publisher = 'hevolve-ai';
fs.writeFileSync(packageJsonPath, JSON.stringify(packageJson, null, 2) + '\n');

console.log('\n' + '='.repeat(50));
console.log('Build complete!');
console.log('='.repeat(50));
console.log(`\nOutput files:`);
console.log(`  Open VSX:        trueflow-openvsx-${version}.vsix`);
console.log(`  VS Marketplace:  trueflow-vsmarketplace-${version}.vsix`);
console.log(`\nTo publish:`);
console.log(`  Open VSX:        npx ovsx publish trueflow-openvsx-${version}.vsix -p <TOKEN>`);
console.log(`  VS Marketplace:  npx vsce publish --packagePath trueflow-vsmarketplace-${version}.vsix -p <TOKEN>`);
console.log('');
