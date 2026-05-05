const SOFT_PHONE_ERROR = "Укажи номер в формате +7 (999) 123-45-67, и я сразу отправлю код.";

function phoneDigits(rawPhone: string) {
  return (rawPhone || "").replace(/\D+/g, "");
}

function canonicalDigits(rawPhone: string) {
  let digits = phoneDigits(rawPhone);
  if (!digits) return "";

  if (digits.length === 11 && digits.startsWith("8")) {
    digits = `7${digits.slice(1)}`;
  } else if (digits.length === 11 && digits.startsWith("7")) {
    digits = digits;
  } else if (digits.length === 10) {
    digits = `7${digits.slice(0, 10)}`;
  } else {
    return "";
  }

  if (digits.length !== 11 || !digits.startsWith("7")) {
    return "";
  }

  return digits;
}

export function normalizeRussianPhone(rawPhone: string) {
  const digits = canonicalDigits(rawPhone);
  if (!digits) return null;
  return `+${digits}`;
}

export function formatRussianPhone(rawPhone: string) {
  const normalized = normalizeRussianPhone(rawPhone);
  if (!normalized) return (rawPhone || "").trim();

  const local = normalized.slice(2, 12);
  const area = local.slice(0, 3);
  const first = local.slice(3, 6);
  const second = local.slice(6, 8);
  const third = local.slice(8, 10);

  let formatted = "+7";
  if (area) {
    formatted += ` (${area}`;
  }
  if (area.length === 3) {
    formatted += ")";
  }
  if (first) {
    formatted += `${area.length === 3 ? " " : ""}${first}`;
  }
  if (second) {
    formatted += `-${second}`;
  }
  if (third) {
    formatted += `-${third}`;
  }

  return formatted;
}

export function validateRussianPhone(rawPhone: string) {
  const normalized = normalizeRussianPhone(rawPhone);
  if (!normalized) {
    return { normalized: null, error: SOFT_PHONE_ERROR };
  }
  return { normalized, error: null };
}
