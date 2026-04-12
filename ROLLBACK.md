# Rollback Reference

Baseline checkpoint:
- Commit: chore: baseline before nutrition confidence loop
- Tag: v0.1-baseline-before-nutrition

Restore options:
1. Checkout baseline tag directly (detached HEAD)
   - git checkout v0.1-baseline-before-nutrition

2. Create a recovery branch from baseline tag
   - git checkout -b recovery/from-baseline v0.1-baseline-before-nutrition

3. Return current branch to baseline commit (destructive to later local commits)
   - git reset --hard v0.1-baseline-before-nutrition
