import { describe, expect, it } from "vitest";

import { validateAccountId, validateAmount, validateDays } from "./demoValidation";

describe("validateDays (ClockAdvanceRequest.days: 1 to 365)", () => {
  it.each(["1", "30", "365", " 7 "])("accepts %j", (raw) => {
    expect(validateDays(raw)).toEqual({ ok: true, value: Number(raw.trim()) });
  });

  it.each(["", "0", "366", "-1", "1.5", "abc", "1e2", "1 2"])("rejects %j", (raw) => {
    const result = validateDays(raw);
    expect(result.ok).toBe(false);
    expect(result).toMatchObject({ message: "Enter a whole number of days from 1 to 365." });
  });
});

describe("validateAccountId", () => {
  it.each(["acc_000123", "acc_1", " acc_000123 "])("accepts %j", (raw) => {
    expect(validateAccountId(raw)).toEqual({ ok: true, value: raw.trim() });
  });

  it.each(["", "000123", "cus_000123", "acc_", "acc 000123", "acc_00-1"])("rejects %j", (raw) => {
    expect(validateAccountId(raw).ok).toBe(false);
  });
});

describe("validateAmount (a decimal string, never a number)", () => {
  it.each(["50", "50.5", "50.00", "0.01", " 1200.25 "])("accepts %j and returns the string", (raw) => {
    expect(validateAmount(raw)).toEqual({ ok: true, value: raw.trim() });
  });

  it("returns the amount as a string, never a number", () => {
    const result = validateAmount("50.10");
    expect(result.ok && typeof result.value).toBe("string");
    expect(result.ok && result.value).toBe("50.10");
  });

  it.each([
    ["-5", "Amount cannot be negative."],
    ["abc", "Enter an amount as a decimal number, for example 50.00."],
    ["", "Enter an amount as a decimal number, for example 50.00."],
    ["5.", "Enter an amount as a decimal number, for example 50.00."],
    ["1.234", "Use at most 2 decimal places."],
    ["0", "Amount must be greater than 0.00."],
    ["0.00", "Amount must be greater than 0.00."],
  ])("rejects %j with a specific message", (raw, message) => {
    expect(validateAmount(raw)).toEqual({ ok: false, message });
  });
});
