// Decky transports Python exceptions as objects rather than JavaScript Errors.
export const getErrorMessage = (error: unknown, fallback: string): string => {
  const seen = new Set<unknown>();
  const read = (value: unknown, depth: number): string => {
    if (depth > 6 || value == null || seen.has(value)) return "";
    if (typeof value === "string") {
      const text = value.trim();
      if (!text) return "";
      if (text.startsWith("{")) {
        try { return read(JSON.parse(text), depth + 1) || text; } catch { /* plain text */ }
      }
      return text;
    }
    if (typeof value !== "object") return "";
    seen.add(value);
    const object = value as Record<string, unknown>;
    for (const key of ["python_message", "python_error", "python_exception", "message", "error", "cause", "details", "exception"]) {
      const message = read(object[key], depth + 1);
      if (message) return message;
    }
    for (const key of ["python_traceback", "traceback"]) {
      const trace = read(object[key], depth + 1);
      if (trace) return trace.split("\n").filter((line) => line.trim()).pop() || trace;
    }
    try {
      const serialized = JSON.stringify(value);
      return serialized === "{}" ? "" : serialized;
    } catch { return ""; }
  };
  return read(error, 0) || fallback;
};
