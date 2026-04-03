# Sample Meeting Transcripts

Use these sample transcripts to test the MeetingMind system.

---

## Sample 1: Q3 Product Planning Meeting (Recommended for Demo)

```
Meeting Title: Q3 Product Planning Discussion
Date: June 5, 2026
Attendees: Sarah (Product Manager), John (Engineering Lead), Maria (Design Lead), Alex (Marketing)

Sarah: Good morning everyone. Let's dive into our Q3 roadmap. Our main priority is launching the mobile app by end of August. John, can you give us a status update on the backend infrastructure?

John: Sure. The API is 80% complete. We need to finish the authentication module and optimize the database queries. I estimate we need another 3 weeks. I'll assign Tom to handle the auth module since he has experience with OAuth implementations.

Sarah: Great. Make sure the authentication is rock solid - security is critical for mobile. Maria, how's the UI design coming along?

Maria: We've completed wireframes for all core screens. The design system is finalized. My team is now working on high-fidelity mockups. We should have everything ready for handoff to engineering by June 20th. I need Alex's team to provide the final copy for onboarding screens though.

Alex: No problem. I'll get the copywriting done by next week. We're also planning a launch campaign for August 25th. We need beta testers lined up by July 15th to get feedback before the public launch. Sarah, can you coordinate the beta program?

Sarah: Yes, I'll own the beta program. I'll need John to set up a separate staging environment for beta users by July 1st. Also, we need to fix the notification system bugs that came up last sprint - customers are complaining about delayed push notifications.

John: I saw those bug reports. I'll prioritize the notification fix. It's probably related to our queue processing. I'll assign Lisa to investigate this week and we should have a fix deployed by end of next week.

Maria: One more thing - we need to schedule a design review meeting with stakeholders before we start development. Can we do that on June 15th at 10 AM?

Sarah: June 15th works for me. Let's make it happen. John and Alex, please block your calendars.

John: Confirmed.

Alex: Sounds good.

Sarah: Perfect. To summarize: John's team will finish the API and fix notification bugs, Maria will complete the mockups by June 20th, Alex will deliver copy by next week and coordinate with me on the beta program, and I'll set up the staging environment logistics. Let's reconvene on June 15th for the design review. Any questions?

Everyone: No questions. Thanks!

Sarah: Great. Meeting adjourned.
```

**Expected System Output:**
- **Summary**: Q3 mobile app launch planning, API development status, design progress, beta program coordination
- **Tasks** (8-10 high/medium priority items):
  - John: Complete authentication module (3 weeks)
  - Tom: Implement OAuth authentication
  - John: Optimize database queries
  - John: Set up staging environment by July 1st
  - Lisa: Fix notification system bugs by end of next week
  - Maria: Complete high-fidelity mockups by June 20th
  - Alex: Deliver onboarding screen copy by next week
  - Sarah: Coordinate beta program (beta testers by July 15th)
  - Schedule design review meeting June 15th at 10 AM
- **Scheduled Meeting**: Design review on June 15, 2026 at 10:00 AM
- **Notes**: Security critical for mobile auth, notification bugs affecting customers, launch campaign August 25th

---

## Sample 2: Sprint Retrospective

```
Meeting: Sprint 12 Retrospective
Date: April 1, 2026
Attendees: Mike (Scrum Master), Emma (Developer), David (Developer), Rachel (QA)

Mike: Welcome to our Sprint 12 retrospective. Let's talk about what went well, what didn't, and action items for improvement. Emma, want to start?

Emma: I think the collaboration between dev and QA was much better this sprint. Rachel caught bugs early which saved us time. However, I struggled with unclear requirements on the checkout flow feature. We had to redo work twice.

Rachel: Thanks Emma. I agree the early testing helped. On the flip side, we need better test data. I spent 2 hours manually creating test accounts. David, can you write a script to generate dummy data?

David: Absolutely. I'll create a data seeding script by end of this week. Also, I noticed our CI/CD pipeline is slow - builds take 25 minutes. This slows down our deployment velocity. Mike, can we allocate time next sprint to optimize the build process?

Mike: Good point. Let's make pipeline optimization a priority. I'll add it to next sprint's backlog. Emma, regarding the unclear requirements - let's schedule a refinement session with the product owner before sprint planning next time.

Emma: That would help a lot. Also, I think we need to update our API documentation. It's outdated and caused confusion when David was integrating with my endpoints.

David: Yes, please! Updated docs would save me hours. Emma, can you own that?

Emma: Sure. I'll update the API docs by April 10th.

Rachel: One more thing - our regression test suite needs expansion. We're not covering edge cases well. I'll create a proposal for additional test scenarios and share it with the team by next Monday.

Mike: Excellent. To recap our action items: David will create a data seeding script by end of week, Emma will update API documentation by April 10th, Rachel will propose expanded test scenarios by Monday, I'll add CI/CD optimization to next sprint, and we'll schedule a requirements refinement session before next planning. Anything else?

Everyone: Nope, that covers it.

Mike: Great work everyone. See you at sprint planning on Thursday!
```

**Expected System Output:**
- **Summary**: Sprint retrospective identifying collaboration successes, requirement clarity issues, testing improvements needed
- **Tasks** (5-6 medium priority items):
  - David: Create data seeding script by end of week
  - Emma: Update API documentation by April 10th
  - Rachel: Propose expanded test scenarios by next Monday
  - Mike: Add CI/CD optimization to next sprint backlog
  - Mike: Schedule requirements refinement session before next sprint planning
- **Scheduled Meeting**: Sprint planning on Thursday
- **Notes**: CI/CD pipeline slow (25 min builds), QA needs better test data, collaboration improved

---

## Sample 3: Customer Escalation Meeting

```
Meeting: Customer Escalation - DataCorp Account
Date: March 28, 2026
Attendees: Jennifer (Account Manager), Kevin (Support Lead), Linda (Engineering Manager)

Jennifer: Thanks for joining on short notice. We have a critical escalation from DataCorp, one of our top enterprise customers. They're experiencing intermittent API timeouts for the past 3 days affecting their production system. Kevin, what do we know?

Kevin: We've received 12 support tickets from DataCorp since Monday. The timeouts occur during peak hours - between 9 AM and 11 AM PST. Our monitoring shows increased latency on the /api/data/export endpoint. Linda, has your team identified the root cause?

Linda: We're investigating. Initial analysis suggests it's related to the database connection pool getting exhausted under load. We implemented auto-scaling last month but there might be a configuration issue. I've assigned Carlos to dig deeper - he should have findings by tomorrow morning.

Jennifer: Tomorrow morning might be too late. DataCorp's VP of Engineering called me directly - they're considering switching to a competitor if this isn't resolved fast. What can we do today?

Linda: I can have Carlos focus on this exclusively. As a temporary mitigation, we can increase the connection pool size manually within the next 2 hours. That should reduce the timeout frequency while we implement a proper fix.

Kevin: I'll personally call DataCorp's technical contact to explain our mitigation plan and timeline. Jennifer, can you loop in their VP to reassure them we're prioritizing this?

Jennifer: Yes, I'll call the VP immediately after this meeting. Linda, what's the timeline for a permanent fix?

Linda: Once Carlos identifies the exact issue tomorrow, the fix should take 1-2 days to implement and test. I'd say we can deploy a permanent solution by Friday morning. We'll also need to do a full performance audit to prevent similar issues - I'll schedule that for next week.

Kevin: Our support team needs better visibility into backend performance. Can we get access to the same monitoring dashboards your engineering team uses?

Linda: Good idea. I'll grant support team access to our Grafana dashboards today. That'll help you proactively identify issues before customers report them.

Jennifer: Okay, action plan is clear. Linda increases connection pool size within 2 hours, Carlos investigates root cause by tomorrow morning, Kevin calls DataCorp's technical contact, I'll reassure their VP, permanent fix deployed by Friday, performance audit next week, and support gets monitoring access today. Let's execute. I'll send a recap email in 30 minutes.

Everyone: Agreed. Let's do this.
```

**Expected System Output:**
- **Summary**: Critical escalation for DataCorp - API timeouts, immediate mitigation and permanent fix plan
- **Tasks** (7-8 high priority items):
  - Linda: Increase database connection pool size within 2 hours
  - Carlos: Investigate root cause by tomorrow morning
  - Carlos: Implement permanent fix by Friday morning
  - Kevin: Call DataCorp technical contact immediately
  - Jennifer: Call DataCorp VP to reassure
  - Linda: Schedule performance audit for next week
  - Linda: Grant support team Grafana dashboard access today
  - Jennifer: Send recap email in 30 minutes
- **Notes**: Critical issue affecting top customer, timeouts 9-11 AM PST, connection pool exhaustion suspected, customer considering switching

---

## Sample 4: Budget Planning Meeting

```
Meeting: 2026 Q4 Budget Planning
Date: July 10, 2026
Attendees: Robert (CFO), Amanda (Head of Engineering), Chris (Head of Sales), Diana (Head of Operations)

Robert: Let's discuss Q4 budget allocations. We have $500K discretionary budget to distribute. Each department submitted requests. Amanda, let's start with engineering.

Amanda: We're requesting $200K for Q4. Breaking it down: $80K for cloud infrastructure expansion as we're hitting capacity limits, $70K for 3 new contractor hires to accelerate the AI features roadmap, and $50K for security audit and compliance tools - we need SOC 2 certification to close enterprise deals.

Chris: The SOC 2 point is critical. I have 5 enterprise prospects worth $2M in pipeline who won't sign without that certification. Amanda, what's the timeline if we approve the $50K?

Amanda: With budget approval today, we can start the audit process next week. Full certification takes 3-4 months, so we'd have it by end of October.

Robert: Noted. Chris, what's sales requesting?

Chris: $150K total. $100K for attending 3 major industry conferences in Q4 - these events generated 40% of our pipeline last year. $50K for a new CRM system - our current tool can't handle the volume and we're losing leads due to poor tracking.

Diana: I can vouch for the CRM issue. Operations is also affected - we need better visibility into customer onboarding status. Our request is $100K: $60K for customer success platform integration, and $40K for hiring a dedicated operations analyst to improve our processes.

Robert: Let me do the math. That's $450K total across all requests, and we have $500K available. The $50K buffer should stay as contingency. However, I want to prioritize items with immediate revenue impact. Chris, the conferences have proven ROI. Amanda, SOC 2 directly enables sales. Diana, the operations analyst can wait until Q1.

Diana: Understood. What about the customer success platform?

Robert: How critical is it?

Diana: It would reduce churn by improving onboarding experience. Without it, we risk losing customers after they sign.

Amanda: I'd argue that's as important as getting new customers. Customer retention impacts MRR.

Robert: Fair point. Okay, here's my decision: Approved - Engineering infrastructure $80K, SOC 2 $50K, Engineering contractors $70K, Sales conferences $100K, Sales CRM $50K, Operations customer success platform $60K. Total $410K. The remaining $90K stays in contingency. Diana, we'll revisit the analyst hire in Q1. Does this work for everyone?

Amanda: Works for me. I'll start contractor hiring process next week.

Chris: Perfect. I'll register for the conferences - first one is September 15th in New York.

Diana: I'll begin evaluating customer success platforms tomorrow. Should have vendor options by end of next week.

Robert: Great. Amanda, send me the SOC 2 audit vendor quotes by Friday so I can process payment. Diana, include me in the platform evaluation - I want to review pricing. Meeting adjourned.
```

**Expected System Output:**
- **Summary**: Q4 budget allocation across engineering, sales, operations - $410K approved from $500K available
- **Tasks** (6-7 medium/high priority items):
  - Amanda: Start contractor hiring process next week
  - Amanda: Send SOC 2 audit vendor quotes to Robert by Friday
  - Amanda: Begin SOC 2 audit process next week
  - Chris: Register for conferences (first one September 15th in New York)
  - Diana: Evaluate customer success platform vendors by end of next week
  - Diana: Include Robert in platform pricing review
- **Notes**: $410K approved ($80K infra, $50K SOC 2, $70K contractors, $100K conferences, $50K CRM, $60K CS platform), $90K contingency buffer, ops analyst hire deferred to Q1

---

## Quick Test Queries

After processing a transcript, try these queries:

1. **Query tasks**: "What tasks are pending?"
2. **Filter by priority**: "Show me high priority tasks"
3. **Filter by owner**: "List all tasks assigned to John"
4. **Update status**: "Mark task 1 as done"
5. **Store memory**: "Remember that DataCorp is a critical customer"
6. **Retrieve memory**: "What do you remember about DataCorp?"

---

## Tips for Testing

- **Minimum length**: Transcripts should be 500+ characters to trigger TRANSCRIPT intent
- **Include names**: Mention specific people for task assignment
- **Include dates**: Helps with deadline extraction
- **Mention meetings**: Triggers scheduler agent
- **Vary language**: Test with different phrasings and styles
- **Check duplicates**: Try processing similar transcripts to test duplicate detection

---

## Expected Processing Time

- **Transcript processing**: 8-12 seconds
- **Query response**: 1-2 seconds
- **Command execution**: 1-2 seconds
- **Memory storage**: 1-2 seconds
