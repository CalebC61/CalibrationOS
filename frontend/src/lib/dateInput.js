const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_PREFIX = /^(\d{4}-\d{2}-\d{2})(?:$|[T\s])/;
const YMD = /^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/;
const MDY = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/;

function pad(value) {
  return String(value).padStart(2, "0");
}

export function isIsoDate(value) {
  const match = ISO_DAY.exec(String(value || ""));
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const check = new Date(Date.UTC(year, month - 1, day));
  return check.getUTCFullYear() === year
    && check.getUTCMonth() === month - 1
    && check.getUTCDate() === day;
}

function fromParts(year, month, day) {
  const value = `${year}-${pad(month)}-${pad(day)}`;
  return isIsoDate(value) ? value : "";
}

/** A complete calendar day, or "" when the text is partial or not a date. */
export function normalizeDateText(raw) {
  const text = String(raw ?? "").trim();
  if (!text || /^invalid date$/i.test(text)) return "";
  if (isIsoDate(text)) return text;
  const prefixed = ISO_PREFIX.exec(text);
  if (prefixed && isIsoDate(prefixed[1])) return prefixed[1];
  const ymd = YMD.exec(text);
  if (ymd) return fromParts(ymd[1], ymd[2], ymd[3]);
  const mdy = MDY.exec(text);
  if (mdy) return fromParts(mdy[3], mdy[1], mdy[2]);
  return "";
}

function dateFromValueAsDate(input) {
  if (!input) return "";
  try {
    const asDate = input.valueAsDate;
    if (!(asDate instanceof Date) || Number.isNaN(asDate.getTime())) return "";
    return fromParts(asDate.getUTCFullYear(), asDate.getUTCMonth() + 1, asDate.getUTCDate());
  } catch {
    return "";
  }
}

/**
 * Read a date input without treating a partial edit as a cleared or illegal day.
 * valid: commit YYYY-MM-DD. empty: the field was cleared. partial: still typing.
 * invalid: the control is holding text that is not a day (do not ask the server).
 */
export function readDateInput(input) {
  if (!input) return { kind: "invalid", value: "" };
  const raw = String(input.value ?? "");
  const fromText = normalizeDateText(raw);
  if (fromText) return { kind: "valid", value: fromText };
  const fromPicker = dateFromValueAsDate(input);
  if (fromPicker) return { kind: "valid", value: fromPicker };
  if (input.validity && input.validity.badInput) return { kind: "partial", value: "" };
  if (raw.trim() === "") return { kind: "empty", value: "" };
  return { kind: "invalid", value: "" };
}

/** Set the value through the prototype so React's tracker stays in step. */
export function writeDateInputValue(input, next) {
  if (!input) return;
  const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
  if (descriptor && typeof descriptor.set === "function") descriptor.set.call(input, next);
  else input.value = next;
}
