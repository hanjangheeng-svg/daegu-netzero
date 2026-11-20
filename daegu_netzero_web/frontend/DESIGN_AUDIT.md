# Daegu NetZero · Frontend review / v1.8

This is a project-specific agent checklist informed by the publicly accessible Anthropic frontend-design skill (https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md), not a claim that a separate agent skill was installed. Use it for each release.

Visual direction: restrained industrial analysis instrument, not a generic SaaS marketing landing page. One decision-first element, disciplined typography and physical units, minimal decorative chrome.

## Content hierarchy
- [ ] Show decision, estimated benefit, comparison, and next action above long tables.
- [ ] Distinguish chosen minimum-complexity recommendation from maximum-reduction alternatives.
- [ ] Identify demo data, user inputs, model assumptions, and public statistics separately.
- [ ] Keep scientific units and rounded display values; retain full precision only in JSON exports.
- [ ] Do not use fabricated testimonials, baseless badges, decorative AI language, excessive gradients, or made-up confidence labels.

## Every interactive control
- [ ] Pointer for click actions, default text cursor for reading, not-allowed for disabled controls.
- [ ] Hover, focus-visible, active, disabled, loading and failure states.
- [ ] Clear verbs: calculate, extract, approve, return, export.
- [ ] No silent success, no crash-to-white-screen, actionable error messages.
- [ ] Keyboard-only navigation and accessible labels.

## Page-specific questions
- **Overview:** Is the result current? Is target achieved? Why this combination? What next?
- **Plant input:** What changed? Is this a sample or a real factory? Is analysis stale?
- **Process:** What was extracted, by what method? Which values were approved? What physical limitations apply?
- **Economics:** Are tariffs and capital assumptions visible? Are payback years correctly labeled as simple payback? Is export current?
- **Region:** What is the year, source and category? Is factory data not conflated with Daegu totals?
- **Evidence:** Is assumption sensitivity separated from statistical confidence? Are audit checks explicitly internal only?

## Test matrix
- 1440/1024/768/375/320 px widths; 200% browser zoom.
- Mouse hover, keyboard Tab+Enter, disabled buttons, error and loading states.
- Change input without calculating: warn that old result is stale; avoid stale export.
- Extract / approve / modify / unapprove; navigate to dashboard, economic scenario, export.
- API disconnected: error stays visible and UI remains usable.

## Known limits
- No real frontend browser render test was completed in this environment.
- LLM extraction using actual API credentials was not verified.
- Output ZIP is raw data, not a user-ready PDF.
