#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Step 1 — make Xero invoicing real (OAuth + invoice + PDF attach + status poll), credential-optional with graceful fallback to the existing mock; target the Xero Demo Company first. Module 9 — build out the Partner Growth Engine (Power Connector 5+50+100 CRM + 3-D introductions) from its inert scaffold into a real, flagged-on v1; reels explicitly deferred (no video-generation capability available)."

backend:
  - task: "Xero OAuth 2.0 connect/callback/disconnect"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Added GET /api/auth/xero/connect (returns authorize URL, signed-JWT state), GET /api/auth/xero/callback (code exchange + /connections tenant + token storage, redirects to /settings?xero=connected|error), POST /api/auth/xero/disconnect. Needs live testing against Xero Demo Company once XERO_CLIENT_ID/SECRET/REDIRECT_URI are set."
  - task: "Real Xero draft invoice on job completion (+ PDF attachment) with mock fallback"
    implemented: true
    working: "NA"
    file: "backend/server.py, backend/xero_invoice.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "create_invoice_for_job() uses real Xero when configured+connected else mock. Contact lookup/create, ACCREC DRAFT invoice (spec 2-line format via xero_invoice.py), attaches the uploaded calibration PDF. Pure payload builder unit-validated locally (format/account-code/VIN fallbacks). Live Xero call path needs testing with real creds."
  - task: "Xero invoice status polling (DRAFT->AUTHORISED->PAID)"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "POST /api/integrations/xero/poll maps Xero statuses onto job.invoice_status. Needs live testing + a scheduled trigger (~4h)."
  - task: "GET /api/integrations/status + merged /api/invoices (real+mock)"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Status endpoint reports configured/connected/mode per integration; /invoices now merges xero_invoices + mock_xero_invoices."
  - task: "Module 9: Partner Growth contacts CRUD + 5/50/100 grid with cap enforcement"
    implemented: true
    working: "NA"
    file: "backend/growth/routes.py, backend/growth/models.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "GET/POST /api/growth/contacts, PATCH /api/growth/contacts/{id}, GET /api/growth/grid. Circle changes are cap-enforced (409 when the target circle is already at GRID_CAPS[circle]; owner must explicitly demote someone first — no silent auto-demotion on write). enforce_grid_caps(db) is a separate idempotent corrective sweep run at startup. Covered by backend/tests/test_growth.py (RBAC, CRUD, cap enforcement)."
  - task: "Module 9: deterministic daily nurture-touch nudges"
    implemented: true
    working: "NA"
    file: "backend/growth/models.py, backend/growth/routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "GET /api/growth/nudges/today calls generate_daily_nudges() — no LLM, template picked deterministically from contact favor state, idempotent per calendar day via a new Touch.nudge_date field. Covered by backend/tests/test_growth.py (idempotency check: repeat call produces no duplicate touch for the same contact)."
  - task: "Module 9: touch + intro approve->send with real dispatch (mock_send_sms / send_email reuse)"
    implemented: true
    working: "NA"
    file: "backend/growth/routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "POST /api/growth/touches/{id}/approve|send and /api/growth/intros/{id}/approve|send. sms channel reuses mock_send_sms; email channel reuses send_email (Resend-if-configured, else logged) — no new outbound-comms integration. Sending updates the contact's favors_given/favors_asked/last_touch_at/next_touch_due. Every approve/send writes to a new ai_action_log collection. Covered by backend/tests/test_growth.py (send-before-approve rejected, touch lifecycle, intro lifecycle + favor bump, email-required-on-both-sides)."
  - task: "Module 9: reels (ReelAsset, /api/growth/reels/generate) — explicitly deferred, not implemented"
    implemented: false
    working: "NA"
    file: "backend/growth/models.py"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "No video-generation capability was available to build this, so it was left out of v1 rather than shipped as a misleading stub. ReelAsset model stays defined for whenever a video pipeline exists. See docs/module9/README.md 'Deferred' section."

frontend:
  - task: "Settings → Integrations: Connect/Disconnect Xero + live status banner"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Settings.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "IntegrationsTab loads /integrations/status, shows Connect Xero (configured) / Disconnect (connected) / Mock mode (unconfigured), and a success/error banner from ?xero= on OAuth return."
  - task: "Module 9: Growth page (grid + nudges + intros), owner nav, Settings status row"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/growth/Growth.jsx, frontend/src/App.js, frontend/src/components/Shell.jsx, frontend/src/pages/Settings.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Growth.jsx rewritten from a static placeholder into a real page: circle-grouped contact grid + add-contact form, Today's Nudges panel with Approve/Send, a 3-D intro creator/list. Routed at /growth, added to Shell.jsx owner nav, and a Growth status row added to Settings → Integrations. Still self-guards on REACT_APP_GROWTH_MODULE_ENABLED so it degrades to the original placeholder card without a code change. Not yet visually verified in a browser — needs UI testing."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 0
  run_ui: false

test_plan:
  current_focus:
    - "Module 9: Partner Growth contacts CRUD + 5/50/100 grid with cap enforcement"
    - "Module 9: deterministic daily nurture-touch nudges"
    - "Module 9: touch + intro approve->send with real dispatch (mock_send_sms / send_email reuse)"
    - "Module 9: Growth page (grid + nudges + intros), owner nav, Settings status row"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Step 1 (real Xero invoicing) implemented credential-optional via Claude Code. Without XERO_CLIENT_ID/SECRET/REDIRECT_URI the app still uses the mock, so existing tests should remain green. To test the real path: set the Xero env vars, connect against the Xero Demo Company from Settings → Integrations, complete a job, and confirm a DRAFT invoice with the spec's two line items + PDF attachment appears in Xero. The pure invoice-format unit tests live in backend/tests/test_xero_invoice.py."
    - agent: "main"
      message: "Module 9 (Partner Growth Engine) built out from its inert scaffold into a real v1 via Claude Code: contacts CRUD + 5/50/100 grid with cap enforcement, deterministic daily nurture-touch nudges, touch/intro approve→send with real dispatch reusing the existing mock_send_sms/send_email helpers (no new secrets/integrations), and a real Growth page routed at /growth. GROWTH_MODULE_ENABLED now defaults true (was false). Reels (ReelAsset, /api/growth/reels/generate) are explicitly NOT implemented — no video-generation capability was available; see docs/module9/README.md 'Deferred' section. backend/tests/test_growth.py covers RBAC, contact CRUD, cap enforcement, nudge idempotency, and the touch/intro approve→send lifecycles — run it as part of `cd backend && pytest tests/ -v`. The frontend Growth page has not been visually verified in a browser (this environment can't run the CRA build — it depends on the private @emergentbase/visual-edits package per CLAUDE.md); please give it a UI pass once synced to Emergent."