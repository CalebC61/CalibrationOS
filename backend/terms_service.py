"""Terms & Agreement versioning.

Each version is immutable; published versions are stored in the `terms_versions`
collection. The current version is the highest version_number flagged `is_current`.
"""
from __future__ import annotations

# v1.0 — drafted Feb 2026, modernized from the dated paper T&A.
# Replace this string when publishing v2; the seed function will insert a new
# version row only if the version_number is new.
TERMS_V1_VERSION = "1.0"
TERMS_V1_EFFECTIVE_DATE = "2026-02-11"
TERMS_V1_TEXT = """\
THE CALIBRATION CREW — SHOP PARTNER TERMS & AGREEMENT
Version 1.0 — Effective February 11, 2026

This Agreement is entered into between The Calibration Crew LLC, an Arizona limited
liability company ("TCC"), and the auto glass shop identified on the registration
form ("Shop"). By creating an account, signing electronically, and saving a payment
method on file, Shop accepts and is legally bound by these Terms.

1. SERVICES PROVIDED
   TCC provides mobile Advanced Driver-Assistance System (ADAS) calibration services
   to vehicles referred by Shop following windshield replacement, including but not
   limited to Static, Dynamic, Dual, Triple-Camera/Subaru, and Tesla calibrations.
   Shop authorizes TCC to operate the referred vehicle on streets, highways, and any
   route necessary to perform a successful calibration, test drive, road verification,
   or inspection. Shop releases TCC from liability for loss or damage to the vehicle
   or for any articles left in or removed from the vehicle (including without
   limitation loss caused by fire, theft, weather, or any other cause beyond TCC's
   reasonable control).

2. ACCOUNT & ACCESS
   2.1  Shop must complete all three onboarding steps — Business Information,
        electronic signature of these Terms, and saving a valid payment method on
        file — before any calibration may be scheduled. Accounts remain in a
        "pending" status until all three steps are complete.
   2.2  Shop is responsible for all activity under its login credentials. Shop must
        promptly notify TCC of any unauthorized use of its account.

3. PAYMENT METHOD ON FILE & AUTHORIZED CHARGES
   3.1  By saving a payment method, Shop authorizes TCC and its payment processor
        (Stripe, Inc.) to charge the saved card for completed calibration services
        in accordance with this Agreement. Card data is stored exclusively with
        Stripe; TCC retains only Stripe identifiers (no PAN, no CVC).
   3.2  Charges are initiated upon completion of the calibration. For bookings
        scheduled within seven (7) calendar days, TCC may place a pre-authorization
        hold for the calibration amount at the time of booking; the hold is captured
        upon successful job completion and is automatically released by Stripe if
        the booking is cancelled or fails to complete within the authorization
        window.
   3.3  Shop agrees that the saved card will be kept current. If a card is lost,
        stolen, expired, or otherwise unusable, Shop will update the card on file
        within two (2) business days. Failure to maintain a valid payment method
        may result in suspension of booking privileges.

4. PRICING & THE DUAL-INVOICE MODEL
   4.1  TCC's standard pricing is published in the Shop's portal and may be modified
        by mutual written agreement on a per-Shop basis (negotiated rate card).
   4.2  Standard prices in effect as of v1.0:
            Static ADAS Calibration              $125.00
            Dynamic ADAS Calibration             $125.00
            Dual ADAS Calibration                $175.00
            Triple-Camera / Subaru Calibration   $185.00
            Tesla ADAS Calibration               $225.00
   4.3  Cash Job. For cash jobs (vehicle owner pays the Shop directly, no insurance
        carrier involved), TCC's charge equals the calibration price for the type
        performed (the "Flat Calibration Fee"). Shop is responsible for collecting
        from the vehicle owner.
   4.4  Insurance Job. For insurance jobs, the Shop's insurance carrier approves an
        amount for the calibration line item (the "Approved Amount"). Shop will
        enter the Approved Amount at booking. The Approved Amount is recorded for
        the Shop's accounting reference. Regardless of the Approved Amount, TCC's
        charge to Shop's card on file equals the Flat Calibration Fee for the
        calibration type performed; any amount the Shop receives from the carrier
        in excess of the Flat Calibration Fee belongs to the Shop.
   4.5  Same-Day Emergency Surcharge. A $25.00 surcharge applies to any same-day
        emergency calibration request.
   4.6  Calibration Failure / No-Fault Trip Charge. In the unlikely event a
        calibration cannot be completed for reasons outside TCC's control
        (including without limitation a defective or aftermarket windshield,
        broken parts or glass, missing camera modules, no-show customer, or
        inaccessible vehicle), TCC will charge a $30.00 trip charge in lieu of
        the full calibration price.
   4.7  No Charge for TCC-Caused Failures. If a calibration fails due to TCC's
        equipment, knowledge, or workmanship, no fee will be charged for that
        attempt.

5. WARRANTIES
   5.1  Lifetime Workmanship Warranty. TCC warrants its calibration workmanship for
        the life of the vehicle. If the original calibrated vehicle requires a
        subsequent windshield replacement and/or recalibration for reasons not
        caused by TCC, TCC will provide that recalibration for the $30.00 trip
        charge described in §4.6 only — no second calibration fee will apply.
   5.2  Post-Calibration ADAS Alerts. If the vehicle displays an ADAS warning or
        fault after a TCC calibration, the customer or Shop must contact TCC at
        (480) 269-1329 promptly so the issue can be diagnosed and resolved at no
        additional cost where TCC is at fault.

6. DISPUTES, CREDITS & REFUNDS
   6.1  Disputes. Any disputed charge must be raised in writing to TCC within seven
        (7) calendar days of the charge date.
   6.2  No Automatic Refunds. TCC does not issue automatic refunds. Any amount due
        back to Shop will be applied as an account credit toward future
        calibrations. All credits require TCC administrator approval before
        issuance.
   6.3  Late Disputes. Disputes raised after the seven-day window may be considered
        at TCC's discretion but are not guaranteed.

7. SCHEDULING, CANCELLATION & RESCHEDULING
   7.1  Service Area. Services are provided within the Phoenix metropolitan area,
        divided into West Valley and East Valley service zones. Bookings outside
        the service area require advance written agreement.
   7.2  Slots. Time slots are 45 minutes and are released in zone-locked blocks
        (West Valley: 8:00 AM – 2:00 PM; East Valley: 2:30 PM – 7:00 PM).
   7.3  Cancellations. Shop may cancel or reschedule a booking at no charge up to
        four (4) hours before the scheduled start. Cancellations made inside that
        window may incur the $30.00 trip charge if TCC has already dispatched or
        begun travel.

8. INVOICING & ACCOUNTING
   TCC will record a draft invoice in its accounting system (Xero) for each
   completed calibration, referencing the Shop's account, the vehicle (year/make/
   model/VIN), the calibration type performed, and the Flat Calibration Fee. The
   Shop is responsible for invoicing the relevant insurance carrier or vehicle
   owner separately.

9. PERSONAL DATA & VEHICLE INFORMATION
   Shop represents that it has authority to share with TCC the customer name,
   vehicle, and address information necessary to perform calibration services.
   TCC will use this information solely to perform the services, communicate with
   the Shop and customer about the booking, and maintain calibration records as
   required by law and best industry practice.

10. TERMINATION
    Either party may terminate this Agreement upon two (2) weeks' written notice.
    TCC may terminate immediately upon any material breach by Shop, including
    without limitation failure to maintain a valid payment method, repeated
    chargebacks, or false reporting of job type or approved amounts.

11. CHANGES TO THESE TERMS
    TCC may update these Terms at any time by publishing a new version in Shop's
    portal. Continued use of the portal after a new version is published, including
    any booking made after publication, constitutes acceptance of the new version.
    Material changes affecting payment authorization will require a fresh
    electronic signature before further bookings may be made.

12. GOVERNING LAW & DISPUTE RESOLUTION
    This Agreement is governed by the laws of the State of Arizona, without regard
    to conflict-of-laws principles. The parties agree to participate in good-faith
    mandatory arbitration before filing any civil action, and to accept the
    determination of the arbitrator in that proceeding.

13. ENTIRE AGREEMENT
    This Agreement, together with any negotiated rate-card addendum referenced in
    Shop's portal, constitutes the entire agreement between TCC and Shop and
    supersedes all prior agreements, written or oral, on the subject matter
    herein. No oral modification will bind either party; modifications must be
    made in writing and signed (electronically or otherwise) by both parties.

ELECTRONIC SIGNATURE
By typing your full legal name below and clicking "I Agree", you confirm that you
have read these Terms in full, that you have authority to bind your Shop to this
Agreement, and that your electronic signature has the same legal force and effect
as a handwritten signature.

The Calibration Crew LLC
1342 W Emerald Ave., Unit 300, Mesa, AZ 85202
(480) 269-1329
"""


def current_terms() -> dict:
    """Return the in-code current T&A document."""
    return {
        "version": TERMS_V1_VERSION,
        "effective_date": TERMS_V1_EFFECTIVE_DATE,
        "content": TERMS_V1_TEXT,
    }


async def ensure_terms_seeded(db) -> None:
    """Insert the current terms row if it doesn't already exist."""
    existing = await db.terms_versions.find_one({"version": TERMS_V1_VERSION})
    if existing:
        return
    from datetime import datetime, timezone
    await db.terms_versions.update_many({"is_current": True}, {"$set": {"is_current": False}})
    await db.terms_versions.insert_one({
        "version": TERMS_V1_VERSION,
        "effective_date": TERMS_V1_EFFECTIVE_DATE,
        "content": TERMS_V1_TEXT,
        "is_current": True,
        "published_at": datetime.now(timezone.utc).isoformat(),
    })
