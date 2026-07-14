# Matterhorn One — Git Workflow

## Branch Strategy

### main
Production-ready code only.

### matterhorn-one-development
Integration branch for completed development work.

### sprint-*
Development sprint branches.

Examples:

- sprint-0-foundation
- sprint-1-branding
- sprint-2-architecture

### feature-*
Individual features.

Examples:

- feature/login
- feature/payroll
- feature/dashboard

### hotfix-*
Emergency production fixes.

---

## Commit Message Convention

Use Conventional Commits.

Examples:

- feat: add employee attendance
- fix: correct login issue
- docs: update deployment guide
- refactor: split authentication module
- security: add session timeout
- test: improve login testing
- chore: update dependencies

---

## Development Workflow

1. Checkout latest development branch.
2. Pull latest changes.
3. Create a sprint or feature branch.
4. Develop and test locally.
5. Commit changes.
6. Push to GitHub.
7. Review changes.
8. Merge into `matterhorn-one-development`.
9. Perform integration testing.
10. Merge into `main` only after release approval.

---

## Rules

- Never develop directly on `main`.
- Never force-push to `main`.
- Never commit database files.
- Never commit secrets or passwords.
- Every production release must have a Git tag.
- Every production deployment must have a database backup.

---

## Versioning

Use Semantic Versioning.

Example:

v0.1.0

MAJOR.MINOR.PATCH

- MAJOR = breaking changes
- MINOR = new features
- PATCH = bug fixes

---

## Release Tags

Example:

git tag -a v0.1.0 -m "Matterhorn One Development Baseline"

git push origin v0.1.0

# Matterhorn One — Git Workflow

## Branch Strategy

### main
Production-ready code only.

### matterhorn-one-development
Integration branch for completed development work.

### sprint-*
Development sprint branches.

Examples:

- sprint-0-foundation
- sprint-1-branding
- sprint-2-architecture

### feature-*
Individual features.

Examples:

- feature/login
- feature/payroll
- feature/dashboard

### hotfix-*
Emergency production fixes.

---

## Commit Message Convention

Use Conventional Commits.

Examples:

- feat: add employee attendance
- fix: correct login issue
- docs: update deployment guide
- refactor: split authentication module
- security: add session timeout
- test: improve login testing
- chore: update dependencies

---

## Development Workflow

1. Checkout latest development branch.
2. Pull latest changes.
3. Create a sprint or feature branch.
4. Develop and test locally.
5. Commit changes.
6. Push to GitHub.
7. Review changes.
8. Merge into `matterhorn-one-development`.
9. Perform integration testing.
10. Merge into `main` only after release approval.

---

## Rules

- Never develop directly on `main`.
- Never force-push to `main`.
- Never commit database files.
- Never commit secrets or passwords.
- Every production release must have a Git tag.
- Every production deployment must have a database backup.

---

## Versioning

Use Semantic Versioning.

Example:

v0.1.0

MAJOR.MINOR.PATCH

- MAJOR = breaking changes
- MINOR = new features
- PATCH = bug fixes

---

## Release Tags

Example:

git tag -a v0.1.0 -m "Matterhorn One Development Baseline"

git push origin v0.1.0
