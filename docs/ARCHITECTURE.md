# Matterhorn One v2 — Technical Architecture Blueprint

## 1. Purpose

Matterhorn One will evolve from the existing WorkTrack prototype into a secure, modular and AI-enabled enterprise operations platform.

The current WorkTrack application will remain operational while Matterhorn One v2 is developed separately through controlled, testable phases.

## 2. Architecture Principles

The platform shall follow these principles:

1. Simple for non-technical business users.
2. Modular instead of one large application file.
3. Secure authentication and role-based access.
4. Complete audit trail for important activities.
5. Clear separation between development and production.
6. Reusable data across modules.
7. API-ready architecture for future integrations.
8. AI assistance subject to permissions and human approval.
9. Controlled database migrations and releases.
10. Support for multiple companies and business entities.

## 3. Recommended Technology Direction

The proposed technology stack is:

- Backend: Python with Django
- Database: PostgreSQL
- Frontend: Django templates initially
- Styling: Bootstrap or a controlled internal design system
- API: Django REST Framework
- Background processing: Celery and Redis when required
- Production server: Gunicorn
- Web server: Nginx
- Authentication: Django authentication with enhanced security controls
- File storage: Private local storage initially, with future object-storage support
- Deployment: Separate development, staging and production environments

Django is recommended because it provides structured authentication, database management, security controls, administration and modular application development within one established framework.

The frontend may be modernised later without replacing the core backend.

## 4. Target Project Structure

```text
matterhorn_one/
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   └── production.txt
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── core/
│   ├── accounts/
│   ├── organisations/
│   ├── permissions/
│   ├── workflows/
│   ├── approvals/
│   ├── notifications/
│   ├── documents/
│   ├── audit/
│   └── integrations/
├── modules/
│   ├── tasks/
│   ├── compliance/
│   ├── hr/
│   ├── finance/
│   ├── procurement/
│   ├── projects/
│   ├── crm/
│   ├── esg/
│   └── ai_copilot/
├── templates/
├── static/
├── media/
├── tests/
├── scripts/
└── docs/
```

Each folder under `modules` will represent a business capability. Modules will use the shared services available under `core`.

## 5. Core Platform Responsibilities

The core platform will provide:

- User authentication
- Password and account security
- Organisations and legal entities
- Roles and permissions
- Approval workflows
- Notifications and reminders
- Document storage and linking
- Audit logs
- Common master data
- Application settings
- Import and export services
- API authentication
- Integration controls

Business-specific functions must not be embedded inside the authentication or core infrastructure.

## 6. Initial Business Modules

### 6.1 Tasks and Work Management

This module will cover:

- Task creation and assignment
- Assigner, assignee and reviewer roles
- Priority and due dates
- Recurring tasks
- Progress updates
- Time recording
- Review and closure
- Delay reasons
- Attachments
- Employee workload views
- My Day planning
- Daily reports

This will be the first module migrated because it represents the current WorkTrack functionality.

### 6.2 Compliance

This module will cover:

- Compliance master
- Entity-wise applicability
- Financial year
- Due dates and recurrence
- Responsible person and reviewer
- Reminder and escalation rules
- Filing status
- Acknowledgement details
- Supporting documents
- Compliance calendar
- Audit history

### 6.3 Human Resources

This module may include:

- Employee master
- Organisation structure
- Attendance
- Leave
- Payroll inputs
- Employee documents
- Performance reviews
- Onboarding and exit
- Letters and approvals

### 6.4 Finance

This module may include:

- Accounting workflow controls
- Tally integration
- Trial balance and ledger reporting
- Investment MIS
- Invoice and payment tracking
- Expense approvals
- Receivable and payable monitoring
- Budget versus actual reporting
- Cross-entity dashboards

Matterhorn One should not replace Tally immediately. It should initially operate as a control, workflow and reporting layer around the accounting system.

### 6.5 Procurement

This module may include:

- Purchase requests
- Vendor master
- Quotation comparison
- Approval workflow
- Purchase orders
- Goods and service receipt
- Invoice matching
- Payment recommendations
- Vendor performance

### 6.6 Projects

This module may include:

- Project master
- Milestones
- Activities
- Budgets
- Resources
- Procurement links
- Client approvals
- Progress reporting
- Project documents
- Billing status

### 6.7 CRM

This module may include:

- Leads
- Clients and contacts
- Opportunities
- Proposals
- Follow-ups
- Engagements
- Client documents
- Client portal access

### 6.8 ESG and Sustainability

This module may include:

- ESG data collection
- BRSR indicators
- Evidence documents
- Approval and validation
- Calculation methodology
- Reporting periods
- Management dashboards
- Disclosure preparation
## 7. Organisation and Entity Model

Matterhorn One must support multiple organisations and legal entities.

A user may have access to:

- One organisation
- Multiple organisations
- One or more entities within an organisation
- Specific modules within those entities

Every material business record should include the relevant organisation and, where applicable, legal entity.

This will prevent information from one entity being inadvertently visible to another.

## 8. Authentication Architecture

The authentication system should include:

- Unique user account
- Secure password hashing
- Mandatory password change where required
- Password-reset workflow
- Account activation and deactivation
- Login-attempt controls
- Session timeout
- Optional two-factor authentication
- Last-login information
- Password-change history
- Administrator-controlled access
- Future single sign-on capability

Passwords must never be stored using plain SHA-256 hashing. Django’s established password-hashing framework should be used.

## 9. Role and Permission Model

Permissions should not depend only on broad role names.

The system should support:

- Roles
- Permissions
- User-role assignments
- Organisation scope
- Entity scope
- Module scope
- Record ownership
- Approval authority
- Temporary delegation

Example permissions include:

- View task
- Create task
- Assign task
- Update assigned task
- Review task
- Close task
- View employee data
- Manage employees
- View compliance
- Complete compliance
- Approve procurement
- View finance reports
- Export sensitive information
- Use AI Copilot

Roles may include:

- System Administrator
- Management
- Module Administrator
- Department Head
- Assigner
- Reviewer
- Assignee
- Finance User
- HR User
- Compliance User
- Project Manager
- Employee
- Client Portal User
- Vendor Portal User

A role will operate as a bundle of permissions rather than as a hard-coded condition throughout the application.

## 10. Database Architecture

PostgreSQL is recommended for Matterhorn One v2 because it provides stronger concurrency, integrity, reporting and scalability than SQLite.

The database design should include:

- Primary keys
- Foreign-key relationships
- Required-field rules
- Unique constraints
- Standard created and modified timestamps
- Created-by and modified-by references
- Organisation and entity references
- Status histories
- Soft deletion where appropriate
- Database indexes
- Migration scripts

Separate databases are not required for every module initially. Modules may use one PostgreSQL database with clearly separated tables and application boundaries.
## 11. Audit Trail

Important actions must create audit records containing:

- User
- Date and time
- Organisation and entity
- Module
- Action performed
- Record affected
- Previous value, where appropriate
- New value, where appropriate
- IP address, where appropriate
- Source of action
- Approval reference

Audit records should not be editable by ordinary users.

## 12. Document Management

Documents should be stored through a central document service.

Each document record should include:

- File name
- Document category
- Organisation and entity
- Related module and record
- Uploaded by
- Upload date
- Version
- Access classification
- Retention information
- File checksum
- Approval status, where applicable

Files should not be publicly accessible through predictable URLs.

## 13. Workflow and Approval Engine

The shared workflow engine should support:

- Draft
- Submitted
- Under review
- Approved
- Rejected
- Returned for correction
- Cancelled
- Completed

Approval rules may be based on:

- Organisation
- Entity
- Department
- Amount
- Transaction type
- User designation
- Risk level
- Sequential approval
- Parallel approval

Every approval must be time-stamped and auditable.

## 14. Notifications and Escalations

The notification service should support:

- In-application notifications
- Email notifications
- Scheduled reminders
- Escalations
- Daily summaries
- Future messaging integrations

Business modules should request notifications through the common service rather than implementing separate notification logic.

## 15. API Strategy

Matterhorn One should provide secured, versioned APIs such as:

```text
/api/v1/tasks/
/api/v1/compliances/
/api/v1/employees/
/api/v1/projects/
/api/v1/documents/
```

APIs will support:

- Future mobile applications
- Tally and accounting integrations
- Client and vendor portals
- External reporting tools
- Approved AI functions
- Controlled import and export

API access must follow the same permission rules as the main application.

## 16. Frontend Strategy

The initial frontend should prioritise:

- Clear navigation
- Responsive pages
- Simple forms
- Dashboards based on user responsibility
- Consistent tables and filters
- Excel and PDF exports
- Accessible status indicators
- Minimal technical terminology
- Confirmation before sensitive actions

A separate JavaScript frontend should be considered only when the business benefit justifies the additional complexity.

## 17. AI Copilot Architecture

AI Copilot should operate as a controlled service layer and must not receive unrestricted database access.

Potential capabilities include:

- Natural-language search
- Task and compliance summaries
- Drafting letters and reports
- Explaining dashboard information
- Identifying overdue activities
- Preparing management summaries
- Suggesting workflow actions
- Document analysis

AI controls must include:

- Permission-aware data retrieval
- Human approval before material actions
- Logging of prompts and actions
- Protection of confidential information
- Source references where practical
- No direct financial posting without approval
- No silent modification or deletion of records
- Organisation and entity isolation

The Copilot should initially provide read-only assistance and drafting support. Transactional actions should be introduced only after the approval framework is mature.

## 18. Reporting and Export Strategy

Each relevant module should support:

- On-screen views
- Search and filters
- Excel export
- PDF export
- Scheduled reports
- Management dashboards
- Drill-down from summaries to source records

Exports must respect user permissions and entity access.
## 19. Environment Architecture

Three environments are recommended:

### Development

Used for coding and initial testing. It must not use the live production database.

### Staging

Used for user acceptance testing with sanitised or test data.

### Production

Used for live business operations. Only tested and approved releases may be deployed.

Each environment should have separate:

- Configuration
- Secrets
- Database
- File storage
- Logs
- Backup process

## 20. Deployment Architecture

The target production request flow will be:

```text
User Browser
    → HTTPS
    → Nginx
    → Gunicorn
    → Django Application
    → PostgreSQL Database
```

Redis and Celery may be added for scheduled jobs, reminders and longer-running processes.

Secrets must be stored in protected environment configuration and must not be committed to Git.

## 21. Backup and Recovery

The platform should include:

- Automated database backups
- Document-storage backups
- Backup encryption
- Defined retention periods
- Off-server backup copies
- Periodic restore testing
- Pre-deployment backups
- Documented recovery procedure

A backup should not be treated as reliable until restoration has been tested.

## 22. Logging and Monitoring

The production environment should monitor:

- Application errors
- Failed login attempts
- Background-job failures
- Database availability
- Disk usage
- Backup status
- SSL certificate status
- Response time
- Service availability

Sensitive information and passwords must never appear in logs.

## 23. Migration from WorkTrack

Migration will be phased.

### Phase 1 — Preserve and Document

- Keep production WorkTrack operational.
- Complete current-system documentation.
- Preserve database and deployment snapshots.
- Record existing behaviour and business rules.

### Phase 2 — Build the v2 Foundation

- Create the Django project.
- Configure PostgreSQL.
- Implement organisations and entities.
- Implement authentication.
- Implement roles and permissions.
- Implement audit logging.
- Establish tests and deployment controls.

### Phase 3 — Rebuild Current Functions

- Employee master
- Task management
- Task updates
- Reviews
- Daily reports
- My Day
- Compliance reminders

### Phase 4 — Data Migration Testing

- Map existing SQLite tables to the new data model.
- Clean and validate source data.
- Conduct trial migrations.
- Reconcile record counts and critical balances.
- Obtain user acceptance.

### Phase 5 — Controlled Cutover

- Take a final production backup.
- Temporarily freeze new entries in the old application.
- Run the approved migration.
- Validate users and records.
- Conduct business-owner acceptance.
- Switch traffic only after formal approval.
- Retain a documented rollback plan.

The existing production database must never be used as the first migration test.

## 24. Testing Strategy

Testing should cover:

- Authentication
- Permissions
- Organisation and entity isolation
- Business workflows
- Approval rules
- Database migrations
- Imports and exports
- Audit logs
- Security
- Backup restoration
- Performance
- User acceptance

Every production release should pass a defined release checklist.

## 25. Development Governance

Development should follow:

1. One controlled sprint branch at a time.
2. Small and reviewable changes.
3. No direct development in production.
4. Meaningful Git commit messages.
5. Documentation alongside code.
6. Database migration review.
7. Testing before merging.
8. Staging approval before production.
9. Backup before production deployment.
10. Recorded rollback procedure.

## 26. Recommended Delivery Roadmap

### Sprint 1 — Architecture Blueprint

- Finalise architecture
- Define module boundaries
- Approve technology direction
- Define migration principles

### Sprint 2 — Development Foundation

- Create structured Django project
- Configure development settings
- Add dependency management
- Establish automated tests
- Add code-quality controls

### Sprint 3 — Identity and Access

- Organisations and entities
- Users
- Roles and permissions
- Authentication
- Audit foundation

### Sprint 4 — Task Module

- Rebuild core WorkTrack task functions
- Implement assignments, updates and reviews
- Add tests and reports

### Sprint 5 — Compliance Module

- Rebuild compliance reminders
- Add recurring schedules and escalations
- Add compliance dashboard

### Sprint 6 — Migration Pilot

- Map existing SQLite data
- Run test migration
- Reconcile and document results

Further modules will be prioritised based on business value, operational urgency and implementation risk.

## 27. Decisions Requiring Approval

Before Sprint 2 begins, the following decisions should be formally confirmed:

- Django as the backend framework
- PostgreSQL as the target database
- Server-rendered frontend for the initial version
- Modular monolith as the initial architecture
- Continued operation of the existing WorkTrack production system during development
- Task and compliance as the first migrated modules
- AI Copilot beginning with read-only and drafting capabilities
- Introduction of a staging environment before production cutover

## 28. Current-State Conclusion

The existing WorkTrack application is a valuable working prototype and source of business requirements. However, its single-file design, manual routing, basic password hashing and SQLite database are not suitable as the long-term foundation for the broader Matterhorn One vision.

Matterhorn One v2 should therefore be developed as a structured modular platform alongside the existing production application. The old system will remain untouched until the replacement has been tested, reconciled and formally approved.
