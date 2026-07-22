#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');

function installBrowserShims(engineRequire) {
    require.extensions['.css'] = () => {};
    const { JSDOM } = engineRequire('jsdom');
    const dom = new JSDOM('<!doctype html><html><body></body></html>', {
        url: 'http://localhost',
    });
    for (const name of [
        'Blob',
        'CustomEvent',
        'Element',
        'HTMLElement',
        'MutationObserver',
        'Node',
        'document',
        'getComputedStyle',
        'navigator',
        'window',
    ]) {
        Object.defineProperty(global, name, {
            value: dom.window[name],
            writable: true,
            configurable: true,
        });
    }
    global.devicePixelRatio = 1;
    global.ResizeObserver = class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
    };
    const matchMedia = () => ({
        matches: false,
        media: '',
        onchange: null,
        addListener() {},
        removeListener() {},
        addEventListener() {},
        removeEventListener() {},
        dispatchEvent() {
            return false;
        },
    });
    global.matchMedia = matchMedia;
    dom.window.matchMedia = matchMedia;
    dom.window.URL.createObjectURL = () => 'blob:splunk-schema-builder';
    Object.defineProperty(global, 'URL', {
        value: dom.window.URL,
        writable: true,
        configurable: true,
    });
    dom.window.ace = {
        config: {
            loadModule(_name, callback) {
                callback({});
            },
        },
        edit() {
            return {};
        },
        require() {
            return {};
        },
    };
    return dom;
}

function main() {
    if (process.argv.length < 4) {
        throw new Error('usage: build-schema.cjs ENGINE_DIRECTORY OUTPUT_PATH');
    }
    const engineDirectory = path.resolve(process.argv[2]);
    const outputPath = path.resolve(process.argv[3]);
    const engineRequire = createRequire(path.join(engineDirectory, 'package.json'));
    const dom = installBrowserShims(engineRequire);
    const { createSchemaBasedOnPresets } = engineRequire('@splunk/dashboard-definition');
    const enterprisePreset = engineRequire('@splunk/dashboard-presets/EnterprisePreset').default;
    const schema = createSchemaBasedOnPresets(enterprisePreset);
    fs.writeFileSync(outputPath, `${JSON.stringify(schema)}\n`, 'utf8');
    fs.writeSync(
        1,
        `${JSON.stringify({
            status: 'ok',
            schemaId: schema.$id || null,
            output: outputPath,
            dashboardDefinition: engineRequire(
                '@splunk/dashboard-definition/package.json'
            ).version,
            dashboardPresets: engineRequire('@splunk/dashboard-presets/package.json').version,
        })}\n`
    );
    dom.window.close();
    process.exit(0);
}

try {
    main();
} catch (error) {
    fs.writeSync(
        2,
        `${JSON.stringify({
            status: 'error',
            phase: 'schema',
            message: error instanceof Error ? error.message : String(error),
        })}\n`
    );
    process.exit(2);
}
