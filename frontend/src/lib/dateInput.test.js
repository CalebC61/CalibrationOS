import { isIsoDate, normalizeDateText, readDateInput } from "./dateInput";

test("a calendar day is accepted and an impossible day is not", () => {
  expect(isIsoDate("2026-11-18")).toBe(true);
  expect(isIsoDate("2026-02-31")).toBe(false);
  expect(normalizeDateText("2026-11-18")).toBe("2026-11-18");
  expect(normalizeDateText("2026-11-18T00:00:00.000Z")).toBe("2026-11-18");
  expect(normalizeDateText("2026/11/18")).toBe("2026-11-18");
  expect(normalizeDateText("11/18/2026")).toBe("2026-11-18");
  expect(normalizeDateText("11-18-2026")).toBe("2026-11-18");
  expect(normalizeDateText("Invalid date")).toBe("");
  expect(normalizeDateText("")).toBe("");
});

test("a date input reports partial, empty, invalid, and picker values apart", () => {
  expect(readDateInput({ value: "2026-11-18", validity: {} })).toEqual({ kind: "valid", value: "2026-11-18" });
  expect(readDateInput({ value: "11/18/2026", validity: {} })).toEqual({ kind: "valid", value: "2026-11-18" });
  expect(readDateInput({
    value: "",
    validity: { badInput: true },
    valueAsDate: null,
  })).toEqual({ kind: "partial", value: "" });
  expect(readDateInput({ value: "", validity: { badInput: false }, valueAsDate: null })).toEqual({
    kind: "empty",
    value: "",
  });
  expect(readDateInput({ value: "Invalid date", validity: {}, valueAsDate: null })).toEqual({
    kind: "invalid",
    value: "",
  });
  const picked = new Date(Date.UTC(2026, 10, 18));
  expect(readDateInput({ value: "", validity: {}, valueAsDate: picked })).toEqual({
    kind: "valid",
    value: "2026-11-18",
  });
});
