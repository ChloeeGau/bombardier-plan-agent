
# ==============================================================================
# Installation & Setup
# ==============================================================================

# Install dependencies using uv package manager
install:
	@command -v uv >/dev/null 2>&1 || { echo "uv is not installed. Installing uv..."; curl -LsSf https://astral.sh/uv/0.8.13/install.sh | sh; source $HOME/.local/bin/env; }
	uv sync

# ==============================================================================
# Playground Targets
# ==============================================================================

# Launch local dev playground
playground:
	@echo "==============================================================================="
	@echo "| 🚀 Starting your agent playground...                                        |"
	@echo "|                                                                             |"
	@echo "| 💡 Try asking: How to save a pandas dataframe to CSV?                       |"
	@echo "|                                                                             |"
	@echo "| 🔍 IMPORTANT: Select the 'app' folder to interact with your agent.          |"
	@echo "==============================================================================="
	uv run adk web . --port 8501 --reload_agents

# ==============================================================================
# Data Ingestion (Vertex AI Search)
# ==============================================================================

# Set up Vertex AI Search datastore (GCS bucket, data connector, search engine)
setup-datastore:
	PROJECT_ID=$$(gcloud config get-value project) && \
	(cd deployment/terraform/dev && terraform init && \
	terraform apply --var-file vars/env.tfvars --var dev_project_id=$$PROJECT_ID --auto-approve \
		-target=google_discovery_engine_search_engine.search_engine_dev)

# Upload sample data and trigger initial sync
data-ingestion:
	PROJECT_ID=$$(gcloud config get-value project) && \
	DATA_STORE_REGION=$$(grep 'data_store_region' deployment/terraform/dev/vars/env.tfvars | sed 's/.*= *"//;s/".*//') && \
	gcloud storage cp gs://bombardier_test_agent/plan-agent/* gs://$$PROJECT_ID-bombardier-plan-agent-docs/ && \
	uv run deployment/terraform/scripts/start_connector_run.py $$PROJECT_ID $$DATA_STORE_REGION bombardier-plan-agent-collection --wait

# Trigger an on-demand sync for the GCS Data Connector
sync-data:
	PROJECT_ID=$$(gcloud config get-value project) && \
	DATA_STORE_REGION=$$(grep 'data_store_region' deployment/terraform/dev/vars/env.tfvars | sed 's/.*= *"//;s/".*//') && \
	uv run deployment/terraform/scripts/start_connector_run.py $$PROJECT_ID $$DATA_STORE_REGION bombardier-plan-agent-collection --wait

# ==============================================================================
# Testing & Code Quality
# ==============================================================================

# Run unit and integration tests
test:
	uv sync --dev
	uv run pytest tests/unit && uv run pytest tests/integration

# ==============================================================================
# Agent Evaluation
# ==============================================================================

# Run agent evaluation using ADK eval
# Usage: make eval [EVALSET=tests/eval/evalsets/basic.evalset.json] [EVAL_CONFIG=tests/eval/eval_config.json]
eval:
	@echo "==============================================================================="
	@echo "| Running Agent Evaluation                                                    |"
	@echo "==============================================================================="
	uv sync --dev --extra eval
	uv run adk eval ./app $${EVALSET:-tests/eval/evalsets/basic.evalset.json} \
		$(if $(EVAL_CONFIG),--config_file_path=$(EVAL_CONFIG),$(if $(wildcard tests/eval/eval_config.json),--config_file_path=tests/eval/eval_config.json,))

# Run evaluation with all evalsets
eval-all:
	@echo "==============================================================================="
	@echo "| Running All Evalsets                                                        |"
	@echo "==============================================================================="
	@for evalset in tests/eval/evalsets/*.evalset.json; do \
		echo ""; \
		echo "▶ Running: $$evalset"; \
		$(MAKE) eval EVALSET=$$evalset || exit 1; \
	done
	@echo ""
	@echo "✅ All evalsets completed"

# Run code quality checks (codespell, ruff, ty)
lint:
	uv sync --dev --extra lint
	uv run codespell
	uv run ruff check . --diff
	uv run ruff format . --check --diff
	uv run ty check .

# --- Commands from Agent Starter Pack ---

backend: deploy

deploy:
	# Export dependencies to requirements file using uv export.
	(uv export --no-hashes --no-header --no-dev --no-emit-project --no-annotate > app/app_utils/.requirements.txt 2>/dev/null || \
	uv export --no-hashes --no-header --no-dev --no-emit-project > app/app_utils/.requirements.txt) && \
	uv run -m app.app_utils.deploy \
		--source-packages=./app \
		--entrypoint-module=app.agent_engine_app \
		--entrypoint-object=agent_engine \
		--requirements-file=app/app_utils/.requirements.txt \
		$(if $(AGENT_IDENTITY),--agent-identity) \
		$(if $(filter command line,$(origin SECRETS)),--set-secrets="$(SECRETS)")

register-gemini-enterprise:
	@uvx agent-starter-pack@0.41.3 register-gemini-enterprise

