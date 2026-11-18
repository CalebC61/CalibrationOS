import { fresherJob } from "./jobState";

test("a newer unpaid list does not hide a charge that already succeeded", () => {
  const paid = {
    id: "job-1",
    status: "complete",
    payment_status: "paid",
    invoice_status: "paid",
    charged_at: "2026-11-18T16:05:00Z",
    charged_amount: 185,
    updated_at: "2026-11-18T16:05:00Z",
  };
  const laterUnpaid = {
    ...paid,
    payment_status: "unpaid",
    invoice_status: "open",
    charged_at: null,
    charged_amount: null,
    updated_at: "2026-11-18T16:06:00Z",
  };
  const kept = fresherJob(paid, laterUnpaid);
  expect(kept.payment_status).toBe("paid");
  expect(kept.charged_amount).toBe(185);
  expect(kept.charged_at).toBe("2026-11-18T16:05:00Z");
});

test("a later failed charge replaces a paid snapshot", () => {
  const paid = {
    id: "job-1",
    payment_status: "paid",
    charged_at: "2026-11-18T16:05:00Z",
    charged_amount: 125,
    updated_at: "2026-11-18T16:05:00Z",
  };
  const failed = {
    id: "job-1",
    payment_status: "payment_failed",
    charged_at: null,
    charge_error: "Card declined.",
    updated_at: "2026-11-18T16:07:00Z",
  };
  expect(fresherJob(paid, failed).payment_status).toBe("payment_failed");
});
