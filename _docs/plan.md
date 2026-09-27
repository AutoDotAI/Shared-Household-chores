# Shared Household Chores — Product Specification

## 1. Product Summary

A simple shared household chore management tool for roommates, couples, families, and other shared households.

The product revolves around a **person-centric household board** where each member has a column containing their assigned chores. Household admins create and assign chores, while regular members can view their chores, claim open chores, and mark chores as done.

The product should prioritize simplicity over gamification or complex productivity features.

---

## 2. Product Goal

Help a household answer four questions quickly:

1. **What needs to be done?**
2. **Who is responsible for it?**
3. **When is it due?**
4. **Has it been completed?**

The main interface should make the current state of household responsibilities obvious at a glance.

---

## 3. Target Users

The application should work for any shared household, including:

- Roommates
- Couples
- Families
- Other people sharing a home

The product should not require users to select a household type during onboarding.

---

## 4. Roles

There are two roles.

### Admin

Admins can:

- Create chores
- Edit chores
- Delete chores
- Assign chores to members
- Leave chores unassigned
- Configure recurrence
- Invite household members by email
- Remove household members
- View all chores
- Mark any chore as done

A household must always have at least one admin.

### Member

Members can:

- View the household board
- View chores assigned to them
- View open/unassigned chores
- Claim an open chore
- Mark their assigned chores as done
- View basic completion history

Members cannot:

- Create chores
- Edit chores
- Delete chores
- Assign chores to other users
- Manage household membership

---

## 5. Authentication and Invitations

Authentication should be passwordless.

### Sign-in

Users enter their email address and receive a **magic link**.

Clicking the link authenticates the user.

No password system is required.

### Household Invitation

Admins invite members by entering their email address.

The invited user receives an email containing a magic link.

When the invited user opens the link:

1. They are authenticated.
2. They join the household automatically.
3. They are given the `Member` role by default.

If the email already belongs to an existing user, the invitation simply adds that user to the household.

---

## 6. Main Household Board

The board is the application's primary screen.

### Layout

The board is organized into columns:

```text
Open
│
├── Clean oven
└── Take recycling out

Alice
│
├── Vacuum living room
└── Clean bathroom

Bob
│
├── Buy groceries
└── Wash dishes
```

There is:

- One **Open** column for unassigned chores.
- One column for each household member.

### Chore Card

Each chore card displays only:

- Chore title
- Assignee, if assigned
- Due date
- Status

Statuses are limited to:

- `To do`
- `Done`

The UI should visually distinguish overdue chores.

---

## 7. Chore Creation

Only admins can create chores.

A chore contains:

| Field | Required | Description |
|---|---|---|
| Title | Yes | Short description of the chore |
| Assignee | No | Household member responsible for it |
| Due date | Yes | Date the chore should be completed |
| Status | Yes | `To do` or `Done` |
| Recurrence | No | Rules for repeating chores |

If no assignee is selected, the chore appears in the **Open** column.

---

## 8. Claiming Open Chores

Members can claim chores from the Open column.

When a member clicks **Claim**:

1. The chore becomes assigned to that member.
2. It moves from the Open column to that member's column.
3. The change is immediately visible to all household members.

Members cannot directly transfer their assigned chores to another person.

An admin must edit the assignment if reassignment is needed.

---

## 9. Completing Chores

A member can mark one of their assigned chores as done.

Admins can mark any chore as done.

When marked as done:

- Status becomes `Done`.
- Completion timestamp is stored.
- The completing user is stored.
- The card remains visible temporarily in the member's column or can be filtered out.

The default board view should primarily show `To do` chores.

A toggle can reveal completed chores.

---

## 10. Recurring Chores

Recurring chores are supported.

Admins can configure recurrence using:

- Every X days
- Every X weeks
- Every X months
- Specific weekdays

Examples:

```text
Every 2 days

Every week on Monday

Every 2 weeks on Saturday

Every month on the 1st
```

### Recurrence Behavior

Recurring chores are represented as a recurring chore definition plus individual chore occurrences.

When a recurring occurrence is marked done:

1. The completed occurrence remains in history.
2. The system automatically creates the next occurrence.
3. The new occurrence receives the calculated next due date.
4. The new occurrence keeps the same assignee unless an admin changes the recurrence configuration.

The system should avoid generating an unlimited number of future occurrences in advance.

Only the next occurrence needs to exist.

---

## 11. Chore History

The application includes **basic history**.

Users can see:

- Chore title
- Who completed it
- Completion date/time

History is household-wide.

No advanced statistics are required.

Out of scope:

- Points
- Streaks
- Leaderboards
- Fairness scores
- Workload analytics

---

## 12. Notifications

Keep notifications minimal.

### Required

Send email notifications for:

- Household invitation

### Optional / Nice-to-have

If time permits:

- Reminder when a chore becomes due
- Reminder when a chore is overdue

Push notifications, SMS, and notification preference systems are out of scope.

---

## 13. Household Management

Admins have a simple household settings page.

They can:

- Rename the household
- Invite a member by email
- See current members
- Change a member between `Admin` and `Member`
- Remove a member

If a removed member has active chores, those chores become unassigned and move to the Open column.

An admin cannot remove the final remaining admin.

---

## 14. Filters

The board should stay simple.

Provide only basic filters:

- Show `To do`
- Show `Done`
- Show overdue

No advanced search or saved filters are required.

---

## 15. Core User Flows

### Flow A — Create Household

```text
User enters email
        ↓
Receives magic link
        ↓
Signs in
        ↓
Creates household
        ↓
Becomes household Admin
        ↓
Household board opens
```

### Flow B — Invite Member

```text
Admin opens Household Settings
        ↓
Enters member email
        ↓
Invitation email sent
        ↓
Member clicks magic link
        ↓
Member joins household
        ↓
Member appears as a new board column
```

### Flow C — Create Assigned Chore

```text
Admin clicks "New chore"
        ↓
Enters title
        ↓
Chooses assignee
        ↓
Selects due date
        ↓
Optionally configures recurrence
        ↓
Creates chore
        ↓
Chore appears in assignee's column
```

### Flow D — Create Open Chore

```text
Admin creates chore
        ↓
Leaves assignee empty
        ↓
Chore appears in Open column
        ↓
Member clicks "Claim"
        ↓
Chore moves to member's column
```

### Flow E — Complete One-Off Chore

```text
Member sees assigned chore
        ↓
Clicks "Done"
        ↓
Chore becomes completed
        ↓
Completion is added to history
```

### Flow F — Complete Recurring Chore

```text
Member marks occurrence Done
        ↓
Current occurrence stored as completed
        ↓
System calculates next due date
        ↓
Next occurrence created automatically
        ↓
New occurrence appears on board
```

---

## 16. Suggested Screens

The homework can be implemented with only these screens.

### 1. Authentication

- Email input
- "Send magic link"

### 2. Household Board

- Open column
- One column per member
- New chore button for admins
- Basic status filters

### 3. Chore Form

- Title
- Assignee
- Due date
- Recurrence configuration
- Save

Used for both create and edit.

### 4. Household Settings

- Household name
- Member list
- Invite member
- Role management
- Remove member

### 5. History

Simple chronological list of completed chores.

---

## 17. Suggested Data Model

### User

```text
id
email
created_at
```

### Household

```text
id
name
created_at
```

### HouseholdMember

```text
id
household_id
user_id
role
joined_at
```

`role`:

```text
admin
member
```

### Invitation

```text
id
household_id
email
token
expires_at
accepted_at
created_at
```

### RecurrenceRule

```text
id
frequency
interval
weekdays
day_of_month
```

Possible `frequency` values:

```text
daily
weekly
monthly
```

Examples:

```text
frequency = daily
interval = 2
```

means every 2 days.

```text
frequency = weekly
interval = 1
weekdays = [MONDAY, THURSDAY]
```

means every Monday and Thursday.

### Chore

```text
id
household_id
title
assignee_id
due_date
status
recurrence_rule_id
recurring_series_id
completed_at
completed_by
created_by
created_at
updated_at
```

`assignee_id` may be null for open chores.

`status`:

```text
todo
done
```

`recurring_series_id` links occurrences belonging to the same recurring chore.

---

## 18. Permissions Matrix

| Action | Admin | Member |
|---|:---:|:---:|
| View board | ✓ | ✓ |
| View history | ✓ | ✓ |
| Create chore | ✓ | |
| Edit chore | ✓ | |
| Delete chore | ✓ | |
| Assign chore | ✓ | |
| Claim open chore | ✓ | ✓ |
| Complete own chore | ✓ | ✓ |
| Complete another user's chore | ✓ | |
| Invite member | ✓ | |
| Remove member | ✓ | |
| Change roles | ✓ | |

---

## 19. Business Rules

1. Every chore belongs to exactly one household.
2. A chore may have zero or one assignee.
3. Only members of the household can be assigned chores.
4. An unassigned chore appears in the Open column.
5. A member may claim an open chore.
6. Members may only complete chores assigned to themselves.
7. Admins may complete any chore.
8. Completed chores must retain completion information.
9. Completing a recurring chore creates its next occurrence.
10. Deleting one occurrence must not automatically delete the entire recurring series unless explicitly requested.
11. Removing a member unassigns their unfinished chores.
12. A household must always have at least one admin.
13. Users cannot access households they do not belong to.

---

## 20. Out of Scope

To keep the homework focused, explicitly exclude:

- Native mobile apps
- AI chore assignment
- Automatic fairness optimization
- Gamification
- Points or rewards
- Leaderboards
- Household expense management
- Grocery lists
- Calendar synchronization
- Chat or comments
- Photo proof of completion
- File attachments
- Complex chore dependencies
- Multiple assignees on one chore
- SMS notifications
- Push notifications
- Offline support
- Public profiles
- Social features
- Advanced analytics

---

## 21. MVP Definition

The homework is complete when a user can:

1. Sign in using a magic link.
2. Create a household.
3. Invite another person by email.
4. See one board column per household member.
5. Create a chore.
6. Assign a chore to a member.
7. Leave a chore open.
8. Claim an open chore.
9. Mark an assigned chore as done.
10. Create a custom recurring chore.
11. Automatically generate the next occurrence after completion.
12. View basic completion history.
13. Manage household members and roles.

Everything beyond this list should be treated as optional.

---

## 22. Suggested UX Principle

The product should feel closer to a **shared household whiteboard** than a project-management application.

A user should be able to open the app and understand the current household workload within a few seconds.

Avoid adding features unless they directly improve:

```text
What needs doing?
Who is doing it?
When is it due?
Is it done?
```

That is the core of the product.
