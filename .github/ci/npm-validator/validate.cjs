#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const { createRequire } = require('node:module');

function normalizeEngineIssue(issue) {
    return {
        source: 'splunk-dashboard-validation',
        path: issue.instancePath || issue.dataPath || '/',
        schemaPath: issue.schemaPath || null,
        keyword: issue.keyword || null,
        message: issue.message || String(issue),
    };
}

function createDosValidator(engineRequire) {
    const { DslParser } = engineRequire('@splunk/visualization-encoding/DslParser');
    const EncodingParser = engineRequire(
        '@splunk/visualization-encoding/EncodingParser'
    ).default;
    const { DataFrame } = engineRequire('@splunk/visualization-encoding/DataFrame');
    const { DataSeries } = engineRequire('@splunk/visualization-encoding/DataSeries');
    const { DataPoint } = engineRequire('@splunk/visualization-encoding/DataPoint');
    const { formatterClasses } = engineRequire(
        '@splunk/visualization-encoding/FormatterPresets'
    );
    const allowedMethods = new Set([
        ...Object.getOwnPropertyNames(DataFrame.prototype),
        ...Object.getOwnPropertyNames(DataSeries.prototype),
        ...Object.getOwnPropertyNames(DataPoint.prototype),
        ...Object.keys(formatterClasses),
    ]);
    allowedMethods.delete('constructor');

    function validateDosTree(value, jsonPath, issues) {
        if (typeof value === 'string' && value.trimStart().startsWith('>')) {
            try {
                const ast = DslParser.parse(EncodingParser.withoutArrow(value));
                for (const expression of ast) {
                    if (expression.type === 'method' && !allowedMethods.has(expression.name)) {
                        issues.push({
                            source: 'splunk-dos',
                            path: jsonPath,
                            schemaPath: null,
                            keyword: 'unknownFunction',
                            message: `Unknown Dashboard Studio DOS function: ${expression.name}`,
                        });
                    }
                }
            } catch (error) {
                issues.push({
                    source: 'splunk-dos',
                    path: jsonPath,
                    schemaPath: null,
                    keyword: 'syntax',
                    message: error instanceof Error ? error.message : String(error),
                });
            }
            return;
        }
        if (Array.isArray(value)) {
            value.forEach((item, index) =>
                validateDosTree(item, `${jsonPath}/${index}`, issues)
            );
            return;
        }
        if (value && typeof value === 'object') {
            for (const [key, child] of Object.entries(value)) {
                const escaped = key.replaceAll('~', '~0').replaceAll('/', '~1');
                validateDosTree(child, `${jsonPath}/${escaped}`, issues);
            }
        }
    }
    return validateDosTree;
}

function createValidator(engineDirectory, schemaPath) {
    const engineRequire = createRequire(path.join(engineDirectory, 'package.json'));
    const { DashboardValidator } = engineRequire('@splunk/dashboard-validation');
    const schema = JSON.parse(fs.readFileSync(schemaPath, 'utf8'));
    const validator = new DashboardValidator();
    const engineWarnings = [];
    const originalWarn = console.warn;
    console.warn = (...parts) => engineWarnings.push(parts.map(String).join(' '));
    try {
        const setupError = validator.setSchema(schema);
        if (setupError) {
            throw setupError;
        }
    } finally {
        console.warn = originalWarn;
    }
    const validateDosTree = createDosValidator(engineRequire);
    const engine = {
        dashboardValidation: engineRequire('@splunk/dashboard-validation/package.json').version,
        visualizationEncoding: engineRequire(
            '@splunk/visualization-encoding/package.json'
        ).version,
        schemaId: schema.$id || null,
    };

    return (request) => {
        const definition = request.definition || request;
        const engineIssues = (validator.validate(definition) || []).map(normalizeEngineIssue);
        const dosIssues = [];
        for (const [id, visualization] of Object.entries(
            definition.visualizations || {}
        )) {
            validateDosTree(
                visualization.options || {},
                `/visualizations/${id}/options`,
                dosIssues
            );
        }
        for (const [id, input] of Object.entries(definition.inputs || {})) {
            validateDosTree(input.options || {}, `/inputs/${id}/options`, dosIssues);
        }
        validateDosTree(
            (definition.defaults && definition.defaults.visualizations) || {},
            '/defaults/visualizations',
            dosIssues
        );
        const issues = [...engineIssues, ...dosIssues];
        return {
            protocolVersion: '1',
            caseId: request.case_id || null,
            status: issues.length ? 'invalid' : 'valid',
            issues,
            warnings: engineWarnings,
            engine,
        };
    };
}

async function main() {
    if (process.argv.length < 4) {
        throw new Error('usage: validate.cjs ENGINE_DIRECTORY SCHEMA_PATH');
    }
    const engineDirectory = path.resolve(process.argv[2]);
    const schemaPath = path.resolve(process.argv[3]);
    const validate = createValidator(engineDirectory, schemaPath);
    const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
    for await (const line of lines) {
        if (!line.trim()) {
            continue;
        }
        try {
            fs.writeSync(1, `${JSON.stringify(validate(JSON.parse(line)))}\n`);
        } catch (error) {
            fs.writeSync(
                1,
                `${JSON.stringify({
                    protocolVersion: '1',
                    status: 'error',
                    issues: [
                        {
                            source: 'bridge',
                            path: '/',
                            schemaPath: null,
                            keyword: 'runtime',
                            message: error instanceof Error ? error.message : String(error),
                        },
                    ],
                })}\n`
            );
            process.exitCode = 2;
        }
    }
    process.exit(process.exitCode || 0);
}

main().catch((error) => {
    fs.writeSync(
        2,
        `${JSON.stringify({
            status: 'error',
            phase: 'validator',
            message: error instanceof Error ? error.message : String(error),
        })}\n`
    );
    process.exit(2);
});
