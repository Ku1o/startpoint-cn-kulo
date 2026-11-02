
# StarPoint CN character awakening

Use the workspace and repository `AGENTS.md` already loaded for this task; read missing or changed rules. The configured Git source worktree also owns the local 8001 runtime. The compatibility mirror is not an ordinary deployment target; only an explicitly authorized independent runtime directory needs synchronization.

Before implementation, identify the target character ID/code, intended designs, official source rows and affected terminal resource state. Reuse verified schema/parser evidence for unchanged inputs, while checking each character's actual rows, board layout and selection results. Rediscover structure when the schema/parser or relevant chain inputs change, evidence is missing, or results conflict; do not infer behavior from page labels or copy the first case's slot mapping.

Treat any awakening that changes abilities 4–6 or a board beyond the official awakening board as a client/server state-model change, not a data-only balance edit. Before publishing it, pass the expanded-board compatibility gate in references/workflow.md（历史本地记录）: board-wide node state, client lookup keys, incremental-response behavior, full-load convergence, old-save repair, and real-client restart behavior must agree.

Read the relevant sections of references/workflow.md（历史本地记录） for client/server discovery, failure modes, version correction, local rollout and verification by change type. Consult matching entries in references/case-ledger.md（历史本地记录） when reusing a layout or diagnosing a known failure; do not reread the entire ledger for a routine character using confirmed structure.

Maintain cases when a new layout, failure, correction or additional acceptance evidence changes reusable knowledge; update the existing matching case where appropriate. Repeated application without new information needs only the task's ordinary result record. Promote a lesson only when official data or multiple independent characters support it; contradictions require narrowing the rule while retaining relevant historical evidence.

Keep cloud release, packaging, commit and push outside scope unless explicitly requested. Before an authorized runtime or database mutation, preserve only the named affected files and character state. Same-source local testing does not copy or hash-compare a mirror; a separately authorized runtime target uses exact-path synchronization, never whole-tree replacement.

Report separately what was verified through data replay/API tests and what was verified on a real client. A correct final character panel does not prove that the awakening page labels accurately describe every switched ability.
