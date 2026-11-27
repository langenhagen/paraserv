/**
 * Speak pi's assistant replies with qtts.
 *
 * ppi.py loads this extension with `pi -e`. It speaks each finalized assistant
 * message with one qtts process, skipping thinking, tool calls, code blocks,
 * and markdown markers. Text deltas are not spoken as they arrive. The qtts
 * log is STATE_DIR/pi-tts.log.
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const voicePath = path.join(
    os.homedir(),
    "Dev/barn-claude-jarvis/voices/anna/reference.wav",
);
const qttsArgs = [
    "--temperature",
    "1.6",
    "--prebuffer",
    "0",
    "--voice",
    voicePath,
];
const runtimeDir = process.env.XDG_RUNTIME_DIR;
const stateDir = runtimeDir
    ? path.join(runtimeDir, "paraserv")
    : path.join(os.homedir(), ".cache", "paraserv");
const logPath = path.join(stateDir, "pi-tts.log");

function toProse(text) {
    return text
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
        .replace(/\*\*([^*]+)\*\*/g, "$1")
        .replace(/\*([^*]+)\*/g, "$1")
        .replace(/`/g, "")
        .replace(/^\s*(?:#{1,6}|[-*+]|\d+\.)\s+/, "")
        .trim();
}

export default function (pi) {
    let child = null;
    let inCodeBlock = false;
    let disabled = false;

    function log(message) {
        try {
            fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });
            fs.appendFileSync(logPath, `${message}\n`);
        } catch {
            // Logging must never interrupt the wrapper.
        }
    }

    function finish() {
        inCodeBlock = false;
        if (child !== null) {
            try {
                child.stdin.end();
            } catch {
                // The process may already have closed its stdin.
            }
            child = null;
        }
    }

    function start() {
        if (disabled || child !== null) return;
        try {
            fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });
            const logFd = fs.openSync(logPath, "a");
            const spawned = spawn("qtts", qttsArgs, {
                stdio: ["pipe", logFd, logFd],
            });
            fs.closeSync(logFd);
            child = spawned;
            spawned.on("error", (error) => {
                log(`cannot start qtts: ${error.message}`);
                if (child === spawned) {
                    disabled = true;
                    child = null;
                }
            });
        } catch (error) {
            log(`cannot start qtts: ${error.message}`);
            disabled = true;
        }
    }

    function speak(line) {
        if (inCodeBlock) return;
        const text = toProse(line);
        if (!text) return;
        start();
        if (child === null || child.stdin === null) return;
        try {
            child.stdin.write(`${text}\n`);
        } catch (error) {
            log(`qtts write failed: ${error.message}`);
            finish();
        }
    }

    function handleLine(line) {
        if (line.trimStart().startsWith("```")) {
            inCodeBlock = !inCodeBlock;
            return;
        }
        speak(line);
    }

    function speakFinalText(text) {
        for (const line of text.split(/\r?\n/)) {
            handleLine(line);
        }
    }

    pi.on("message_start", (event) => {
        if (event.message.role === "assistant") finish();
    });

    pi.on("message_end", (event) => {
        if (event.message.role !== "assistant") return;
        finish();
        const text = event.message.content
            .filter((block) => block.type === "text" && typeof block.text === "string")
            .map((block) => block.text)
            .join("\n");
        if (!text.trim()) return;
        log(`speaking final reply (${text.length} chars)`);
        speakFinalText(text);
        finish();
    });

    pi.on("session_shutdown", () => finish());
}
