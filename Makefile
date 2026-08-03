.PHONY: demo patch-demo baseline eval test

demo:
	PYTHONPATH=src python3 -m issuelens agent \
		--repo fixtures/calculator_repo \
		--issue evals/cases/division_by_zero.md \
		--policy offline \
		--run-dir runs

patch-demo:
	@set -eu; \
	printf '%s\n' '候选补丁 / Candidate Patch:'; \
	cat evals/patches/division_by_zero.diff; \
	printf '\n'; \
	proposal_json="$$(PYTHONPATH=src python3 -m issuelens patch-proposal \
		--repo fixtures/calculator_repo \
		--diff evals/patches/division_by_zero.diff)"; \
	printf '%s\n' "$$proposal_json"; \
	proposal_hash="$$(printf '%s\n' "$$proposal_json" | \
		python3 -c 'import json, sys; print(json.load(sys.stdin)["proposal_hash"])')"; \
	printf '\n请先审查候选补丁及上述提案。 / Review the candidate patch and proposal above.\n'; \
	printf '请输入完整 Proposal Hash 以明确批准 / Paste the full Proposal Hash to approve: '; \
	IFS= read -r approved_hash; \
	if [ "$$approved_hash" != "$$proposal_hash" ]; then \
		printf '%s\n' '审批已拒绝：Proposal Hash 不匹配。 / Approval rejected: Proposal Hash mismatch.' >&2; \
		exit 1; \
	fi; \
	printf '请输入审批人名称 / Enter approver name: '; \
	IFS= read -r approved_by; \
	if [ -z "$$approved_by" ]; then \
		printf '%s\n' '审批已拒绝：审批人名称不能为空。 / Approval rejected: approver name cannot be empty.' >&2; \
		exit 1; \
	fi; \
	review_json="$$(PYTHONPATH=src python3 -m issuelens patch-review \
		--repo fixtures/calculator_repo \
		--diff evals/patches/division_by_zero.diff \
		--run-id patch-demo \
		--approved-by "$$approved_by" \
		--approve-proposal-hash "$$approved_hash" \
		--audit-dir runs/patch-demo/audit)"; \
	printf '\n%s\n' "$$review_json"; \
	receipt_hash="$$(printf '%s\n' "$$review_json" | \
		python3 -c 'import json, sys; print(json.load(sys.stdin)["receipt_hash"])')"; \
	printf '\n'; \
	PYTHONPATH=src python3 -m issuelens audit-report \
		--audit-dir runs/patch-demo/audit \
		--receipt-hash "$$receipt_hash"

baseline:
	PYTHONPATH=src python3 -m issuelens analyze \
		--repo fixtures/calculator_repo \
		--issue evals/cases/division_by_zero.md \
		--run-dir runs

eval:
	PYTHONPATH=src python3 -m issuelens eval \
		--manifest evals/manifest.json \
		--run-dir runs/eval

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v
