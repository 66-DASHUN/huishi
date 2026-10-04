const REDACTED = "[redacted]";

const URL_PATTERN = /https?:\/\/[^\s<>'")]+/gi;
const SECRET_TOKEN_PATTERN = /\b(?:sk|sess|key|token|secret|bearer)[-_A-Za-z0-9]{8,}\b/gi;

function redactUrl(value: string) {
    try {
        const url = new URL(value);
        return `${url.protocol}//${url.host}${url.pathname}`;
    } catch {
        return "[redacted-url]";
    }
}

export function redactSensitiveText(value: unknown, secrets: unknown[] = []) {
    let text = String(value ?? "");
    for (const secret of secrets) {
        const secretText = String(secret ?? "");
        if (secretText) text = text.replaceAll(secretText, REDACTED);
    }

    text = text.replace(URL_PATTERN, (match) => redactUrl(match));
    text = text.replace(/\b(Bearer\s+)[^\s,;]+/gi, `$1${REDACTED}`);
    text = text.replace(/(\b(?:api[_-]?key|token|secret|key|password)\b\s*["']?\s*[:=]\s*["']?)([^"',&\s}]+)/gi, `$1${REDACTED}`);
    text = text.replace(/\b(api\s*key|token|secret|password)\s+(?:is\s+)?([A-Za-z0-9._-]{8,})/gi, `$1 ${REDACTED}`);
    return text.replace(SECRET_TOKEN_PATTERN, REDACTED);
}

export function redactSensitiveErrorMessage(value: unknown, fallback: string) {
    const text = typeof value === "string" && value.trim() ? value : fallback;
    return redactSensitiveText(text) || fallback;
}
