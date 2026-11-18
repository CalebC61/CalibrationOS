import { freshParams } from "./freshGet";

test("each read gets a new cache key and keeps the real query", () => {
  const first = freshParams();
  const second = freshParams({ date_str: "2026-11-17" });
  expect(String(first._)).not.toBe(String(second._));
  expect(second.date_str).toBe("2026-11-17");
});
